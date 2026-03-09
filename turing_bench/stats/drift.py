"""Drift detection - identify performance degradation over time."""

from typing import Tuple, Dict, Any


def detect_drift(latencies: list, threshold_percent: float = 5.0) -> Dict[str, Any]:
    """
    Detect performance drift across a run sequence.

    Splits runs into first half and second half, compares means.
    A drift indicates thermal throttling, memory fragmentation, or
    other system-level degradation.

    Args:
        latencies: List of latency values in ms
        threshold_percent: Drift threshold as percentage (default 5%)

    Returns:
        Dict with drift_percent, has_drift, message
    """

    if len(latencies) < 2:
        return {
            "drift_percent": 0.0,
            "has_drift": False,
            "message": "Need at least 2 samples for drift detection",
        }

    mid = len(latencies) // 2
    first_half = latencies[:mid]
    second_half = latencies[mid:]

    first_mean = sum(first_half) / len(first_half) if first_half else 0
    second_mean = sum(second_half) / len(second_half) if second_half else 0

    if first_mean == 0:
        drift_percent = 0.0
    else:
        drift_percent = ((second_mean - first_mean) / first_mean) * 100

    has_drift = abs(drift_percent) > threshold_percent

    if drift_percent > 0:
        message = f"Performance degradation: +{drift_percent:.1f}%"
    elif drift_percent < 0:
        message = f"Performance improvement: {drift_percent:.1f}%"
    else:
        message = "No drift detected"

    return {
        "drift_percent": drift_percent,
        "has_drift": has_drift,
        "first_half_mean": first_mean,
        "second_half_mean": second_mean,
        "message": message,
    }
