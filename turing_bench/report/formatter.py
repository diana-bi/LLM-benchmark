"""Report formatting - display validity and performance results."""

from typing import Dict, Any, List


def format_validity_report(results: Dict[str, Any]) -> str:
    """
    Format validity gate section of report.

    Shows pass/fail for each scenario and overall verdict.
    """

    lines = [
        "VALIDITY GATE",
        "─" * 60,
    ]

    all_passed = True

    for scenario_id, result in results.items():
        passed = result.get("passed", False)
        similarity = result.get("similarity", 1.0)
        exact_match = result.get("exact_match", False)

        if passed:
            status = "✓ PASS"
        else:
            status = "✗ FAIL"
            all_passed = False

        if exact_match:
            lines.append(f"  {scenario_id:<30} {status}  (exact-match: ✓)")
        else:
            lines.append(f"  {scenario_id:<30} {status}  (similarity: {similarity:.2f})")

    lines.append("")
    if all_passed:
        lines.append("Overall: ✓ PASS — proceeding to performance measurement")
    else:
        lines.append("Overall: ✗ FAIL — performance measurement skipped")

    return "\n".join(lines)


def format_performance_report(baseline_file: str, results: Dict[str, Any]) -> str:
    """
    Format performance metrics section.

    Only shown if validity gate passed.
    Compares candidate metrics against pinned baseline.
    """

    lines = [
        "",
        "PERFORMANCE",
        f"(vs pinned baseline: {baseline_file})",
        "─" * 60,
        "",
        f"{'Metric':<20} {'Baseline':<15} {'Candidate':<15} {'Δ':<10}",
        "─" * 60,
    ]

    # Add metric comparisons here
    metrics = results.get("metrics", {})
    baseline_metrics = results.get("baseline_metrics", {})

    for metric_name in ["ttft_p50", "ttft_p95", "throughput", "latency_p95"]:
        if metric_name in metrics and metric_name in baseline_metrics:
            baseline_val = baseline_metrics[metric_name]
            candidate_val = metrics[metric_name]
            delta_pct = ((candidate_val - baseline_val) / baseline_val) * 100 if baseline_val != 0 else 0
            delta_sign = "+" if delta_pct > 0 else ""

            lines.append(
                f"{metric_name:<20} {baseline_val:<15.1f} {candidate_val:<15.1f} {delta_sign}{delta_pct:>6.1f}%"
            )

    cv = results.get("cv", 0.0)
    lines.append("")
    lines.append(f"CV (candidate):  {cv:.1f}%  →  {'RELIABLE' if cv < 10 else 'ACCEPTABLE' if cv < 20 else 'HIGH VARIANCE'}")

    return "\n".join(lines)
