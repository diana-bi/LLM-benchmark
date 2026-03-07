"""Runner module for executing benchmark scenarios.

Three execution modes:
1. Sequential (SequentialRunner) - Validates correctness via validity layer.
   One request at a time, isolated. If this fails, run stops.

2. Concurrent workload (ConcurrentRunner) - Measures performance under load.
   Fixed RPS, multiple concurrent requests. Primary performance measurement.

3. Concurrent sweep (SweepRunner) - Optional capacity analysis.
   Gradually increases concurrency to find saturation point and system limits.
"""

from .sequential import SequentialRunner, SequentialRunResult
from .concurrent import ConcurrentRunner, ConcurrentRunResult
from .sweep import SweepRunner, SweepStageResult
from .conformance import check_conformance
from .sse_parser import SSEParser, StreamMetrics

__all__ = [
    "SequentialRunner",
    "SequentialRunResult",
    "ConcurrentRunner",
    "ConcurrentRunResult",
    "SweepRunner",
    "SweepStageResult",
    "check_conformance",
    "SSEParser",
    "StreamMetrics",
]
