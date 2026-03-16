"""Concurrent benchmark runner - measures throughput and latency under load."""

import asyncio
import time
from dataclasses import dataclass, asdict
from typing import Dict, Any, List
import httpx

from .sse_parser import SSEParser


@dataclass
class ConcurrentRunResult:
    """Result of a single concurrent request."""

    scenario_id: str
    request_number: int
    output: str
    ttft_ms: float
    output_tokens: int
    total_time_ms: float
    error: str | None = None


class ConcurrentRunner:
    """Run scenarios concurrently at fixed RPS.

    Purpose: Measure throughput and latency under load (primary performance measurement).
    Uses fixed request-per-second rate to make improvements comparable.
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

    async def run_scenario(
        self,
        scenario: Dict[str, Any],
        rps: int,
        num_requests: int = 500,
        stats_collector=None,
    ) -> List[ConcurrentRunResult]:
        """
        Run scenario concurrently at fixed RPS.

        Args:
            scenario: Scenario definition
            rps: Requests per second target
            num_requests: Total requests to send
            stats_collector: Optional object with on_result(result) called per response.
                             Used by LiveDashboard for real-time display updates.

        Returns:
            List of request results
        """

        results = []
        interval = 1.0 / rps  # Seconds between request starts

        if stats_collector is None:
            print(f"  Running {num_requests} requests at {rps} RPS...", flush=True)

        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            # Launch requests at controlled rate
            tasks = []
            start_time = time.time()

            for req_num in range(num_requests):
                # Calculate when this request should start
                scheduled_time = start_time + (req_num * interval)
                wait_time = max(0, scheduled_time - time.time())

                task = asyncio.create_task(
                    self._scheduled_request(
                        client, scenario, req_num + 1, wait_time, stats_collector
                    )
                )
                tasks.append(task)

                if stats_collector is None and (req_num + 1) % 100 == 0:
                    print(f"    Launched {req_num + 1}/{num_requests}", flush=True)

            if stats_collector is None:
                print("  Waiting for responses...", flush=True)
            results = await asyncio.gather(*tasks)

        return results

    async def _scheduled_request(
        self,
        client: httpx.AsyncClient,
        scenario: Dict[str, Any],
        request_number: int,
        wait_time: float,
        stats_collector=None,
    ) -> ConcurrentRunResult:
        """Execute a single request at scheduled time."""

        # Wait until scheduled time
        if wait_time > 0:
            await asyncio.sleep(wait_time)

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

                result = ConcurrentRunResult(
                    scenario_id=scenario["scenario_id"],
                    request_number=request_number,
                    output=full_output,
                    ttft_ms=metrics.ttft_ms,
                    output_tokens=metrics.total_tokens,
                    total_time_ms=metrics.total_time_ms,
                    error=None,
                )
                if stats_collector is not None:
                    stats_collector.on_result(result)
                return result

        except Exception as e:
            # Log error for debugging
            error_msg = f"{type(e).__name__}: {str(e)}"
            result = ConcurrentRunResult(
                scenario_id=scenario["scenario_id"],
                request_number=request_number,
                output="",
                ttft_ms=0,
                output_tokens=0,
                total_time_ms=0,
                error=error_msg,
            )
            if stats_collector is not None:
                stats_collector.on_result(result)
            return result

    def results_to_dict(self, results: List[ConcurrentRunResult]) -> Dict[str, Any]:
        """Convert results to serializable format."""
        return {
            "requests": [asdict(r) for r in results],
            "count": len(results),
            "errors": sum(1 for r in results if r.error),
        }
