#!/usr/bin/env python
"""Turing LLM Benchmark - CLI entrypoint."""

import asyncio
import sys
from pathlib import Path
from typing import Optional

import click
import yaml

from turing_bench.runner.conformance import check_conformance
from turing_bench.runner.sequential import SequentialRunner
from turing_bench.runner.concurrent import ConcurrentRunner
from turing_bench.report.baseline import BaselineManager


@click.group()
def cli():
    """Turing LLM Benchmark - Service-level validation and performance testing."""
    pass


@cli.command()
@click.option("--endpoint", "-e", required=True, help="Service endpoint URL (e.g., http://localhost:8000)")
@click.option("--timeout", "-t", default=10.0, help="Conformance check timeout in seconds")
def check_conformance_cmd(endpoint: str, timeout: float):
    """Check if an endpoint conforms to Turing benchmark requirements."""

    print(f"Checking conformance for {endpoint}...\n")

    is_conformant, message = check_conformance(endpoint, timeout)

    print(message)
    sys.exit(0 if is_conformant else 1)


@cli.command()
@click.option("--endpoint", "-e", required=True, help="Service endpoint URL")
@click.option("--adapter", "-a", default="llama_cpp", help="Adapter to use (llama_cpp, vllm, etc.)")
@click.option("--phase", "-p", default="baseline", type=click.Choice(["baseline", "candidate"]),
              help="Benchmark phase")
@click.option("--stack-id", "-s", default="test-stack", help="Stack identifier for baseline pinning")
@click.option("--warmup-requests", default=None, type=int, help="Override warmup request count")
@click.option("--output", "-o", default="./baselines", help="Baselines output directory")
def run_benchmark(
    endpoint: str,
    adapter: str,
    phase: str,
    stack_id: str,
    warmup_requests: Optional[int],
    output: str,
):
    """Run the benchmark suite (sequential + concurrent)."""

    print(f"Turing Benchmark v0.1.0")
    print(f"Endpoint: {endpoint}")
    print(f"Adapter: {adapter}")
    print(f"Phase: {phase}\n")

    # Load adapter configuration
    adapter_path = Path(__file__).parent / "turing_bench" / "adapters" / f"{adapter}.yaml"
    if not adapter_path.exists():
        adapter_path = Path(__file__).parent / "turing_bench" / "adapters" / "_default.yaml"

    with open(adapter_path) as f:
        adapter_config = yaml.safe_load(f)

    # Load all scenarios
    scenarios_dir = Path(__file__).parent / "turing_bench" / "scenarios"
    scenarios = []

    for scenario_file in sorted(scenarios_dir.glob("*.yaml")):
        with open(scenario_file) as f:
            scenarios.append(yaml.safe_load(f))

    print(f"Loaded {len(scenarios)} scenarios\n")

    # Run benchmark
    asyncio.run(_run_benchmark_async(
        endpoint=endpoint,
        adapter_config=adapter_config,
        scenarios=scenarios,
        phase=phase,
        stack_id=stack_id,
        warmup_requests=warmup_requests,
        output_dir=output,
    ))


async def _run_benchmark_async(
    endpoint: str,
    adapter_config: dict,
    scenarios: list,
    phase: str,
    stack_id: str,
    warmup_requests: Optional[int],
    output_dir: str,
):
    """Run benchmark asynchronously."""

    # Initialize runners
    seq_runner = SequentialRunner(endpoint, adapter_config)
    conc_runner = ConcurrentRunner(endpoint, adapter_config)

    # Run each scenario
    for scenario in scenarios:
        scenario_id = scenario["scenario_id"]
        print(f"Running scenario: {scenario_id}")

        # Sequential phase
        print(f"  Phase 1: Sequential validation...")
        try:
            seq_results = await seq_runner.run_scenario(
                scenario,
                warmup_requests=warmup_requests,
                num_runs=scenario.get("runs", 50),
            )
            print(f"    ✓ Completed {len(seq_results)} runs")
        except Exception as e:
            print(f"    ✗ Failed: {e}")
            continue

        # Concurrent phase (only if sequential passed)
        concurrent_config = scenario.get("concurrent", {})
        if concurrent_config:
            print(f"  Phase 2: Concurrent performance...")
            try:
                conc_results = await conc_runner.run_scenario(
                    scenario,
                    rps=concurrent_config.get("rps", 16),
                    num_requests=concurrent_config.get("num_requests", 500),
                )
                print(f"    ✓ Completed {len(conc_results)} requests")
            except Exception as e:
                print(f"    ✗ Failed: {e}")
                continue

        print()

    print("Benchmark completed!")
    print(f"Results saved to: {output_dir}")


if __name__ == "__main__":
    cli()
