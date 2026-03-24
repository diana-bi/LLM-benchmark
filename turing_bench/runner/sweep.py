"""Concurrent sweep runner - gradually increases load to find saturation point.

Purpose: Optional deeper analysis to identify system capacity limits and
how latency/throughput degrade as concurrency increases.
"""

import asyncio
import time
from dataclasses import dataclass, asdict
from typing import Dict, Any, List
import httpx

from .sse_parser import SSEParser


@dataclass
class SweepLevelResult:
    """Results for a single concurrency level in the sweep."""

    concurrency: int
    request_number: int
    output: str
    ttft_ms: float
    output_tokens: int
    total_time_ms: float
    error: str | None = None


@dataclass
class SweepStageResult:
    """Aggregated results for a concurrency level."""

    concurrency: int
    num_requests: int
    results: List[SweepLevelResult]
    avg_ttft_ms: float
    avg_latency_ms: float
    p95_latency_ms: float
    throughput_rps: float
    error_count: int


class SweepRunner:
    """Run scenarios with increasing concurrency to identify saturation point.

    Purpose: Explore system capacity under increasing load.
    Gradually increases concurrency levels and collects metrics at each level.
    Useful for deeper analysis but optional for regular benchmark runs.
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
            endpoint_url: Service endpoint
            adapter_config: Backend adapter config
            timeout_s: Per-request timeout
            model_name: Model name to send in API requests (required for Ollama/vLLM)
        """
        self.endpoint_url = endpoint_url
        self.adapter_config = adapter_config
        self.timeout_s = timeout_s
        self.model_name = model_name
        self.parser = SSEParser(adapter_config)

    async def run_scenario_sweep(
        self,
        scenario: Dict[str, Any],
        concurrency_levels: List[int] | None = None,
        requests_per_level: int = 50,
    ) -> List[SweepStageResult]:
        """
        Run scenario with increasing concurrency levels.

        Args:
            scenario: Scenario definition
            concurrency_levels: List of concurrency values to test.
                               Default: [1, 2, 4, 8, 16, 32, 64]
            requests_per_level: Number of concurrent requests at each level

        Returns:
            List of aggregated results for each concurrency level
        """

        if concurrency_levels is None:
            concurrency_levels = [1, 2, 4, 8, 16, 32, 64]

        sweep_results = []

        print(f"  Running sweep with concurrency levels: {concurrency_levels}", flush=True)

        for concurrency in concurrency_levels:
            print(f"  Testing concurrency={concurrency}...", flush=True)

            results = await self._run_at_concurrency(
                scenario, concurrency, requests_per_level
            )

            # Aggregate results for this level
            agg = self._aggregate_results(concurrency, results)
            sweep_results.append(agg)

            print(
                f"    Concurrency {concurrency}: "
                f"Throughput={agg.throughput_rps:.1f} req/s, "
                f"P95 Latency={agg.p95_latency_ms:.1f}ms, "
                f"Errors={agg.error_count}",
                flush=True,
            )

        return sweep_results

    async def _run_at_concurrency(
        self, scenario: Dict[str, Any], concurrency: int, num_requests: int
    ) -> List[SweepLevelResult]:
        """Run requests with fixed concurrency."""

        results = []
        semaphore = asyncio.Semaphore(concurrency)

        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            tasks = []
            stage_start = time.time()

            for req_num in range(num_requests):
                task = asyncio.create_task(
                    self._concurrent_request_limited(
                        client, scenario, req_num + 1, concurrency, semaphore
                    )
                )
                tasks.append(task)

            # Collect results as they complete
            results = await asyncio.gather(*tasks)
            stage_time = time.time() - stage_start

        return results

    async def _concurrent_request_limited(
        self,
        client: httpx.AsyncClient,
        scenario: Dict[str, Any],
        request_number: int,
        concurrency: int,
        semaphore: asyncio.Semaphore,
    ) -> SweepLevelResult:
        """Execute request with concurrency limit."""

        async with semaphore:
            try:
                prompt = scenario["prompt"]
                temperature = scenario.get("temperature", 0.0)
                seed = scenario.get("seed", 42)

                request_start = time.time()

                async with client.stream(
                    "POST",
                    f"{self.endpoint_url}/v1/chat/completions",
                    json={
                        "model": self.model_name,
                        "messages": [{"role": "user", "content": prompt}],
                        "stream": True,
                        "temperature": temperature,
                        "seed": seed,
                        "max_tokens": scenario.get("expected_tokens", 100) * 2,
                    },
                ) as response:

                    if response.status_code != 200:
                        raise RuntimeError(f"Request failed with status {response.status_code}")

                    metrics = await self.parser.parse_stream(response.aiter_lines())
                    full_output = "".join(chunk.content for chunk in metrics.chunks)

                    return SweepLevelResult(
                        concurrency=concurrency,
                        request_number=request_number,
                        output=full_output,
                        ttft_ms=metrics.ttft_ms,
                        output_tokens=metrics.total_tokens,
                        total_time_ms=metrics.total_time_ms,
                        error=None,
                    )

            except Exception as e:
                return SweepLevelResult(
                    concurrency=concurrency,
                    request_number=request_number,
                    output="",
                    ttft_ms=0,
                    output_tokens=0,
                    total_time_ms=0,
                    error=str(e),
                )

    def _aggregate_results(
        self, concurrency: int, results: List[SweepLevelResult]
    ) -> SweepStageResult:
        """Aggregate results for a single concurrency level."""

        successful = [r for r in results if r.error is None]
        errors = len(results) - len(successful)

        if not successful:
            # All failed
            return SweepStageResult(
                concurrency=concurrency,
                num_requests=len(results),
                results=results,
                avg_ttft_ms=0,
                avg_latency_ms=0,
                p95_latency_ms=0,
                throughput_rps=0,
                error_count=errors,
            )

        # Calculate metrics
        ttft_values = [r.ttft_ms for r in successful]
        latency_values = [r.total_time_ms for r in successful]

        avg_ttft = sum(ttft_values) / len(ttft_values)
        avg_latency = sum(latency_values) / len(latency_values)

        # P95 latency
        sorted_latencies = sorted(latency_values)
        p95_idx = int(len(sorted_latencies) * 0.95)
        p95_latency = sorted_latencies[p95_idx]

        # Throughput: completed requests / wall-clock time of the stage
        total_time_s = max(r.total_time_ms for r in successful) / 1000.0
        throughput = len(successful) / total_time_s if total_time_s > 0 else 0

        return SweepStageResult(
            concurrency=concurrency,
            num_requests=len(results),
            results=results,
            avg_ttft_ms=avg_ttft,
            avg_latency_ms=avg_latency,
            p95_latency_ms=p95_latency,
            throughput_rps=throughput,
            error_count=errors,
        )

    def results_to_dict(self, results: List[SweepStageResult]) -> Dict[str, Any]:
        """Convert results to serializable format."""
        return {
            "levels": [
                {
                    "concurrency": r.concurrency,
                    "num_requests": r.num_requests,
                    "avg_ttft_ms": r.avg_ttft_ms,
                    "avg_latency_ms": r.avg_latency_ms,
                    "p95_latency_ms": r.p95_latency_ms,
                    "throughput_rps": r.throughput_rps,
                    "error_count": r.error_count,
                }
                for r in results
            ]
        }
