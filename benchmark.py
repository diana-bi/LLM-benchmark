#!/usr/bin/env python
"""
Turing LLM Benchmark - Production CLI

A universal, external benchmark for LLM serving systems.
Validates correctness and measures performance for any OpenAI-compatible endpoint.

QUICK START:
  # Step 1: Establish baseline (run once, keep forever)
  python benchmark.py baseline --endpoint http://localhost:9000 --stack-id my-model

  # Step 2: Optimize your service
  # (quantization, batching, model selection, etc.)

  # Step 3: Measure after optimization (auto-compares to baseline)
  python benchmark.py candidate --endpoint http://localhost:9000 --stack-id my-model

  # Optional: Include capacity analysis
  python benchmark.py candidate --endpoint http://localhost:9000 --stack-id my-model --sweep

BEST PRACTICES:
  1. HTTP-only design: Benchmark ANY OpenAI-compatible endpoint (vLLM, llama.cpp, Ollama, etc.)
  2. Immutable baselines: Save reference performance once, compare against it always
  3. Sequential → Concurrent flow: Validate correctness before measuring performance
  4. Stack naming: Use descriptive IDs (e.g., qwen2.5-7b_vllm_a100_baseline)
  5. Version-aware: All 4 scenarios are frozen (v1) - changes = major version bump
  6. Pinned comparisons: Never compare two fresh runs; always use a saved baseline
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple

import click
import yaml

from turing_bench.runner.sequential import SequentialRunner
from turing_bench.runner.concurrent import ConcurrentRunner
from turing_bench.runner.sweep import SweepRunner
from turing_bench.validity import ValidityLayer
from turing_bench.report.baseline import BaselineManager
from turing_bench.report.formatter import format_validity_report, format_performance_report
from turing_bench.stats.percentiles import calculate_percentiles
from turing_bench.stats.cv import calculate_cv
from turing_bench.stats.drift import detect_drift
from turing_bench.stats.spike import detect_spikes
from turing_bench.stats.distribution import analyze_distribution, detect_bimodal
from turing_bench.stats.visualize import ascii_time_series, ascii_histogram
from turing_bench.stats.live_dashboard import LiveDashboard


SCENARIOS_DIR = Path(__file__).parent / "turing_bench" / "scenarios"
ADAPTERS_DIR = Path(__file__).parent / "turing_bench" / "adapters"
BASELINES_DIR = Path.cwd() / "baselines"


def compute_metrics(latencies):
    """Compute standard metrics."""
    if not latencies:
        return {}

    percentiles = calculate_percentiles(latencies)
    cv = calculate_cv(latencies)

    return {
        "mean_latency_ms": percentiles.get("mean", 0),
        "p50_latency_ms": percentiles.get("p50", 0),
        "p95_latency_ms": percentiles.get("p95", 0),
        "p99_latency_ms": percentiles.get("p99", 0),
        "cv_percent": cv,
    }


def compute_ttft_metrics(ttft_values):
    """Compute TTFT metrics."""
    if not ttft_values:
        return {}

    percentiles = calculate_percentiles(ttft_values)
    return {
        "mean_ttft_ms": percentiles.get("mean", 0),
        "p50_ttft_ms": percentiles.get("p50", 0),
        "p95_ttft_ms": percentiles.get("p95", 0),
    }


def compare_metrics(baseline_metrics: Dict, candidate_metrics: Dict) -> Dict[str, Tuple[float, str]]:
    """
    Compare candidate metrics against baseline.
    Returns dict of {metric_name: (pct_change, direction)}.
    Negative means improvement, positive means regression.
    """
    comparison = {}

    for metric_key in ["p95_latency_ms", "p95_ttft_ms", "cv_percent"]:
        baseline = baseline_metrics.get(metric_key, 0)
        candidate = candidate_metrics.get(metric_key, 0)

        if baseline and candidate:
            pct_change = ((candidate - baseline) / baseline) * 100
            direction = "↓ better" if pct_change < 0 else "↑ worse" if pct_change > 0 else "→ same"
            comparison[metric_key] = (pct_change, direction)

    return comparison


async def run_benchmark(
    endpoint: str,
    stack_id: str,
    phase: str,
    include_sweep: bool = False,
    fast_mode: bool = False,
    rps_override: Optional[int] = None,
    requests_override: Optional[int] = None,
    show_plots: bool = False,
    show_live: bool = False,
):
    """Run full benchmark."""

    # Load configs
    with open(ADAPTERS_DIR / "_default.yaml") as f:
        adapter_config = yaml.safe_load(f)

    scenarios = {}
    for scenario_file in sorted(SCENARIOS_DIR.glob("*.yaml")):
        with open(scenario_file) as f:
            scenarios[scenario_file.stem] = yaml.safe_load(f)

    # Apply fast mode defaults if enabled
    if fast_mode:
        fast_warmup = 5
        fast_sequential = 25
        fast_concurrent = 100
        for scenario_cfg in scenarios.values():
            scenario_cfg["runs"] = scenario_cfg.get("runs", fast_sequential)
            if "concurrent" not in scenario_cfg:
                scenario_cfg["concurrent"] = {}
            scenario_cfg["concurrent"]["num_requests"] = fast_concurrent

    # Extract model name from stack_id (e.g. "qwen2.5:1.5b_cpu" → "qwen2.5:1.5b")
    model_name = stack_id.rsplit("_", 1)[0] if "_" in stack_id else stack_id

    # Initialize
    seq_runner = SequentialRunner(endpoint, adapter_config, model_name=model_name)
    conc_runner = ConcurrentRunner(endpoint, adapter_config, model_name=model_name)
    sweep_runner = SweepRunner(endpoint, adapter_config, model_name=model_name)

    # Create shared embedding cache to avoid reloading model per scenario
    class _EmbeddingCache:
        pass
    embedding_cache = _EmbeddingCache()
    validity_layer = ValidityLayer(embedding_cache=embedding_cache)

    baseline_manager = BaselineManager(str(BASELINES_DIR))

    BASELINES_DIR.mkdir(exist_ok=True)

    print(f"\n{'=' * 70}")
    print(f"TURING LLM BENCHMARK v0.1.0 - {phase.upper()} PHASE")
    print(f"{'=' * 70}")
    print(f"Endpoint:  {endpoint}")
    print(f"Stack:     {stack_id}")
    print(f"Scenarios: {', '.join(scenarios.keys())}")
    if include_sweep:
        print(f"Sweep:     enabled")
    print()

    # Pre-flight health check
    print("Pre-flight check: verifying server is reachable...")
    try:
        import httpx
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{endpoint}/v1/models")
            if response.status_code != 200:
                click.secho(
                    f"[ERROR] Server returned {response.status_code}. "
                    f"Is the LLM service running and healthy?",
                    fg="red"
                )
                sys.exit(1)
        click.secho("[OK] Server is reachable and responding", fg="green")
    except Exception as e:
        click.secho(f"[ERROR] Cannot reach server at {endpoint}", fg="red")
        click.secho(f"   Details: {e}", fg="red")
        click.secho(f"   Make sure the service is running. Example:", fg="yellow")
        click.secho(f"   docker-compose up -d", fg="yellow")
        sys.exit(1)
    print()

    # Load baseline if candidate phase
    baseline_data = None
    if phase == "candidate":
        try:
            baseline_data = baseline_manager.load_baseline(stack_id)
            baseline_ts = baseline_data.get('timestamp', 'unknown')
            click.secho(f"[OK] Loaded baseline: {baseline_ts}", fg="green")
            print()
        except FileNotFoundError:
            parts = stack_id.split('_')
            model = parts[0] if len(parts) > 0 else "your-model"
            hardware = parts[1] if len(parts) > 1 else "your-hardware"
            click.secho(f"[ERROR] No baseline found for {stack_id}", fg="red")
            print(f"   Run baseline first:")
            print(f"   python benchmark.py baseline --endpoint {endpoint} --model {model} --hardware {hardware}")
            print()
            sys.exit(1)

    results = {
        "stack_id": stack_id,
        "phase": phase,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "endpoint": endpoint,
        "scenarios": {},
        "comparison": {} if phase == "candidate" else None
    }

    # PHASE 1: Sequential
    print(f"{'=' * 70}")
    print("PHASE 1: SEQUENTIAL EXECUTION (Correctness Validation)")
    print(f"{'=' * 70}")
    print()

    validity_passed = True

    for scenario_name, scenario_cfg in scenarios.items():
        print(f"{scenario_name}...")

        try:
            seq_results = await seq_runner.run_scenario(
                scenario_cfg,
                num_runs=scenario_cfg.get("runs", 50)
            )

            successful = [r for r in seq_results if r.error is None]

            if not successful:
                click.secho(f"  FAILED: No successful runs", fg="red")
                validity_passed = False
                continue

            raw_outputs = [r.output for r in successful]
            ttft_values = [r.ttft_ms for r in successful]
            latency_values = [r.total_time_ms for r in successful]

            # Validity check
            baseline_outputs = None
            if baseline_data:
                baseline_outputs = baseline_data.get("scenarios", {}).get(scenario_name, {}).get("raw_outputs")

            validity_config = scenario_cfg.get("validity", {})
            validation_result, _ = validity_layer.validate_batch(
                scenario_id=scenario_name,
                outputs=raw_outputs,
                baseline_outputs=baseline_outputs,
                validity_config=validity_config,
            )

            scenario_result = validation_result.scenarios.get(scenario_name)

            if scenario_result and not scenario_result.overall_passed:
                if scenario_result.overall_severity.value == "FAIL":
                    click.secho(f"  FAILED: {scenario_result.checks[-1].message if scenario_result.checks else 'Unknown'}", fg="red")
                    validity_passed = False
                else:
                    click.secho(f"  WARNING: {scenario_result.checks[-1].message if scenario_result.checks else 'Check warning'}", fg="yellow")
            else:
                click.secho(f"  PASS: {len(successful)} runs", fg="green")

            # Store metrics
            metrics = compute_metrics(latency_values)
            ttft_metrics = compute_ttft_metrics(ttft_values)
            metrics.update(ttft_metrics)

            # Observability analysis on sequential latency sequence (ordered in time)
            seq_analysis = {
                "drift": detect_drift(latency_values),
                "spikes": detect_spikes(latency_values),
            }

            results["scenarios"][scenario_name] = {
                "raw_outputs": raw_outputs,
                "metrics": metrics,
                "sequential_latencies": latency_values,
                "sequential_analysis": seq_analysis,
                "validity": {
                    "passed": scenario_result.overall_passed if scenario_result else False,
                    "severity": scenario_result.overall_severity.value if scenario_result else "FAIL"
                }
            }

        except Exception as e:
            click.secho(f"  ERROR: {e}", fg="red")
            validity_passed = False

    print()

    if not validity_passed:
        click.secho("VALIDITY GATE FAILED - Stopping before concurrent phase", fg="red")
        print()

        # Prepare scenario results for baseline manager
        scenario_results = {}
        for scenario_name, scenario_data in results["scenarios"].items():
            scenario_results[scenario_name] = {
                "raw_outputs": scenario_data.get("raw_outputs", []),
                "metrics": scenario_data.get("metrics", {}),
                "validity": scenario_data.get("validity", {})
            }

        # Prepare metadata
        metadata = {
            "endpoint": results.get("endpoint", ""),
        }

        try:
            baseline_manager.save_baseline(
                stack_id=results["stack_id"],
                phase=results["phase"],
                scenario_results=scenario_results,
                metadata=metadata,
                timestamp=results.get("timestamp")
            )
        except ValueError as e:
            click.secho(f"[ERROR] {e}", fg="red")

        # Report will be displayed at the end (line 395)
        return results

    # PHASE 2: Concurrent
    print(f"{'=' * 70}")
    print("PHASE 2: CONCURRENT WORKLOAD (Performance Measurement)")
    print(f"{'=' * 70}")
    print()

    for scenario_name, scenario_cfg in scenarios.items():
        print(f"{scenario_name}...")

        try:
            # Read concurrent settings from scenario YAML first, adapter config as fallback
            # CLI overrides take precedence
            scenario_concurrent = scenario_cfg.get("concurrent", {})
            rps = rps_override if rps_override else (scenario_concurrent.get("rps") or adapter_config.get("concurrent", {}).get("rps", 16))
            num_requests = requests_override if requests_override else (scenario_concurrent.get("num_requests") or adapter_config.get("concurrent", {}).get("num_requests", 500))

            if show_live:
                dashboard = LiveDashboard(scenario_name, num_requests, rps)
                with dashboard:
                    run_task = asyncio.create_task(
                        conc_runner.run_scenario(
                            scenario_cfg, rps=rps, num_requests=num_requests,
                            stats_collector=dashboard
                        )
                    )
                    while not run_task.done():
                        dashboard.update()
                        await asyncio.sleep(0.25)
                    conc_results = await run_task
                    dashboard.finalize()
            else:
                conc_results = await conc_runner.run_scenario(
                    scenario_cfg,
                    rps=rps,
                    num_requests=num_requests
                )

            successful = [r for r in conc_results if r.error is None]
            total_requests = len(conc_results)
            failed_requests = len([r for r in conc_results if r.error is not None])

            if successful:
                ttft_values = [r.ttft_ms for r in successful]
                latency_values = [r.total_time_ms for r in successful]

                metrics = compute_metrics(latency_values)
                ttft_metrics = compute_ttft_metrics(ttft_values)
                metrics.update(ttft_metrics)

                # Observability analysis on concurrent distribution (unordered, large sample)
                conc_analysis = {
                    "distribution": analyze_distribution(latency_values),
                    "bimodal": detect_bimodal(latency_values),
                }

                # Add to results
                if scenario_name not in results["scenarios"]:
                    results["scenarios"][scenario_name] = {}
                results["scenarios"][scenario_name]["concurrent_metrics"] = metrics
                results["scenarios"][scenario_name]["concurrent_latencies"] = latency_values
                results["scenarios"][scenario_name]["concurrent_analysis"] = conc_analysis
                results["scenarios"][scenario_name]["concurrent_request_count"] = total_requests
                results["scenarios"][scenario_name]["concurrent_error_count"] = failed_requests

                # Compare to baseline if candidate phase
                if phase == "candidate" and baseline_data:
                    baseline_metrics = baseline_data.get("scenarios", {}).get(scenario_name, {}).get("concurrent_metrics", {})
                    if baseline_metrics:
                        comparison = compare_metrics(baseline_metrics, metrics)
                        results["comparison"][scenario_name] = comparison
                        p95 = metrics.get("p95_latency_ms", 0)
                        click.secho(f"  PASS: P95={p95:.1f}ms", fg="green")
                    else:
                        p95 = metrics.get("p95_latency_ms", 0)
                        click.secho(f"  PASS: P95={p95:.1f}ms", fg="green")
                else:
                    p95 = metrics.get("p95_latency_ms", 0)
                    click.secho(f"  PASS: P95={p95:.1f}ms", fg="green")
            else:
                # All requests failed - store error info for the report
                if scenario_name not in results["scenarios"]:
                    results["scenarios"][scenario_name] = {}
                results["scenarios"][scenario_name]["concurrent_metrics"] = {}
                results["scenarios"][scenario_name]["concurrent_request_count"] = total_requests
                results["scenarios"][scenario_name]["concurrent_error_count"] = failed_requests
                click.secho(f"  ERROR: All {total_requests} requests failed", fg="red")

        except Exception as e:
            click.secho(f"  ERROR: {e}", fg="red")

    print()

    # PHASE 3: Sweep (optional)
    if include_sweep:
        print(f"{'=' * 70}")
        print("PHASE 3: CONCURRENT SWEEP (Capacity Analysis - Optional)")
        print(f"{'=' * 70}")
        print()

        for scenario_name, scenario_cfg in scenarios.items():
            print(f"{scenario_name} (concurrency sweep)...")

            try:
                sweep_results = await sweep_runner.run_scenario_sweep(
                    scenario_cfg,
                    concurrency_levels=[1, 2, 4, 8, 16, 32, 64],
                    requests_per_level=20
                )

                sweep_data = {}
                for result in sweep_results:
                    sweep_data[f"concurrency_{result.concurrency}"] = {
                        "avg_latency_ms": result.avg_latency_ms,
                        "p95_latency_ms": result.p95_latency_ms,
                        "throughput_rps": result.throughput_rps,
                    }

                if scenario_name not in results["scenarios"]:
                    results["scenarios"][scenario_name] = {}
                results["scenarios"][scenario_name]["sweep"] = sweep_data

                click.secho(f"  PASS: Sweep complete", fg="green")

            except Exception as e:
                click.secho(f"  ERROR: {e}", fg="red")

        print()

    # Save baseline using BaselineManager (enforces schema and immutability)
    BASELINES_DIR.mkdir(exist_ok=True)

    # Prepare scenario results for baseline manager
    scenario_results = {}
    for scenario_name, scenario_data in results["scenarios"].items():
        scenario_results[scenario_name] = {
            "raw_outputs": scenario_data.get("raw_outputs", []),
            "metrics": scenario_data.get("metrics", {}),
            "concurrent_metrics": scenario_data.get("concurrent_metrics", {}),
            "validity": scenario_data.get("validity", {}),
            "sweep": scenario_data.get("sweep", {})
        }

    # Prepare metadata
    metadata = {
        "endpoint": results.get("endpoint", ""),
        "timestamp": results.get("timestamp", ""),
    }

    try:
        report_file = baseline_manager.save_baseline(
            stack_id=results["stack_id"],
            phase=results["phase"],
            scenario_results=scenario_results,
            metadata=metadata,
            timestamp=results.get("timestamp")
        )
    except ValueError as e:
        click.secho(f"[ERROR] {e}", fg="red")
        print()
        sys.exit(1)

    # Display report
    display_report(results, show_plots=show_plots)

    return results


def get_cv_tier(cv_percent):
    """Get CV stability tier label."""
    if cv_percent < 5:
        return "VERY STABLE"
    elif cv_percent < 10:
        return "STABLE"
    elif cv_percent < 20:
        return "ACCEPTABLE"
    else:
        return "HIGH VARIANCE"


def display_report(results, show_plots: bool = False):
    """Display formatted report with clean table layout."""
    phase = results.get("phase", "unknown").upper()
    stack_id = results.get("stack_id", "unknown")
    timestamp = results.get("timestamp", "").split("T")[0] if results.get("timestamp") else "unknown"

    print(f"\n{'=' * 80}")
    print(f"REPORT — {stack_id}  |  {phase}  |  {timestamp}")
    print(f"{'=' * 80}\n")

    # VALIDITY GATE
    print("VALIDITY GATE")
    print("-" * 80)
    for scenario_name, data in results["scenarios"].items():
        validity = data.get("validity", {})
        if validity.get("passed"):
            click.secho(f"  {scenario_name:<40} PASS", fg="green")
        elif validity.get("severity") == "WARN":
            click.secho(f"  {scenario_name:<40} WARN", fg="yellow")
        else:
            click.secho(f"  {scenario_name:<40} FAIL", fg="red")
    print()

    # PERFORMANCE METRICS (if at least one scenario passed validity)
    any_valid = any(data.get("validity", {}).get("passed") for data in results["scenarios"].values())
    if any_valid:
        print("PERFORMANCE METRICS (concurrent phase)")
        print("-" * 80)
        print(f"  {'Scenario':<30} {'P95':<12} {'P99':<12} {'TTFT':<10} {'CV':<10} {'ERR':<8}")
        print("  " + "-" * 76)

        for scenario_name, data in results["scenarios"].items():
            concurrent_metrics = data.get("concurrent_metrics", {})

            if concurrent_metrics:  # Concurrent phase succeeded
                p95 = concurrent_metrics.get("p95_latency_ms", 0)
                p99 = concurrent_metrics.get("p99_latency_ms", 0)
                ttft = concurrent_metrics.get("p50_ttft_ms", 0)
                cv = concurrent_metrics.get("cv_percent", 0)

                # Count errors: total_requests - successful
                total_req = data.get("concurrent_request_count", 500)
                error_count = data.get("concurrent_error_count", 0)
                error_pct = (error_count / total_req * 100) if total_req > 0 else 0.0

                # Color code CV based on stability tier
                cv_tier = get_cv_tier(cv)
                cv_color = "green" if cv < 5 else "yellow" if cv < 20 else "red"

                line = f"  {scenario_name:<30} {p95:>10.1f}ms {p99:>10.1f}ms {ttft:>8.1f}ms {cv:>8.1f}% {error_pct:>6.1f}%"
                print(line)

                # Show CV tier warning if variance is high
                if cv >= 20:
                    click.secho(f"    └─ CV {cv_tier} ({cv_tier.lower()}): latency may be unstable under load", fg=cv_color)
            else:  # Concurrent phase failed
                click.secho(f"  {scenario_name:<30} FAILED (no concurrent data)", fg="red")
        print()

        # SWEEP RESULTS (if present)
        has_sweep = any(data.get("sweep") for data in results["scenarios"].values())
        if has_sweep:
            print("CONCURRENCY SWEEP RESULTS")
            print("-" * 80)
            for scenario_name, data in results["scenarios"].items():
                sweep = data.get("sweep", {})
                if sweep:
                    print(f"  {scenario_name}:")
                    print(f"    {'Concurrency':<15} {'Avg Latency':<15} {'P95 Latency':<15} {'Throughput':<12}")
                    print("    " + "-" * 57)
                    for key in sorted(sweep.keys(), key=lambda x: int(x.split("_")[1]) if "_" in x else 0):
                        metrics = sweep[key]
                        concurrency = key.split("_")[1] if "_" in key else key
                        avg_lat = metrics.get("avg_latency_ms", 0)
                        p95_lat = metrics.get("p95_latency_ms", 0)
                        throughput = metrics.get("throughput_rps", 0)
                        print(f"    {concurrency:<15} {avg_lat:<14.1f}ms {p95_lat:<14.1f}ms {throughput:<11.1f} rps")
                    print()

        # COMPARISON vs BASELINE (only show if candidate phase and we have comparison data)
        comparison = results.get("comparison", {})
        if comparison and any(comparison.values()):
            print("COMPARISON vs BASELINE")
            print("-" * 80)
            print(f"  {'Scenario':<30} {'P95 latency':<25} {'TTFT':<20} {'CV':<15}")
            print("  " + "-" * 76)

            for scenario_name, metrics_comparison in comparison.items():
                if metrics_comparison:
                    p95_change, p95_dir = metrics_comparison.get("p95_latency_ms", (0, ""))
                    ttft_change, ttft_dir = metrics_comparison.get("p95_ttft_ms", (0, ""))
                    cv_change, cv_dir = metrics_comparison.get("cv_percent", (0, ""))

                    p95_str = f"{p95_change:+.1f}% {p95_dir}"
                    ttft_str = f"{ttft_change:+.1f}% {ttft_dir}"
                    cv_str = f"{cv_change:+.1f}% {cv_dir}"

                    # Color code
                    p95_color = "green" if p95_change < 0 else "red" if p95_change > 0 else "white"
                    ttft_color = "green" if ttft_change < 0 else "red" if ttft_change > 0 else "white"
                    cv_color = "green" if cv_change < 0 else "red" if cv_change > 0 else "white"

                    # Build clean line
                    output = f"  {scenario_name:<30} "
                    output_parts = [output]

                    # Concatenate all colored parts
                    click.secho(output + "P95: ", fg=None, nl=False)
                    click.secho(f"{p95_str:<21} ", fg=p95_color, nl=False)
                    click.secho("TTFT: ", fg=None, nl=False)
                    click.secho(f"{ttft_str:<16} ", fg=ttft_color, nl=False)
                    click.secho("CV: ", fg=None, nl=False)
                    click.secho(f"{cv_str}", fg=cv_color)
                else:
                    # Scenario in comparison but has no data (failed concurrent)
                    print(f"  {scenario_name:<30} (no concurrent data)")
            print()

    # OBSERVABILITY ANALYSIS
    has_seq_analysis = any(
        data.get("sequential_analysis") for data in results["scenarios"].values()
    )
    has_conc_analysis = any(
        data.get("concurrent_analysis") for data in results["scenarios"].values()
    )
    if has_seq_analysis or has_conc_analysis:
        print("OBSERVABILITY ANALYSIS")
        print("-" * 80)

        for scenario_name, data in results["scenarios"].items():
            seq_analysis = data.get("sequential_analysis", {})
            conc_analysis = data.get("concurrent_analysis", {})

            if not seq_analysis and not conc_analysis:
                continue

            print(f"  {scenario_name}")

            # Drift
            drift = seq_analysis.get("drift", {})
            if drift:
                drift_pct = drift.get("drift_percent", 0)
                drift_icon = "⚠ " if drift.get("has_drift") else "  "
                drift_color = "yellow" if drift.get("has_drift") else None
                click.secho(
                    f"    {drift_icon}Drift:        {drift.get('message', 'n/a')}",
                    fg=drift_color,
                )

            # Spikes
            spikes = seq_analysis.get("spikes", {})
            if spikes:
                spike_icon = "⚠ " if spikes.get("has_spikes") else "  "
                spike_color = "yellow" if spikes.get("has_spikes") else None
                spike_indices = spikes.get("spike_indices", [])
                idx_str = f" at runs {spike_indices[:5]}" if spike_indices else ""
                click.secho(
                    f"    {spike_icon}Spikes:       {spikes.get('message', 'n/a')}{idx_str}",
                    fg=spike_color,
                )

            # Distribution (fat tail)
            dist = conc_analysis.get("distribution", {})
            if dist:
                tail_icon = "⚠ " if dist.get("is_fat_tail") else "  "
                tail_color = "yellow" if dist.get("is_fat_tail") else None
                click.secho(
                    f"    {tail_icon}Fat tail:     {dist.get('message', 'n/a')}",
                    fg=tail_color,
                )

            # Bimodal
            bimodal = conc_analysis.get("bimodal", {})
            if bimodal:
                bim_icon = "⚠ " if bimodal.get("is_bimodal") else "  "
                bim_color = "yellow" if bimodal.get("is_bimodal") else None
                click.secho(
                    f"    {bim_icon}Bimodal:      {bimodal.get('message', 'n/a')}",
                    fg=bim_color,
                )

            # ASCII plots (only when --plots flag is set)
            if show_plots:
                seq_lats = data.get("sequential_latencies", [])
                conc_lats = data.get("concurrent_latencies", [])

                if seq_lats:
                    print()
                    ts = ascii_time_series(seq_lats, title="Sequential latency (ms) — run order")
                    if ts:
                        print(ts)

                if conc_lats:
                    print()
                    hist = ascii_histogram(conc_lats, title="Concurrent latency distribution (ms)")
                    if hist:
                        print(hist)

            print()

    # FILES SAVED
    print("FILES SAVED")
    print("-" * 80)
    latest_files = sorted(BASELINES_DIR.glob(f"{results['stack_id']}*"), key=lambda x: x.stat().st_mtime, reverse=True)[:3]
    for f in latest_files:
        if results["stack_id"] in f.name:
            marker = "← this run" if "candidate" in f.name or "baseline" in f.name else ""
            click.secho(f"  {f.name:<50} {marker}", fg="cyan")
    print()

    click.secho("Benchmark complete!", fg="green")
    print(f"{'=' * 80}\n")


@click.group()
def main():
    """
    Turing LLM Benchmark - Hardware-Aware Optimization Benchmark

    Commands:
      baseline   - Establish baseline performance (run once, keep forever)
      candidate  - Measure after optimization (auto-compares to baseline)
      list       - List all saved baselines
      promote    - Promote a candidate run to a new baseline
    """
    pass


@main.command()
@click.argument("phase", type=click.Choice(["baseline", "candidate"], case_sensitive=False))
@click.option("--endpoint", "-e", required=True, help="LLM service endpoint (e.g., http://localhost:9000)")
@click.option("--model", "-m", required=True, help="Model name (e.g., qwen2.5-7b, llama2-7b)")
@click.option("--hardware", "-hw", required=True, help="Hardware (e.g., cpu, a100, xeon, macos)")
@click.option("--sweep", is_flag=True, help="Also run optional capacity sweep (concurrency levels)")
@click.option("--fast", is_flag=True, help="Fast mode: reduced warmup/runs for quick iteration")
@click.option("--rps", type=int, default=None, help="Override RPS for concurrent phase")
@click.option("--requests", type=int, default=None, help="Override request count for concurrent phase")
@click.option("--plots", is_flag=True, help="Show ASCII time-series and histogram plots in the report")
@click.option("--live", "live_dashboard", is_flag=True, help="Show live Rich dashboard during concurrent phase")
def run_phase(phase: str, endpoint: str, model: str, hardware: str, sweep: bool, fast: bool, rps: Optional[int], requests: Optional[int], plots: bool, live_dashboard: bool):
    """
    Run benchmark (baseline or candidate phase).

    \b
    WORKFLOW:
    1. python benchmark.py run-phase baseline --endpoint ... --model qwen2.5-7b --hardware a100
    2. (optimize your service)
    3. python benchmark.py run-phase candidate --endpoint ... --model qwen2.5-7b --hardware a100

    Optional: Add capacity analysis with --sweep
    """

    # Auto-generate stack-id from model + hardware (simplifies for user)
    stack_id = f"{model}_{hardware}"

    try:
        asyncio.run(run_benchmark(endpoint, stack_id, phase.lower(), sweep, fast, rps, requests, show_plots=plots, show_live=live_dashboard))
    except KeyboardInterrupt:
        click.secho("\nBenchmark interrupted", fg="red")
        sys.exit(1)
    except Exception as e:
        click.secho(f"\nError: {e}", fg="red")
        import traceback
        traceback.print_exc()
        sys.exit(1)


@main.command(name="baseline")
@click.option("--endpoint", "-e", required=True, help="LLM service endpoint (e.g., http://localhost:9000)")
@click.option("--model", "-m", required=True, help="Model name (e.g., qwen2.5-7b, llama2-7b)")
@click.option("--hardware", "-hw", required=True, help="Hardware (e.g., cpu, a100, xeon, macos)")
@click.option("--sweep", is_flag=True, help="Also run optional capacity sweep (concurrency levels)")
@click.option("--fast", is_flag=True, help="Fast mode: reduced warmup/runs for quick iteration")
@click.option("--rps", type=int, default=None, help="Override RPS for concurrent phase")
@click.option("--requests", type=int, default=None, help="Override request count for concurrent phase")
@click.option("--plots", is_flag=True, help="Show ASCII time-series and histogram plots in the report")
@click.option("--live", "live_dashboard", is_flag=True, help="Show live Rich dashboard during concurrent phase")
def baseline_cmd(endpoint: str, model: str, hardware: str, sweep: bool, fast: bool, rps: Optional[int], requests: Optional[int], plots: bool, live_dashboard: bool):
    """Establish baseline performance (run once, keep forever)."""
    stack_id = f"{model}_{hardware}"
    try:
        asyncio.run(run_benchmark(endpoint, stack_id, "baseline", sweep, fast, rps, requests, show_plots=plots, show_live=live_dashboard))
    except KeyboardInterrupt:
        click.secho("\nBenchmark interrupted", fg="red")
        sys.exit(1)
    except Exception as e:
        click.secho(f"\nError: {e}", fg="red")
        import traceback
        traceback.print_exc()
        sys.exit(1)


@main.command(name="candidate")
@click.option("--endpoint", "-e", required=True, help="LLM service endpoint (e.g., http://localhost:9000)")
@click.option("--model", "-m", required=True, help="Model name (e.g., qwen2.5-7b, llama2-7b)")
@click.option("--hardware", "-hw", required=True, help="Hardware (e.g., cpu, a100, xeon, macos)")
@click.option("--sweep", is_flag=True, help="Also run optional capacity sweep (concurrency levels)")
@click.option("--fast", is_flag=True, help="Fast mode: reduced warmup/runs for quick iteration")
@click.option("--rps", type=int, default=None, help="Override RPS for concurrent phase")
@click.option("--requests", type=int, default=None, help="Override request count for concurrent phase")
@click.option("--plots", is_flag=True, help="Show ASCII time-series and histogram plots in the report")
@click.option("--live", "live_dashboard", is_flag=True, help="Show live Rich dashboard during concurrent phase")
def candidate_cmd(endpoint: str, model: str, hardware: str, sweep: bool, fast: bool, rps: Optional[int], requests: Optional[int], plots: bool, live_dashboard: bool):
    """Measure after optimization (auto-compares to baseline)."""
    stack_id = f"{model}_{hardware}"
    try:
        asyncio.run(run_benchmark(endpoint, stack_id, "candidate", sweep, fast, rps, requests, show_plots=plots, show_live=live_dashboard))
    except KeyboardInterrupt:
        click.secho("\nBenchmark interrupted", fg="red")
        sys.exit(1)
    except Exception as e:
        click.secho(f"\nError: {e}", fg="red")
        import traceback
        traceback.print_exc()
        sys.exit(1)


@main.command(name="list")
@click.option("--stack-id", default=None, help="Filter by stack ID (optional)")
def list_cmd(stack_id: str):
    """List all saved baselines."""
    BASELINES_DIR.mkdir(exist_ok=True)
    baseline_manager = BaselineManager(str(BASELINES_DIR))

    try:
        baselines = baseline_manager.list_baselines(stack_id)
        if not baselines:
            print("No baselines found.")
            return

        print(f"\n{'=' * 80}")
        print(f"BASELINES")
        print(f"{'=' * 80}\n")

        for i, baseline_file in enumerate(baselines, 1):
            click.secho(f"{i}. {baseline_file}", fg="cyan")

        print()
    except Exception as e:
        click.secho(f"Error listing baselines: {e}", fg="red")
        sys.exit(1)


@main.command(name="promote")
@click.argument("candidate_file")
def promote_cmd(candidate_file: str):
    """Promote a candidate run to a new baseline."""
    BASELINES_DIR.mkdir(exist_ok=True)
    baseline_manager = BaselineManager(str(BASELINES_DIR))

    try:
        # Resolve the file path
        candidate_path = Path(candidate_file)
        if not candidate_path.is_absolute():
            candidate_path = BASELINES_DIR / candidate_file

        if not candidate_path.exists():
            click.secho(f"Error: Candidate file not found: {candidate_path}", fg="red")
            sys.exit(1)

        promoted_file = baseline_manager.promote_candidate_to_baseline(str(candidate_path))
        click.secho(f"✓ Promoted to baseline: {Path(promoted_file).name}", fg="green")
        print()
    except ValueError as e:
        click.secho(f"Error: {e}", fg="red")
        sys.exit(1)
    except Exception as e:
        click.secho(f"Error: {e}", fg="red")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
