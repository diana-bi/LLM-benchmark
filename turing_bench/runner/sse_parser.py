"""SSE streaming parser for LLM service responses."""

import json
import time
from typing import AsyncIterator, Dict, Any, Optional
from dataclasses import dataclass
import yaml


@dataclass
class StreamChunk:
    """Represents a single token chunk from streaming response."""

    content: str
    timestamp: float  # When this chunk was received
    chunk_number: int


@dataclass
class StreamMetrics:
    """Metrics collected during streaming."""

    ttft_ms: float  # Time to first token
    total_tokens: int
    total_time_ms: float
    chunks: list[StreamChunk]


class SSEParser:
    """Parse Server-Sent Events from LLM service responses.

    Handles backend-specific format variations via adapter config.
    """

    def __init__(self, adapter_config: Dict[str, Any]):
        """
        Initialize parser with backend adapter configuration.

        Args:
            adapter_config: YAML config specifying SSE format for this backend
                Expected keys:
                - sse_content_path: JSONPath to content field (e.g., "choices[0].delta.content")
                - done_signal: Signal indicating stream end (e.g., "[DONE]")
                - empty_delta_check: How to identify empty deltas
        """
        self.sse_content_path = adapter_config.get("sse_content_path", "choices[0].delta.content")
        self.done_signal = adapter_config.get("done_signal", "[DONE]")
        self.empty_delta_check = adapter_config.get("empty_delta_check", 'content == "" or content missing')

    async def parse_stream(
        self, response_iterator: AsyncIterator[str], timeout_s: float = 30.0
    ) -> StreamMetrics:
        """
        Parse SSE stream and collect metrics.

        Args:
            response_iterator: Async iterator of response lines
            timeout_s: Timeout for entire stream

        Returns:
            StreamMetrics with TTFT and content chunks
        """

        chunks = []
        ttft_ms = None
        stream_start = time.time()
        chunk_number = 0

        async for line in response_iterator:
            elapsed = (time.time() - stream_start) * 1000

            if elapsed > timeout_s * 1000:
                raise TimeoutError(f"Stream parsing timed out after {timeout_s}s")

            if not line.strip():
                continue

            # Parse SSE line
            if line.startswith("data: "):
                data_str = line[6:].strip()

                # Check for end signal
                if data_str == self.done_signal:
                    break

                # Parse JSON chunk
                try:
                    chunk_data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                # Extract content using path
                content = self._extract_content(chunk_data)

                # Skip empty deltas
                if content == "":
                    continue

                # Record first token time
                if ttft_ms is None:
                    ttft_ms = elapsed

                chunk = StreamChunk(
                    content=content, timestamp=stream_start + elapsed / 1000, chunk_number=chunk_number
                )
                chunks.append(chunk)
                chunk_number += 1

        if ttft_ms is None:
            ttft_ms = (time.time() - stream_start) * 1000

        total_time_ms = (time.time() - stream_start) * 1000

        return StreamMetrics(
            ttft_ms=ttft_ms, total_tokens=len(chunks), total_time_ms=total_time_ms, chunks=chunks
        )

    def _extract_content(self, chunk_data: Dict[str, Any]) -> str:
        """
        Extract content from chunk using configured path.

        Handles paths like:
        - "choices[0].delta.content" (vLLM)
        - "content" (llama.cpp)
        """

        try:
            value = chunk_data
            for key in self.sse_content_path.replace("[0]", ".0").split("."):
                if key.isdigit():
                    value = value[int(key)]
                else:
                    value = value.get(key, "")

            return value if value else ""
        except (KeyError, TypeError, AttributeError):
            return ""


def load_adapter_config(adapter_path: str) -> Dict[str, Any]:
    """Load adapter configuration from YAML file."""
    with open(adapter_path, "r") as f:
        return yaml.safe_load(f)
