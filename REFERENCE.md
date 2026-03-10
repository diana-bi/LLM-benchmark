# Quick Reference - How Everything Works

## Three Execution Modes (Automatic)

```
python -m turing_bench run --endpoint http://localhost:8000 --phase baseline --stack-id mystack
                                        │
                    ┌───────────────────┼───────────────────┐
                    ↓                   ↓                   ↓
                PHASE 1           PHASE 2               PHASE 3
             SEQUENTIAL         CONCURRENT             SWEEP
          (Correctness)        (Performance)          (Optional)
             50 runs            500 requests          Capacity
             1 at a time        At fixed RPS          Increasing load
```

---

## PHASE 1: SEQUENTIAL EXECUTION
**File**: `turing_bench/runner/sequential.py`

```
Purpose: Validate correctness before measuring performance
├─ Warmup: 20 requests (discarded)
├─ Measurement: 50 runs (validated)
├─ Concurrency: 1 (send one at a time)
└─ Duration: ~5 min

Process:
  for run in 1..50:
    request → parse streaming response → measure latency → VALIDATE
    └─ Layer 1: Sanity (empty, length)
    └─ Layer 2: Structural (JSON, syntax)
    └─ Layer 3: Semantic similarity (embedding)
    └─ Layer 4: Exact-match (control only)

Result: SequentialRunResult
├─ scenario_id
├─ run_number (1-50)
├─ output (full generated text)
├─ ttft_ms (time to first token)
├─ total_time_ms (full latency)
└─ error (None if success)

Metrics Computed:
├─ Mean, P50, P95, P99 latency
├─ Mean, P50, P95 TTFT
├─ CV (coefficient of variation)
└─ Validity status (PASS/WARN/FAIL)

Decision:
├─ If ANY FAIL severity → STOP, don't continue to Phase 2
└─ If ALL PASS → Continue to Phase 2
```

---

## PHASE 2: CONCURRENT WORKLOAD
**File**: `turing_bench/runner/concurrent.py`

```
Purpose: Measure performance under realistic load
├─ Total requests: 500 per scenario
├─ Rate: Fixed RPS (e.g., 16 for A100)
├─ Concurrency: Auto-calculated (e.g., 32)
├─ Duration: ~5-10 min
└─ Only runs if Phase 1 PASSED

Process:
  Launch requests at controlled rate
  ├─ Time 0ms:   Start requests 1-32
  ├─ Time 62ms:  Request 1 finishes → Start request 33
  ├─ Time 125ms: Request 2 finishes → Start request 34
  └─ ... continue until all 500 sent

  NO VALIDATION (already done in Phase 1)
  Focus purely on performance metrics

Result: ConcurrentRunResult
├─ scenario_id
├─ request_number (1-500)
├─ output
├─ ttft_ms
├─ total_time_ms
└─ error

Metrics Computed:
├─ Mean, P50, P95, P99 latency
├─ Mean, P50, P95 TTFT
├─ CV (reliability indicator)
├─ Drift (thermal throttling?)
├─ Spikes (outliers?)
└─ Distribution (fat tail?)
```

---

## PHASE 3: SWEEP (Optional)
**File**: `turing_bench/runner/sweep.py`

```
Purpose: Analyze system capacity at increasing loads
├─ Concurrency levels: 1, 2, 4, 8, 16, 32, 64
├─ Requests per level: 50
├─ Only runs if --sweep flag passed
└─ Results NEVER compared to baseline

Process:
  for concurrency_level in [1, 2, 4, 8, 16, 32, 64]:
    Send 50 requests with this concurrency
    ├─ Measure avg latency
    ├─ Measure P95 latency
    ├─ Calculate throughput
    └─ Check if saturated

Result: SweepStageResult per level
├─ concurrency
├─ num_requests
├─ avg_latency_ms
├─ p95_latency_ms
├─ throughput_rps
└─ error_count

Output: Saturation curve
├─ Shows how latency increases
├─ Shows throughput scaling
└─ Identifies capacity limits
```

---

## Metrics Location Reference

### In Sequential Results
```
results["sequential"][scenario_name]["metrics"] = {
    "mean_ttft_ms": 45.0,
    "p50_ttft_ms": 44.0,
    "p95_ttft_ms": 60.0,
    "mean_latency_ms": 120.5,
    "p50_latency_ms": 118.0,
    "p95_latency_ms": 180.2,
    "p99_latency_ms": 220.5,
    "cv_percent": 8.3,
}
```

### In Concurrent Results
```
results["workload"][scenario_name]["metrics"] = {
    "mean_ttft_ms": 45.0,
    "p50_ttft_ms": 44.0,
    "p95_ttft_ms": 60.0,
    "mean_latency_ms": 120.5,
    "p50_latency_ms": 118.0,
    "p95_latency_ms": 180.2,
    "p99_latency_ms": 220.5,
    "cv_percent": 8.3,
}
```

### Stability Metrics (Ready to Use)
```
# From turing_bench/stats/ modules:

drift = detect_drift(latencies)
# Returns: drift_percent, has_drift, message

spikes = detect_spikes(latencies)
# Returns: spike_count, spike_percent, spike_indices

distribution = analyze_distribution(latencies)
# Returns: p99_p95_ratio, is_fat_tail, is_right_skewed
```

---

## How Metrics Are Computed

### Percentiles
```python
from turing_bench.stats.percentiles import calculate_percentiles

latencies = [120.5, 118.0, 125.3, ...]  # 50 or 500 values
result = calculate_percentiles(latencies)
# Returns: {p50: 118.0, p95: 180.2, p99: 220.5, mean: 120.5, min: 100.0, max: 250.0}
```

### Coefficient of Variation (Reliability)
```python
from turing_bench.stats.cv import calculate_cv

cv = calculate_cv(latencies)  # Returns percentage

# Interpretation:
├─ CV ≤ 5% → GREEN: Results reliable
├─ 5% < CV ≤ 10% → YELLOW: Results noisy (consider re-run)
└─ CV > 10% → RED: Results unreliable (stabilize system)
```

### Drift Detection
```python
from turing_bench.stats.drift import detect_drift

drift = detect_drift(latencies, threshold_percent=5.0)
# Returns:
# ├─ drift_percent: 3.2 (positive = degradation)
# ├─ has_drift: True/False
# ├─ message: "Performance degradation: +3.2%"
# └─ first_half_mean, second_half_mean
```

### Spike Detection
```python
from turing_bench.stats.spike import detect_spikes

spikes = detect_spikes(latencies, multiplier=2.5, max_spike_percent=5.0)
# Returns:
# ├─ spike_count: 2 (number of outliers)
# ├─ spike_percent: 0.4 (as percentage of total)
# ├─ has_spikes: True/False (if > max_spike_percent)
# ├─ spike_indices: [127, 342] (which requests)
# └─ message: "Detected 2 spikes (0.4%)"
```

### Distribution Analysis
```python
from turing_bench.stats.distribution import analyze_distribution

dist = analyze_distribution(latencies)
# Returns:
# ├─ p99_p95_ratio: 1.22 (fat tail indicator)
# ├─ is_fat_tail: True/False (if ratio > 1.5)
# ├─ is_right_skewed: True/False
# └─ message: "P99/P95 ratio: 1.22x"
```

---

## Decision Flow

```
python -m turing_bench run ...
    │
    ├─ PHASE 1: Sequential (50 runs)
    │   │
    │   ├─ Compute metrics
    │   ├─ Check CV
    │   │   ├─ CV ≤ 5% → GREEN
    │   │   ├─ 5% < CV ≤ 10% → YELLOW (warn)
    │   │   └─ CV > 10% → RED (STOP or warn)
    │   │
    │   └─ Check validity
    │       ├─ Any FAIL → STOP here
    │       └─ All PASS → Continue
    │
    ├─ PHASE 2: Concurrent (500 requests)
    │   │
    │   ├─ Compute metrics
    │   ├─ Compute stability (drift, spikes, dist)
    │   └─ Store all results
    │
    ├─ PHASE 3: Sweep (optional)
    │   └─ Analyze saturation point
    │
    └─ Save baseline/candidate JSON
        └─ Display report
```

---

## Test Coverage

All metrics tested in:
- `tests/test_cli_integration.py` - 10 tests
- `tests/test_stability_analysis.py` - 14 tests
- `tests/test_validity_integration.py` - 8 tests

**Status**: 32 tests PASSING ✅

---

## What's Missing (Next Steps)

### Tier 1 (Recommended)
- [ ] CV-based early stopping (stop Phase 2 if Phase 1 CV > 10%)
- [ ] Stability metrics in report output
- [ ] Recommendations display

### Tier 2 (Nice to Have)
- [ ] Matplotlib plotting (--plots flag)
- [ ] Baseline vs candidate deltas (% improvement)

### Tier 3 (Polish)
- [ ] Mock backends for testing
- [ ] User documentation
- [ ] Deprecation warning cleanup

---

## CLI Usage

```bash
# Establish baseline
python -m turing_bench run \
  --endpoint http://localhost:8000 \
  --phase baseline \
  --stack-id mystack

# Measure candidate
python -m turing_bench run \
  --endpoint http://localhost:8000 \
  --phase candidate \
  --stack-id mystack

# With optional sweep
python -m turing_bench run \
  --endpoint http://localhost:8000 \
  --phase candidate \
  --stack-id mystack \
  --sweep
```

---

## Key Files

```
turing_bench/runner/
├─ sequential.py       ← Phase 1 (correctness)
├─ concurrent.py       ← Phase 2 (performance)
├─ sweep.py            ← Phase 3 (capacity)
└─ sse_parser.py       ← Streaming response parser

turing_bench/stats/
├─ percentiles.py      ← P50/P95/P99
├─ cv.py               ← Reliability indicator
├─ drift.py            ← Thermal throttling
├─ spike.py            ← Outlier detection
└─ distribution.py     ← Fat tail detection

turing_bench/validity/
├─ sanity.py           ← Layer 1
├─ structural.py       ← Layer 2
├─ semantic.py         ← Layer 3
└─ exact_match.py      ← Layer 4

turing_bench/report/
├─ baseline.py         ← Save/load baseline
└─ formatter.py        ← Format report

turing_bench/cli.py    ← Main orchestration
```

---

## Summary

✅ **Sequential Phase**: Validates correctness (4-layer gate)
✅ **Concurrent Phase**: Measures performance under load
✅ **Sweep Phase**: Optional capacity analysis
✅ **Metrics**: P50/P95/P99, TTFT, CV, Drift, Spikes, Distribution
✅ **Tests**: 32 passing
⏳ **Next**: CV-based early stopping, report integration
