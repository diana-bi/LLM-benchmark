"""Distribution analysis - detect fat tails, skewness, and bimodal patterns."""

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


def detect_bimodal(
    latencies: list,
    min_cluster_fraction: float = 0.15,
    gap_ratio_threshold: float = 5.0,
) -> Dict[str, Any]:
    """
    Detect bimodal (two-cluster) latency distribution.

    A bimodal distribution typically means two different code paths are being
    exercised: cached vs uncached KV, two batch sizes forming, or fast vs slow
    backend instances.

    Strategy: look for a significant gap in sorted latencies in the middle 70%
    of data. If the largest gap is >> the median gap and both resulting clusters
    are substantial, flag as bimodal.

    Args:
        latencies: List of latency values in ms
        min_cluster_fraction: Minimum fraction of data in each cluster (default 15%)
        gap_ratio_threshold: How many times larger the max gap must be vs median gap

    Returns:
        Dict with is_bimodal, cluster means, gap_ratio, message
    """
    if len(latencies) < 10:
        return {
            "is_bimodal": False,
            "gap_ratio": 0.0,
            "message": "Too few samples for bimodal detection",
        }

    sorted_lats = sorted(latencies)
    n = len(sorted_lats)

    gaps = [sorted_lats[i + 1] - sorted_lats[i] for i in range(n - 1)]

    # Only look for gaps in the middle 70% to avoid outliers distorting the split
    start = int(n * 0.15)
    end = int(n * 0.85)
    mid_gaps = [(gaps[i], i) for i in range(start, min(end, len(gaps)))]

    if not mid_gaps:
        return {"is_bimodal": False, "gap_ratio": 0.0, "message": "Insufficient data"}

    sorted_all_gaps = sorted(gaps)
    median_gap = sorted_all_gaps[len(sorted_all_gaps) // 2]

    if median_gap <= 0:
        return {"is_bimodal": False, "gap_ratio": 0.0, "message": "No variance in data"}

    max_mid_gap, max_gap_idx = max(mid_gaps)
    gap_ratio = max_mid_gap / median_gap

    split_idx = max_gap_idx + 1
    cluster1_frac = split_idx / n
    cluster2_frac = (n - split_idx) / n

    is_bimodal = (
        gap_ratio >= gap_ratio_threshold
        and cluster1_frac >= min_cluster_fraction
        and cluster2_frac >= min_cluster_fraction
    )

    if is_bimodal:
        c1_mean = sum(sorted_lats[:split_idx]) / split_idx
        c2_mean = sum(sorted_lats[split_idx:]) / (n - split_idx)
        message = (
            f"Bimodal: cluster 1 ~{c1_mean:.0f}ms ({cluster1_frac * 100:.0f}% of requests), "
            f"cluster 2 ~{c2_mean:.0f}ms ({cluster2_frac * 100:.0f}%)"
        )
    else:
        message = "Unimodal distribution"

    return {
        "is_bimodal": is_bimodal,
        "gap_ratio": round(gap_ratio, 1),
        "message": message,
    }
