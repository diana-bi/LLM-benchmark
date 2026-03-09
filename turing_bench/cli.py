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
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

import click
import yaml

from .runner import (
    SequentialRunner,
    ConcurrentRunner,
    SweepRunner,
    check_conformance,
)
from .validity import ValidityLayer
from .report.baseline import BaselineManager
from .report.formatter import format_validity_report, format_performance_report


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

    # Initialize validity layer and baseline manager
    validity_layer = ValidityLayer()
    baseline_manager = BaselineManager(str(BASELINES_DIR))

    # Load baseline outputs if in candidate phase
    baseline_data = None
    if phase == "candidate":
        try:
            baseline_data = baseline_manager.load_baseline(stack_id)
            click.echo(f"Loaded baseline: {baseline_data.get('timestamp', 'unknown')}")
            click.echo()
        except FileNotFoundError:
            click.secho(f"Warning: No baseline found for {stack_id}", fg="yellow")
            click.echo()

    sequential_runner = SequentialRunner(endpoint, adapter_config)
    results["sequential"] = {}
    results["validity"] = {}
    sequential_passed = True
    validity_passed = True

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
                raw_outputs = [r.output for r in successful]

                # Compute metrics
                metrics = _compute_metrics(latency_values, ttft_values)

                results["sequential"][scenario_name] = {
                    "runs": len(async_results),
                    "successful": len(successful),
                    "errors": error_count,
                    "metrics": metrics,
                    "raw_outputs": raw_outputs,
                }

                # ===== Validity Checking =====
                baseline_outputs = None
                if baseline_data:
                    baseline_outputs = baseline_data.get("scenarios", {}).get(scenario_name, {}).get("raw_outputs")

                is_valid, scenario_result, severity = _validate_sequential_results(
                    scenario_id=scenario_name,
                    raw_outputs=raw_outputs,
                    baseline_outputs=baseline_outputs,
                    scenario_config=scenario_config,
                    validity_layer=validity_layer,
                )

                # Store validity results
                if scenario_result:
                    validity_data = {
                        "passed": is_valid,
                        "severity": severity,
                        "checks": [],
                    }
                    for check in scenario_result.checks:
                        validity_data["checks"].append({
                            "layer": check.layer,
                            "name": check.name,
                            "passed": check.passed,
                            "severity": check.severity.value,
                            "message": check.message,
                            "score": check.score,
                        })
                    results["validity"][scenario_name] = validity_data
                else:
                    results["validity"][scenario_name] = {"passed": False, "severity": "FAIL"}

                # Update pass/fail status
                if not is_valid and severity == "FAIL":
                    validity_passed = False

                # Display status
                if error_count == 0:
                    click.secho(f"  ✓ {scenario_name}: {len(async_results)} runs", fg="green")
                else:
                    click.secho(
                        f"  ⚠ {scenario_name}: {len(async_results)} runs, {error_count} errors",
                        fg="yellow",
                    )

                if not is_valid:
                    if severity == "FAIL":
                        click.secho(f"    ✗ Validity FAILED: {scenario_result.checks[-1].message if scenario_result.checks else 'unknown'}", fg="red")
                    else:
                        click.secho(f"    ⚠ Validity WARN: {scenario_result.checks[-1].message if scenario_result.checks else 'unknown'}", fg="yellow")
            else:
                click.secho(f"  ✗ {scenario_name}: All requests failed", fg="red")
                validity_passed = False
                sequential_passed = False
                results["sequential"][scenario_name] = {"error": "All requests failed"}
                results["validity"][scenario_name] = {"passed": False, "severity": "FAIL", "message": "All requests failed"}

        except Exception as e:
            click.secho(f"  ✗ {scenario_name}: {e}", fg="red")
            validity_passed = False
            sequential_passed = False
            results["sequential"][scenario_name] = {"error": str(e)}
            results["validity"][scenario_name] = {"passed": False, "severity": "FAIL", "message": str(e)}

    click.echo()

    # Print validity summary
    click.secho("VALIDITY GATE SUMMARY", fg="cyan")
    click.secho("─" * 70, fg="cyan")
    for scenario_name in scenario_configs.keys():
        validity_info = results["validity"].get(scenario_name, {})
        passed = validity_info.get("passed", False)
        severity = validity_info.get("severity", "FAIL")
        if passed:
            click.secho(f"  ✓ {scenario_name:<30} PASS", fg="green")
        elif severity == "WARN":
            click.secho(f"  ⚠ {scenario_name:<30} WARN", fg="yellow")
        else:
            click.secho(f"  ✗ {scenario_name:<30} FAIL", fg="red")
    click.echo()

    if not validity_passed:
        click.secho("VALIDITY GATE FAILED. Stopping before concurrent phase.", fg="red")
        click.echo()
        _output_results(results, output)
        sys.exit(1)

    if not sequential_passed:
        click.secho("Sequential execution had errors. Proceeding with caution.", fg="yellow")
        click.echo()

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
                ttft_values = [r.ttft_ms for r in successful]
                metrics = _compute_metrics(latencies, ttft_values)

                results["workload"][scenario_name] = {
                    "requests": len(async_results),
                    "successful": len(successful),
                    "errors": error_count,
                    "metrics": metrics,
                }

                p95 = metrics.get("p95_latency_ms", 0)
                if error_count == 0:
                    click.secho(f"  ✓ {scenario_name}: P95={p95:.1f}ms", fg="green")
                else:
                    click.secho(f"  ⚠ {scenario_name}: {error_count} errors, P95={p95:.1f}ms", fg="yellow")
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
    # ===========================================================================
    # Baseline Pinning and Comparison
    # ===========================================================================

    # Prepare scenario results for baseline saving
    scenario_results = {}
    for scenario_name in scenario_configs.keys():
        seq_data = results["sequential"].get(scenario_name, {})
        workload_data = results["workload"].get(scenario_name, {})

        scenario_results[scenario_name] = {
            "raw_outputs": seq_data.get("raw_outputs", []),
            "metrics": {
                **seq_data.get("metrics", {}),
                **workload_data.get("metrics", {}),
            },
            "validity": results["validity"].get(scenario_name, {}),
        }

    # Hardware metadata
    metadata = {
        "endpoint": endpoint,
        "adapter": adapter,
        "benchmark_version": "0.1.0",
        "execution_timestamp": datetime.utcnow().isoformat() + "Z",
    }

    # Save baseline or candidate
    try:
        saved_file = baseline_manager.save_baseline(
            stack_id=stack_id,
            phase=phase,
            scenario_results=scenario_results,
            metadata=metadata,
        )
        click.secho(f"Results saved to: {saved_file}", fg="green")
        results["baseline_file"] = str(saved_file)
    except Exception as e:
        click.secho(f"Warning: Could not save baseline: {e}", fg="yellow")

    # ===========================================================================
    # Summary and Output
    # ===========================================================================
    click.secho("=" * 70, fg="cyan")
    click.secho("BENCHMARK COMPLETE", fg="cyan")
    click.secho("=" * 70, fg="cyan")
    click.echo()

    # Print validity summary one more time
    click.secho("VALIDITY GATE", fg="cyan")
    click.secho("─" * 70, fg="cyan")
    for scenario_name in scenario_configs.keys():
        validity_info = results["validity"].get(scenario_name, {})
        passed = validity_info.get("passed", False)
        severity = validity_info.get("severity", "FAIL")
        if passed:
            click.secho(f"  ✓ {scenario_name:<30} PASS", fg="green")
        elif severity == "WARN":
            click.secho(f"  ⚠ {scenario_name:<30} WARN", fg="yellow")
        else:
            click.secho(f"  ✗ {scenario_name:<30} FAIL", fg="red")
    click.echo()

    # Print performance summary
    if validity_passed:
        click.secho("PERFORMANCE METRICS", fg="cyan")
        click.secho("─" * 70, fg="cyan")
        for scenario_name in scenario_configs.keys():
            workload = results["workload"].get(scenario_name, {})
            if workload and "metrics" in workload:
                metrics = workload["metrics"]
                p95 = metrics.get("p95_latency_ms", 0)
                p95_ttft = metrics.get("p95_ttft_ms", 0)
                click.echo(f"  {scenario_name:<30} P95={p95:.1f}ms, TTFT={p95_ttft:.1f}ms")
        click.echo()

    _output_results(results, output)

    click.secho("Done.", fg="green")


def _compute_metrics(latencies: list, ttft_values: list = None) -> Dict[str, float]:
    """Compute standard metrics from latency and TTFT data."""
    if not latencies:
        return {}

    latencies_sorted = sorted(latencies)
    metrics = {
        "mean_latency_ms": sum(latencies) / len(latencies),
        "p50_latency_ms": latencies_sorted[len(latencies_sorted) // 2],
        "p95_latency_ms": latencies_sorted[int(len(latencies_sorted) * 0.95)],
        "p99_latency_ms": latencies_sorted[int(len(latencies_sorted) * 0.99)],
    }

    if ttft_values:
        ttft_sorted = sorted(ttft_values)
        metrics["mean_ttft_ms"] = sum(ttft_values) / len(ttft_values)
        metrics["p50_ttft_ms"] = ttft_sorted[len(ttft_sorted) // 2]
        metrics["p95_ttft_ms"] = ttft_sorted[int(len(ttft_sorted) * 0.95)]

    # Compute coefficient of variation for latency
    if len(latencies) > 1:
        mean = metrics["mean_latency_ms"]
        variance = sum((x - mean) ** 2 for x in latencies) / len(latencies)
        std_dev = variance ** 0.5
        metrics["cv_percent"] = (std_dev / mean * 100) if mean > 0 else 0

    return metrics


def _validate_sequential_results(
    scenario_id: str,
    raw_outputs: list,
    baseline_outputs: Optional[list],
    scenario_config: dict,
    validity_layer: ValidityLayer,
) -> tuple:
    """
    Run validity checks on sequential results.

    Returns: (is_valid, validation_result, severity)
    """
    if not raw_outputs:
        return False, None, "FAIL"

    validity_config = scenario_config.get("validity", {})
    validation_result, per_output = validity_layer.validate_batch(
        scenario_id=scenario_id,
        outputs=raw_outputs,
        baseline_outputs=baseline_outputs,
        validity_config=validity_config,
        scenario_config=scenario_config,
    )

    # Get scenario-specific result
    scenario_result = validation_result.scenarios.get(scenario_id)
    if not scenario_result:
        return False, validation_result, "FAIL"

    is_valid = scenario_result.overall_passed
    severity = scenario_result.overall_severity.value

    return is_valid, scenario_result, severity


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
