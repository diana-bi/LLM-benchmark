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
            adapter_config: YAML config specifying SSE format
                Expected keys:
                - sse_content_path: Primary JSONPath to content field
                - fallback_paths: List of alternate paths to try if primary fails
                - done_signal: Signal indicating stream end
                - alternate_done_signals: List of alternate end signals
        """
        # Primary content path
        self.sse_content_path = adapter_config.get("sse_content_path", "choices[0].delta.content")

        # Fallback paths for auto-detection (try these if primary fails)
        self.fallback_paths = adapter_config.get(
            "fallback_paths",
            [
                "choices[0].delta.content",  # OpenAI format (primary)
                "content",                    # llama.cpp format
                "message.content",            # Alternative nesting
                "delta.content",              # Another variant
                "text",                       # Custom servers
            ],
        )

        # Primary done signal
        self.done_signal = adapter_config.get("done_signal", "[DONE]")

        # Alternate done signals for auto-detection
        self.alternate_done_signals = adapter_config.get(
            "alternate_done_signals",
            [
                "[DONE]",
                '{"stop": true}',
                '{"finish_reason": "stop"}',
            ],
        )

        self.skip_empty_deltas = adapter_config.get("skip_empty_deltas", True)

        # Track which path worked (for logging/debugging)
        self._detected_content_path = None
        self._detected_done_signal = None

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

                # Check for end signal (try primary first, then alternates)
                if self._is_done_signal(data_str):
                    break

                # Parse JSON chunk
                try:
                    chunk_data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                # Extract content using path (with auto-detection fallback)
                content = self._extract_content(chunk_data)

                # Skip empty deltas if configured
                if self.skip_empty_deltas and content == "":
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

        Auto-detects format: tries primary path first, then fallback paths
        until one yields a token. Handles variations like:
        - "choices[0].delta.content" (vLLM, OpenAI standard)
        - "content" (llama.cpp)
        - "message.content" (alternative nesting)
        - "delta.content" (another variant)
        - "text" (custom servers)
        """

        # Try primary path first
        content = self._get_nested_value(chunk_data, self.sse_content_path)
        if content:
            self._detected_content_path = self.sse_content_path
            return content

        # If primary path yields nothing, try fallbacks
        for fallback_path in self.fallback_paths:
            if fallback_path == self.sse_content_path:
                continue  # Skip if same as primary

            content = self._get_nested_value(chunk_data, fallback_path)
            if content:
                self._detected_content_path = fallback_path
                return content

        # No content found in any path
        return ""

    def _get_nested_value(self, data: Dict[str, Any], path: str) -> str:
        """
        Navigate nested dict/list using dot notation with array indexing.

        Examples:
        - "choices[0].delta.content" → data["choices"][0]["delta"]["content"]
        - "content" → data["content"]
        - "message.content" → data["message"]["content"]
        """
        try:
            value = data
            # Replace [n] with .n for consistent splitting
            normalized_path = path.replace("[", ".").replace("]", "")

            for key in normalized_path.split("."):
                if not key:  # Skip empty parts
                    continue

                if key.isdigit():
                    value = value[int(key)]
                else:
                    value = value.get(key, None)

                if value is None:
                    return ""

            return str(value) if value else ""
        except (KeyError, TypeError, AttributeError, IndexError, ValueError):
            return ""

    def _is_done_signal(self, data_str: str) -> bool:
        """
        Check if this line signals end-of-stream.

        Tries primary signal first, then alternates.
        """
        if data_str == self.done_signal:
            self._detected_done_signal = self.done_signal
            return True

        for alt_signal in self.alternate_done_signals:
            if data_str == alt_signal:
                self._detected_done_signal = alt_signal
                return True

        return False


def load_adapter_config(adapter_path: str) -> Dict[str, Any]:
    """Load adapter configuration from YAML file."""
    with open(adapter_path, "r") as f:
        return yaml.safe_load(f)
