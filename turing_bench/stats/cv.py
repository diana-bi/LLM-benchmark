"""Coefficient of variation (CV) - stability/reliability metric."""

from typing import List
import numpy as np


def calculate_cv(latencies: List[float]) -> float:
    """
    Calculate coefficient of variation (CV).

    CV = (standard deviation / mean) * 100

    Indicates reliability:
    - < 5%:   Very stable
    - 5-10%:  Stable
    - 10-20%: Acceptable
    - > 20%:  High variance, potentially unreliable

    Args:
        latencies: List of latency values in milliseconds

    Returns:
        CV as percentage
    """

    if not latencies or len(latencies) < 2:
        return 0.0

    arr = np.array(latencies)
    mean = np.mean(arr)

    if mean == 0:
        return 0.0

    std = np.std(arr)
    cv = (std / mean) * 100

    return float(cv)
