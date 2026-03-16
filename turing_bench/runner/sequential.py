"""Sequential benchmark runner - validates correctness before performance measurement."""

import asyncio
import json
import time
from dataclasses import dataclass, asdict
from typing import Dict, Any, List
import httpx

from .sse_parser import SSEParser, StreamMetrics


@dataclass
class SequentialRunResult:
    """Result of a single sequential run."""

    scenario_id: str
    run_number: int
    output: str
    ttft_ms: float
    output_tokens: int
    total_time_ms: float
    error: str | None = None


class SequentialRunner:
    """Run scenarios sequentially with individual latency tracking.

    Purpose: Validate correctness (validity layer) with clean per-request isolation.
    Not affected by batching or scheduling effects.
    """

    def __init__(
        self,
        endpoint_url: str,
        adapter_config: Dict[str, Any],
        timeout_s: float = 30.0,
        model_name: str = "default",
    ):
        """
        Initialize runner.

        Args:
            endpoint_url: Service endpoint (e.g., http://localhost:8000)
            adapter_config: Backend adapter config with SSE format specification
            timeout_s: Per-request timeout in seconds
            model_name: Model name to send in API requests (required for Ollama/vLLM)
        """
        self.endpoint_url = endpoint_url
        self.adapter_config = adapter_config
        self.timeout_s = timeout_s
        self.model_name = model_name
        self.parser = SSEParser(adapter_config)

    async def run_scenario(
        self, scenario: Dict[str, Any], warmup_requests: int = None, num_runs: int = 50
    ) -> List[SequentialRunResult]:
        """
        Run a single scenario sequentially.

        Args:
            scenario: Scenario definition (from YAML)
            warmup_requests: Override warmup count (None uses scenario default)
            num_runs: Number of measurement runs

        Returns:
            List of run results (warmup runs excluded)
        """

        actual_warmup = warmup_requests or scenario.get("warmup", 20)
        results = []

        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            # Warmup phase - not included in results
            print(f"  Warming up ({actual_warmup} requests)...", flush=True)
            for _ in range(actual_warmup):
                try:
                    await self._single_request(client, scenario)
                except Exception as e:
                    print(f"    Warmup request failed: {e}", flush=True)

            # Measurement phase
            print(f"  Running {num_runs} measurement requests...", flush=True)
            for run_num in range(1, num_runs + 1):
                try:
                    result = await self._single_request(client, scenario, run_number=run_num)
                    results.append(result)

                    if run_num % 10 == 0:
                        print(f"    Completed {run_num}/{num_runs}", flush=True)

                except Exception as e:
                    results.append(
                        SequentialRunResult(
                            scenario_id=scenario["scenario_id"],
                            run_number=run_num,
                            output="",
                            ttft_ms=0,
                            output_tokens=0,
                            total_time_ms=0,
                            error=str(e),
                        )
                    )

        return results

    async def _single_request(
        self,
        client: httpx.AsyncClient,
        scenario: Dict[str, Any],
        run_number: int = 0,
    ) -> SequentialRunResult:
        """Execute a single streaming request."""

        prompt = scenario["prompt"]
        temperature = scenario.get("temperature", 0.0)
        seed = scenario.get("seed", 42)

        request_start = time.time()

        # Make streaming request
        async with client.stream(
            "POST",
            f"{self.endpoint_url}/v1/chat/completions",
            json={
                "model": self.model_name,
                "messages": [{"role": "user", "content": prompt}],
                "stream": True,
                "temperature": temperature,
                "seed": seed,
                "max_tokens": scenario.get("expected_tokens", 100) * 2,  # Allow room for variation
            },
        ) as response:

            if response.status_code != 200:
                raise RuntimeError(f"Request failed with status {response.status_code}")

            # Parse streaming response
            metrics = await self.parser.parse_stream(response.aiter_lines())

            # Reconstruct full output
            full_output = "".join(chunk.content for chunk in metrics.chunks)

            return SequentialRunResult(
                scenario_id=scenario["scenario_id"],
                run_number=run_number,
                output=full_output,
                ttft_ms=metrics.ttft_ms,
                output_tokens=metrics.total_tokens,
                total_time_ms=metrics.total_time_ms,
                error=None,
            )

    def results_to_dict(self, results: List[SequentialRunResult]) -> Dict[str, Any]:
        """Convert results to serializable format."""
        return {
            "runs": [asdict(r) for r in results],
            "count": len(results),
            "errors": sum(1 for r in results if r.error),
        }
