"""Command-line interface for Turing LLM Benchmark.

Supports three execution modes:
1. Sequential - Validates correctness (mandatory gate)
2. Workload - Measures performance under realistic load
3. Sweep - Explores system capacity under increasing concurrency
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional

import click
import yaml

from .runner import (
    SequentialRunner,
    ConcurrentRunner,
    SweepRunner,
    check_conformance,
)


# Get package root directory
PACKAGE_ROOT = Path(__file__).parent
SCENARIOS_DIR = PACKAGE_ROOT / "scenarios"
ADAPTERS_DIR = PACKAGE_ROOT / "adapters"


@click.group()
def cli():
    """Turing LLM Benchmark - Service-level validation and performance testing."""
    pass


@cli.command()
@click.option(
    "--endpoint",
    required=True,
    help="LLM service endpoint (e.g., http://localhost:8000)",
)
@click.option(
    "--adapter",
    required=True,
    help="Backend adapter (e.g., llama_cpp, vllm, ollama, openvino)",
)
def check(endpoint: str, adapter: str):
    """Check if endpoint conforms to Turing benchmark requirements.

    This is a quick pre-flight test to ensure the service exposes
    the OpenAI-compatible /v1/chat/completions API with streaming support.
    """
    click.echo(f"Checking endpoint: {endpoint}")
    click.echo(f"Adapter: {adapter}")

    try:
        result = asyncio.run(check_conformance(endpoint))
        if result:
            click.secho("✓ Endpoint is conformant", fg="green")
            sys.exit(0)
        else:
            click.secho("✗ Endpoint is not conformant", fg="red")
            sys.exit(1)
    except Exception as e:
        click.secho(f"✗ Conformance check failed: {e}", fg="red")
        sys.exit(1)


@cli.command()
@click.option(
    "--endpoint",
    required=True,
    help="LLM service endpoint (e.g., http://localhost:8000)",
)
@click.option(
    "--adapter",
    required=True,
    help="Backend adapter (e.g., llama_cpp, vllm, ollama, openvino)",
)
@click.option(
    "--mode",
    type=click.Choice(["sequential", "workload", "sweep", "full"], case_sensitive=False),
    default="full",
    help="Execution mode. Default: 'full' (sequential + workload)",
)
@click.option(
    "--scenarios",
    multiple=True,
    help="Specific scenarios to run (e.g., small_prompt_v1 large_prompt_v1). "
    "Omit to run all scenarios.",
)
@click.option(
    "--seq-warmup",
    type=int,
    default=None,
    help="Override sequential warmup count (default: from scenario config)",
)
@click.option(
    "--seq-runs",
    type=int,
    default=50,
    help="Number of sequential measurement runs per scenario (default: 50)",
)
@click.option(
    "--workload-rps",
    type=int,
    default=16,
    help="Requests per second for workload mode (default: 16)",
)
@click.option(
    "--workload-concurrency",
    type=int,
    default=32,
    help="Max concurrent requests for workload mode (default: 32)",
)
@click.option(
    "--workload-requests",
    type=int,
    default=500,
    help="Total requests for workload mode (default: 500)",
)
@click.option(
    "--sweep-levels",
    type=str,
    default="1,2,4,8,16,32,64",
    help="Concurrency levels for sweep mode (comma-separated, default: 1,2,4,8,16,32,64)",
)
@click.option(
    "--sweep-per-level",
    type=int,
    default=50,
    help="Requests per concurrency level in sweep mode (default: 50)",
)
@click.option(
    "--output",
    type=click.Path(),
    help="Output JSON file for results (optional)",
)
def run(
    endpoint: str,
    adapter: str,
    mode: str,
    scenarios: tuple,
    seq_warmup: Optional[int],
    seq_runs: int,
    workload_rps: int,
    workload_concurrency: int,
    workload_requests: int,
    sweep_levels: str,
    sweep_per_level: int,
    output: Optional[str],
):
    """Run Turing benchmark against an LLM service.

    Execution modes:

    \b
    sequential   - Correctness validation gate (mandatory, runs first)
    workload     - Performance measurement under realistic load (primary metric)
    sweep        - Capacity analysis with increasing concurrency (optional, exploratory)
    full         - Sequential + Workload (recommended standard run)

    Examples:

    \b
    # Standard benchmark (sequential + workload)
    turing-bench run --endpoint http://localhost:8000 --adapter llama_cpp

    \b
    # Correctness validation only
    turing-bench run --endpoint http://localhost:8000 --adapter llama_cpp --mode sequential

    \b
    # Capacity analysis (sweep mode)
    turing-bench run --endpoint http://localhost:8000 --adapter llama_cpp --mode sweep

    \b
    # Custom workload settings
    turing-bench run --endpoint http://localhost:8000 --adapter llama_cpp \\
      --workload-rps 32 --workload-requests 1000
    """

    click.echo(f"Turing LLM Benchmark")
    click.echo(f"Endpoint: {endpoint}")
    click.echo(f"Adapter: {adapter}")
    click.echo(f"Mode: {mode}")
    click.echo()

    # Load adapter configuration
    adapter_path = ADAPTERS_DIR / f"{adapter}.yaml"
    if not adapter_path.exists():
        click.secho(
            f"✗ Adapter not found: {adapter_path}", fg="red"
        )
        sys.exit(1)

    with open(adapter_path) as f:
        adapter_config = yaml.safe_load(f)

    # Load scenarios
    if scenarios:
        scenario_paths = [SCENARIOS_DIR / f"{s}.yaml" for s in scenarios]
    else:
        scenario_paths = sorted(SCENARIOS_DIR.glob("*.yaml"))

    scenario_configs = {}
    for path in scenario_paths:
        if not path.exists():
            click.secho(f"✗ Scenario not found: {path}", fg="red")
            sys.exit(1)
        with open(path) as f:
            scenario_configs[path.stem] = yaml.safe_load(f)

    click.echo(f"Loaded {len(scenario_configs)} scenario(s)")
    click.echo()

    # Parse sweep levels
    try:
        concurrency_levels = [int(x.strip()) for x in sweep_levels.split(",")]
    except ValueError:
        click.secho(f"✗ Invalid sweep levels: {sweep_levels}", fg="red")
        sys.exit(1)

    results = {}

    # ===========================================================================
    # Mode: Sequential
    # ===========================================================================
    if mode.lower() in ["sequential", "full"]:
        click.secho("=" * 70, fg="cyan")
        click.secho("PHASE 1: SEQUENTIAL EXECUTION (Correctness Validation)", fg="cyan")
        click.secho("=" * 70, fg="cyan")
        click.echo()

        sequential_runner = SequentialRunner(endpoint, adapter_config)
        results["sequential"] = {}

        for scenario_name, scenario_config in scenario_configs.items():
            click.echo(f"Running {scenario_name} (sequential)...")

            try:
                async_results = asyncio.run(
                    sequential_runner.run_scenario(
                        scenario_config,
                        warmup_requests=seq_warmup,
                        num_runs=seq_runs,
                    )
                )

                results["sequential"][scenario_name] = {
                    "runs": len(async_results),
                    "errors": sum(1 for r in async_results if r.error),
                    "mean_ttft_ms": (
                        sum(r.ttft_ms for r in async_results if r.error is None)
                        / len([r for r in async_results if r.error is None])
                        if async_results
                        else 0
                    ),
                    "mean_latency_ms": (
                        sum(r.total_time_ms for r in async_results if r.error is None)
                        / len([r for r in async_results if r.error is None])
                        if async_results
                        else 0
                    ),
                }

                error_count = results["sequential"][scenario_name]["errors"]
                if error_count == 0:
                    click.secho(
                        f"  ✓ {scenario_name}: {seq_runs} runs, no errors",
                        fg="green",
                    )
                else:
                    click.secho(
                        f"  ⚠ {scenario_name}: {seq_runs} runs, {error_count} errors",
                        fg="yellow",
                    )

            except Exception as e:
                click.secho(f"  ✗ {scenario_name}: {e}", fg="red")
                results["sequential"][scenario_name] = {"error": str(e)}
                if mode.lower() == "full":
                    click.secho(
                        "Sequential failed. Stopping before workload phase.",
                        fg="red",
                    )
                    sys.exit(1)

        click.echo()

    # ===========================================================================
    # Mode: Workload
    # ===========================================================================
    if mode.lower() in ["workload", "full"]:
        click.secho("=" * 70, fg="cyan")
        click.secho("PHASE 2: CONCURRENT WORKLOAD (Performance Measurement)", fg="cyan")
        click.secho("=" * 70, fg="cyan")
        click.echo()

        concurrent_runner = ConcurrentRunner(endpoint, adapter_config)
        results["workload"] = {}

        for scenario_name, scenario_config in scenario_configs.items():
            click.echo(
                f"Running {scenario_name} "
                f"({workload_requests} requests @ {workload_rps} RPS)..."
            )

            try:
                async_results = asyncio.run(
                    concurrent_runner.run_scenario(
                        scenario_config,
                        rps=workload_rps,
                        num_requests=workload_requests,
                    )
                )

                successful = [r for r in async_results if r.error is None]
                error_count = len(async_results) - len(successful)

                if successful:
                    latencies = [r.total_time_ms for r in successful]
                    latencies_sorted = sorted(latencies)

                    results["workload"][scenario_name] = {
                        "requests": len(async_results),
                        "errors": error_count,
                        "successful": len(successful),
                        "mean_latency_ms": sum(latencies) / len(latencies),
                        "p50_latency_ms": latencies_sorted[len(latencies_sorted) // 2],
                        "p95_latency_ms": latencies_sorted[
                            int(len(latencies_sorted) * 0.95)
                        ],
                        "p99_latency_ms": latencies_sorted[
                            int(len(latencies_sorted) * 0.99)
                        ],
                        "mean_ttft_ms": (
                            sum(r.ttft_ms for r in successful) / len(successful)
                        ),
                    }

                    if error_count == 0:
                        click.secho(
                            f"  ✓ {scenario_name}: "
                            f"P95={results['workload'][scenario_name]['p95_latency_ms']:.1f}ms",
                            fg="green",
                        )
                    else:
                        click.secho(
                            f"  ⚠ {scenario_name}: "
                            f"{error_count} errors, "
                            f"P95={results['workload'][scenario_name]['p95_latency_ms']:.1f}ms",
                            fg="yellow",
                        )
                else:
                    results["workload"][scenario_name] = {
                        "error": "All requests failed"
                    }
                    click.secho(f"  ✗ {scenario_name}: All requests failed", fg="red")

            except Exception as e:
                click.secho(f"  ✗ {scenario_name}: {e}", fg="red")
                results["workload"][scenario_name] = {"error": str(e)}

        click.echo()

    # ===========================================================================
    # Mode: Sweep
    # ===========================================================================
    if mode.lower() in ["sweep"]:
        click.secho("=" * 70, fg="cyan")
        click.secho("PHASE 3: CONCURRENT SWEEP (Capacity Analysis)", fg="cyan")
        click.secho("=" * 70, fg="cyan")
        click.echo()

        sweep_runner = SweepRunner(endpoint, adapter_config)
        results["sweep"] = {}

        for scenario_name, scenario_config in scenario_configs.items():
            click.echo(f"Running {scenario_name} (sweep)...")

            try:
                async_results = asyncio.run(
                    sweep_runner.run_scenario_sweep(
                        scenario_config,
                        concurrency_levels=concurrency_levels,
                        requests_per_level=sweep_per_level,
                    )
                )

                results["sweep"][scenario_name] = sweep_runner.results_to_dict(
                    async_results
                )

                click.secho(f"  ✓ {scenario_name}: sweep complete", fg="green")

            except Exception as e:
                click.secho(f"  ✗ {scenario_name}: {e}", fg="red")
                results["sweep"][scenario_name] = {"error": str(e)}

        click.echo()

    # ===========================================================================
    # Summary and Output
    # ===========================================================================
    click.secho("=" * 70, fg="cyan")
    click.secho("RESULTS SUMMARY", fg="cyan")
    click.secho("=" * 70, fg="cyan")
    click.echo()

    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        click.secho(f"Results saved to: {output_path}", fg="green")
    else:
        click.echo(json.dumps(results, indent=2))

    click.echo()
    click.secho("Benchmark complete.", fg="green")


if __name__ == "__main__":
    cli()
