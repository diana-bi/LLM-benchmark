"""Percentile calculations for latency metrics."""

from typing import List, Dict, Any
import numpy as np


def calculate_percentiles(latencies: List[float]) -> Dict[str, float]:
    """
    Calculate percentile-based latency metrics.

    Args:
        latencies: List of latency values in milliseconds

    Returns:
        Dictionary with P50, P95, P99 metrics
    """

    if not latencies:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "mean": 0.0, "min": 0.0, "max": 0.0}

    arr = np.array(latencies)

    return {
        "p50": float(np.percentile(arr, 50)),
        "p95": float(np.percentile(arr, 95)),
        "p99": float(np.percentile(arr, 99)),
        "mean": float(np.mean(arr)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
    }


def calculate_throughput(token_counts: List[int], duration_seconds: float) -> float:
    """
    Calculate tokens per second.

    Args:
        token_counts: List of output token counts per request
        duration_seconds: Total time in seconds

    Returns:
        Tokens per second
    """

    if duration_seconds == 0:
        return 0.0

    total_tokens = sum(token_counts)
    return total_tokens / duration_seconds
