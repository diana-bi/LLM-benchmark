"""Command-line interface for Turing LLM Benchmark.

The benchmark runs against a deployed LLM service (OpenAI-compatible API).
It always executes three sequential phases internally:
1. Sequential execution - Correctness validation gate
2. Concurrent workload - Performance measurement under load
3. Optional sweep - Capacity analysis (off by default)

The CLI is simple: point at the endpoint, select baseline or candidate phase,
and the benchmark handles the rest according to the Turing protocol.
"""

import asyncio
import json
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
BASELINES_DIR = Path.cwd() / "baselines"


@click.group()
def cli():
    """Turing LLM Benchmark - Universal service-level validation for any LLM.

    One benchmark for any OpenAI-compatible LLM service:
    - vLLM, llama.cpp, Ollama, OpenVINO, TensorRT-LLM, or custom servers
    - Works anywhere. No backend-specific setup.

    The benchmark validates correctness and measures performance against
    a pinned baseline. Same tool for all backends.

    Typical workflow:

    \b
    1. Establish baseline (run once, keep forever):
       turing-bench run --endpoint http://localhost:8000 \\
         --phase baseline --stack-id my-model-hardware

    2. After optimization, compare:
       turing-bench run --endpoint http://localhost:8000 \\
         --phase candidate --stack-id my-model-hardware

    The benchmark compares candidate against baseline and reports
    improvement/regression in performance and correctness.
    """
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
    help="Backend adapter (e.g., llama_cpp, vllm, ollama, openvino, _default)",
)
def check(endpoint: str, adapter: str):
    """Pre-flight conformance check for an endpoint.

    Verifies that the endpoint exposes OpenAI-compatible /v1/chat/completions
    with streaming support. Works with any backend.

    Example:
        turing-bench check --endpoint http://localhost:8000
    """
    click.echo(f"Checking endpoint: {endpoint}")
    click.echo(f"Adapter: {adapter}")
    click.echo()

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
    required=False,
    default="_default",
    help="Adapter config (default: _default, which works for any OpenAI-compatible endpoint)",
)
@click.option(
    "--phase",
    type=click.Choice(["baseline", "candidate"], case_sensitive=False),
    default="candidate",
    help="Baseline (establish reference) or candidate (measure after optimization). Default: candidate",
)
@click.option(
    "--stack-id",
    required=True,
    help="Unique identifier for this hardware/software stack "
    "(e.g., qwen2.5-7b_vllm_a100, qwen2.5-7b_openvino_xeon). "
    "Baselines are stored per stack.",
)
@click.option(
    "--scenarios",
    multiple=True,
    help="Specific scenarios to run (e.g., small_prompt_v1 large_prompt_v1). "
    "Omit to run all scenarios.",
)
@click.option(
    "--warmup-requests",
    type=int,
    default=None,
    help="Override warmup request count (default: from adapter config)",
)
@click.option(
    "--sweep",
    is_flag=True,
    help="Also run capacity sweep (optional, exploratory)",
)
@click.option(
    "--output",
    type=click.Path(),
    help="Output JSON file for results (optional, default: print to stdout)",
)
def run(
    endpoint: str,
    adapter: str,
    phase: str,
    stack_id: str,
    scenarios: tuple,
    warmup_requests: Optional[int],
    sweep: bool,
    output: Optional[str],
):
    """Run Turing benchmark against any OpenAI-compatible LLM service.

    Works with vLLM, llama.cpp, Ollama, OpenVINO, TensorRT-LLM, or any
    custom server exposing /v1/chat/completions with streaming.

    The benchmark always executes three phases internally:
    1. Sequential execution (50 runs per scenario)
       - Correctness validation gate
       - Runs one request at a time
       - If validity fails: stops, no performance numbers reported

    2. Concurrent workload (500 requests at fixed RPS)
       - Performance measurement under realistic load
       - Only runs if sequential validation passes
       - Primary source of performance metrics

    3. Optional sweep (increasing concurrency)
       - Identifies saturation point and capacity
       - Only if --sweep flag is passed
       - Results reported separately, never compared to baseline

    Examples:

    \b
    # Establish baseline (any backend)
    turing-bench run --endpoint http://localhost:8000 \\
      --phase baseline --stack-id my-model-hardware

    \b
    # Measure candidate after optimization
    turing-bench run --endpoint http://localhost:8000 \\
      --phase candidate --stack-id my-model-hardware

    \b
    # Optional: include capacity analysis
    turing-bench run --endpoint http://localhost:8000 \\
      --phase candidate --stack-id my-model-hardware --sweep
    """

    click.echo(f"Turing LLM Benchmark")
    click.echo(f"Endpoint: {endpoint}")
    click.echo(f"Adapter: {adapter}")
    click.echo(f"Stack: {stack_id}")
    click.echo(f"Phase: {phase.upper()}")
    if sweep:
        click.echo(f"Sweep: enabled (optional capacity analysis)")
    click.echo()

    # Load adapter configuration
    adapter_path = ADAPTERS_DIR / f"{adapter}.yaml"
    if not adapter_path.exists():
        click.secho(
            f"✗ Adapter not found: {adapter_path}",
            fg="red",
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

    click.echo(f"Loaded {len(scenario_configs)} scenario(s): {', '.join(scenario_configs.keys())}")
    click.echo()

    results = {
        "metadata": {
            "endpoint": endpoint,
            "adapter": adapter,
            "stack_id": stack_id,
            "phase": phase,
            "scenarios": list(scenario_configs.keys()),
        }
    }

    # ===========================================================================
    # PHASE 1: Sequential Execution (Correctness Validation)
    # ===========================================================================
    click.secho("=" * 70, fg="cyan")
    click.secho("PHASE 1: SEQUENTIAL EXECUTION (Correctness Validation)", fg="cyan")
    click.secho("=" * 70, fg="cyan")
    click.echo()

    sequential_runner = SequentialRunner(endpoint, adapter_config)
    results["sequential"] = {}
    sequential_passed = True

    for scenario_name, scenario_config in scenario_configs.items():
        click.echo(f"Running {scenario_name}...")

        try:
            async_results = asyncio.run(
                sequential_runner.run_scenario(
                    scenario_config,
                    warmup_requests=warmup_requests,
                    num_runs=scenario_config.get("runs", 50),
                )
            )

            successful = [r for r in async_results if r.error is None]
            error_count = len(async_results) - len(successful)

            if successful:
                ttft_values = [r.ttft_ms for r in successful]
                latency_values = [r.total_time_ms for r in successful]

                results["sequential"][scenario_name] = {
                    "runs": len(async_results),
                    "successful": len(successful),
                    "errors": error_count,
                    "mean_ttft_ms": sum(ttft_values) / len(ttft_values),
                    "mean_latency_ms": sum(latency_values) / len(latency_values),
                    "raw_outputs": [r.output for r in successful],
                }

                if error_count == 0:
                    click.secho(f"  ✓ {scenario_name}: {len(async_results)} runs, no errors", fg="green")
                else:
                    click.secho(
                        f"  ⚠ {scenario_name}: {len(async_results)} runs, {error_count} errors",
                        fg="yellow",
                    )
                    sequential_passed = False
            else:
                click.secho(f"  ✗ {scenario_name}: All requests failed", fg="red")
                sequential_passed = False
                results["sequential"][scenario_name] = {"error": "All requests failed"}

        except Exception as e:
            click.secho(f"  ✗ {scenario_name}: {e}", fg="red")
            sequential_passed = False
            results["sequential"][scenario_name] = {"error": str(e)}

    click.echo()

    if not sequential_passed:
        click.secho("Sequential validation FAILED. Stopping before concurrent phase.", fg="red")
        click.echo()
        _output_results(results, output)
        sys.exit(1)

    # ===========================================================================
    # PHASE 2: Concurrent Workload (Performance Measurement)
    # ===========================================================================
    click.secho("=" * 70, fg="cyan")
    click.secho("PHASE 2: CONCURRENT WORKLOAD (Performance Measurement)", fg="cyan")
    click.secho("=" * 70, fg="cyan")
    click.echo()

    concurrent_runner = ConcurrentRunner(endpoint, adapter_config)
    results["workload"] = {}

    # Get RPS and concurrency from adapter config (with defaults)
    rps = adapter_config.get("concurrent", {}).get("rps", 16)
    concurrency = adapter_config.get("concurrent", {}).get("concurrency", 32)
    num_requests = adapter_config.get("concurrent", {}).get("num_requests", 500)

    for scenario_name, scenario_config in scenario_configs.items():
        click.echo(f"Running {scenario_name} ({num_requests} requests @ {rps} RPS)...")

        try:
            async_results = asyncio.run(
                concurrent_runner.run_scenario(
                    scenario_config,
                    rps=rps,
                    num_requests=num_requests,
                )
            )

            successful = [r for r in async_results if r.error is None]
            error_count = len(async_results) - len(successful)

            if successful:
                latencies = [r.total_time_ms for r in successful]
                latencies_sorted = sorted(latencies)
                ttft_values = [r.ttft_ms for r in successful]

                results["workload"][scenario_name] = {
                    "requests": len(async_results),
                    "successful": len(successful),
                    "errors": error_count,
                    "mean_latency_ms": sum(latencies) / len(latencies),
                    "p50_latency_ms": latencies_sorted[len(latencies_sorted) // 2],
                    "p95_latency_ms": latencies_sorted[int(len(latencies_sorted) * 0.95)],
                    "p99_latency_ms": latencies_sorted[int(len(latencies_sorted) * 0.99)],
                    "mean_ttft_ms": sum(ttft_values) / len(ttft_values),
                }

                if error_count == 0:
                    click.secho(
                        f"  ✓ {scenario_name}: P95={results['workload'][scenario_name]['p95_latency_ms']:.1f}ms",
                        fg="green",
                    )
                else:
                    click.secho(
                        f"  ⚠ {scenario_name}: {error_count} errors, "
                        f"P95={results['workload'][scenario_name]['p95_latency_ms']:.1f}ms",
                        fg="yellow",
                    )
            else:
                click.secho(f"  ✗ {scenario_name}: All requests failed", fg="red")
                results["workload"][scenario_name] = {"error": "All requests failed"}

        except Exception as e:
            click.secho(f"  ✗ {scenario_name}: {e}", fg="red")
            results["workload"][scenario_name] = {"error": str(e)}

    click.echo()

    # ===========================================================================
    # PHASE 3: Optional Sweep (Capacity Analysis)
    # ===========================================================================
    if sweep:
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
                        concurrency_levels=[1, 2, 4, 8, 16, 32, 64],
                        requests_per_level=50,
                    )
                )

                results["sweep"][scenario_name] = sweep_runner.results_to_dict(async_results)
                click.secho(f"  ✓ {scenario_name}: sweep complete", fg="green")

            except Exception as e:
                click.secho(f"  ✗ {scenario_name}: {e}", fg="red")
                results["sweep"][scenario_name] = {"error": str(e)}

        click.echo()

    # ===========================================================================
    # Summary and Output
    # ===========================================================================
    click.secho("=" * 70, fg="cyan")
    click.secho("BENCHMARK COMPLETE", fg="cyan")
    click.secho("=" * 70, fg="cyan")
    click.echo()

    _output_results(results, output)

    click.secho("Done.", fg="green")


def _output_results(results: dict, output_path: Optional[str]):
    """Save or print benchmark results."""
    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(results, f, indent=2)
        click.secho(f"Results saved to: {path}", fg="green")
    else:
        click.echo(json.dumps(results, indent=2))


if __name__ == "__main__":
    cli()
