"""Distribution analysis - detect fat tails, skewness, and bimodality."""

import statistics
from typing import Dict, Any


def analyze_distribution(latencies: list) -> Dict[str, Any]:
    """
    Analyze the shape of the latency distribution.

    Detects fat tails (right-skew) which indicate occasional slow requests
    that don't show up in mean/median but hurt P99.

    Args:
        latencies: List of latency values in ms

    Returns:
        Dict with p99_p95_ratio, is_fat_tail, skewness, message
    """

    if len(latencies) < 3:
        return {
            "p99_p95_ratio": 1.0,
            "is_fat_tail": False,
            "message": "Need at least 3 samples for distribution analysis",
        }

    sorted_latencies = sorted(latencies)

    # Calculate percentiles
    p50_idx = len(sorted_latencies) // 2
    p95_idx = int(len(sorted_latencies) * 0.95)
    p99_idx = int(len(sorted_latencies) * 0.99)

    p50 = sorted_latencies[p50_idx]
    p95 = sorted_latencies[p95_idx]
    p99 = sorted_latencies[p99_idx]

    # P99/P95 ratio indicates tail fatness
    # Normal: 1.0-1.2x
    # Fat tail: >1.5x
    if p95 > 0:
        p99_p95_ratio = p99 / p95
    else:
        p99_p95_ratio = 1.0

    # Simple skewness: if P50 is much closer to P95 than to mean,
    # the tail is heavier on the right (positive skew)
    mean = sum(latencies) / len(latencies)
    is_right_skewed = p50 < mean  # Median < mean indicates right skew

    # Fat tail detection
    is_fat_tail = p99_p95_ratio > 1.5

    # Bimodal detection: two distinct latency populations
    # Algorithm: find largest gap between consecutive sorted values
    # If largest_gap > 5 × median_gap, flag as bimodal
    is_bimodal = False
    bimodal_gap = 0.0
    if len(sorted_latencies) > 1:
        gaps = [sorted_latencies[i + 1] - sorted_latencies[i] for i in range(len(sorted_latencies) - 1)]
        if gaps:
            median_gap = statistics.median(gaps)
            largest_gap = max(gaps)
            # Only flag bimodal if median gap is meaningful (>0.1ms) to avoid noise
            if median_gap > 0.1:
                is_bimodal = largest_gap > 5 * median_gap
                bimodal_gap = largest_gap

    message = f"P99/P95 ratio: {p99_p95_ratio:.2f}x"
    if is_fat_tail:
        message += " - fat tail detected"
    if is_right_skewed:
        message += " (right-skewed)"

    return {
        "p50": p50,
        "p95": p95,
        "p99": p99,
        "mean": mean,
        "p99_p95_ratio": p99_p95_ratio,
        "is_fat_tail": is_fat_tail,
        "is_right_skewed": is_right_skewed,
        "is_bimodal": is_bimodal,
        "bimodal_gap": bimodal_gap,
        "message": message,
    }
