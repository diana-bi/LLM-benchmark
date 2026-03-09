"""Spike detection - identify outlier latencies."""

from typing import Dict, Any, List


def detect_spikes(latencies: list, multiplier: float = 2.5, max_spike_percent: float = 5.0) -> Dict[str, Any]:
    """
    Detect latency spikes (outliers).

    A spike is defined as a latency > median * multiplier.
    Indicates background processes, OS scheduling hiccups, or thermal throttling.

    Args:
        latencies: List of latency values in ms
        multiplier: Spike threshold as median multiplier (default 2.5x)
        max_spike_percent: Max acceptable spike percentage (default 5%)

    Returns:
        Dict with spike_count, spike_percent, has_spikes, spike_indices, message
    """

    if len(latencies) < 2:
        return {
            "spike_count": 0,
            "spike_percent": 0.0,
            "has_spikes": False,
            "spike_indices": [],
            "message": "Need at least 2 samples",
        }

    # Calculate median
    sorted_latencies = sorted(latencies)
    median = sorted_latencies[len(sorted_latencies) // 2]

    # Find spikes
    spike_threshold = median * multiplier
    spike_indices = [i for i, lat in enumerate(latencies) if lat > spike_threshold]
    spike_count = len(spike_indices)
    spike_percent = (spike_count / len(latencies)) * 100

    has_spikes = spike_percent > max_spike_percent

    message = f"Detected {spike_count} spikes ({spike_percent:.1f}%)"
    if has_spikes:
        message += f" - exceeds threshold {max_spike_percent}%"

    return {
        "spike_count": spike_count,
        "spike_percent": spike_percent,
        "has_spikes": has_spikes,
        "spike_indices": spike_indices,
        "median": median,
        "spike_threshold": spike_threshold,
        "message": message,
    }
