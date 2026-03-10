# Metrics & Stability Analysis - Complete Guide

## Where Metrics Are Computed

### Phase 1: Sequential Execution
**File**: `turing_bench/cli.py` (lines 256-402)

```python
# Extract from sequential runner results
ttft_values = [r.ttft_ms for r in successful]
latency_values = [r.total_time_ms for r in successful]

# Call helper function to compute all metrics
metrics = _compute_metrics(latency_values, ttft_values)
```

**Metrics Computed**:
```python
{
    "mean_latency_ms": 120.5,
    "p50_latency_ms": 118.0,
    "p95_latency_ms": 180.2,
    "p99_latency_ms": 220.5,
    "mean_ttft_ms": 45.0,
    "p50_ttft_ms": 44.0,
    "p95_ttft_ms": 60.0,
    "cv_percent": 8.3,  # Coefficient of Variation
}
```

---

### Phase 2: Concurrent Workload
**File**: `turing_bench/cli.py` (lines 403-450)

```python
# Extract from concurrent runner results
latencies = [r.total_time_ms for r in successful]
ttft_values = [r.ttft_ms for r in successful]

# Same function used
metrics = _compute_metrics(latencies, ttft_values)
```

**Metrics Computed**: (Same as Phase 1)

---

### Phase 3: Sweep (Optional)
**File**: `turing_bench/runner/sweep.py`

```python
# Each concurrency level gets its own metrics
sweep_results = {
    1: {
        "avg_latency_ms": 120.0,
        "p95_latency_ms": 150.0,
        "throughput_rps": 8.3,
    },
    64: {
        "avg_latency_ms": 450.0,
        "p95_latency_ms": 600.0,
        "throughput_rps": 8.5,
    },
}
```

---

## Where Stability Metrics Are (Ready to Use)

### 1. Drift Detection
**File**: `turing_bench/stats/drift.py`

```python
from turing_bench.stats.drift import detect_drift

latencies = [...]  # 500 concurrent measurements
result = detect_drift(latencies, threshold_percent=5.0)

# Returns:
{
    "drift_percent": 3.2,        # Second half mean vs first half mean
    "has_drift": False,          # True if > threshold
    "first_half_mean": 118.0,
    "second_half_mean": 121.8,
    "message": "Performance degradation: +3.2%",
}
```

**Detects**: Thermal throttling, memory fragmentation, system degradation over time

---

### 2. Spike Detection
**File**: `turing_bench/stats/spike.py`

```python
from turing_bench.stats.spike import detect_spikes

latencies = [...]  # 500 concurrent measurements
result = detect_spikes(latencies, multiplier=2.5, max_spike_percent=5.0)

# Returns:
{
    "spike_count": 2,            # Number of outliers
    "spike_percent": 0.4,        # 2/500 = 0.4%
    "has_spikes": False,         # True if > max_spike_percent
    "spike_indices": [127, 342], # Which requests were spikes
    "median": 120.0,
    "spike_threshold": 300.0,    # median * multiplier
    "message": "Detected 2 spikes (0.4%)",
}
```

**Detects**: Background processes, OS hiccups, network glitches, outlier requests

---

### 3. Distribution Analysis
**File**: `turing_bench/stats/distribution.py`

```python
from turing_bench.stats.distribution import analyze_distribution

latencies = [...]  # 500 concurrent measurements
result = analyze_distribution(latencies)

# Returns:
{
    "p50": 118.0,
    "p95": 180.2,
    "p99": 220.5,
    "mean": 120.5,
    "p99_p95_ratio": 1.22,       # Fat tail indicator
    "is_fat_tail": False,        # True if ratio > 1.5
    "is_right_skewed": False,    # True if median < mean
    "message": "P99/P95 ratio: 1.22x",
}
```

**Detects**: Fat tail distribution (occasional very slow requests), non-normal behavior, asymmetric latency

---

## How to Use Metrics in Code

### Get Metrics After Sequential Phase

```python
from turing_bench.cli import _compute_metrics

# After running sequential phase
sequential_results = [...]  # List of SequentialRunResult
latencies = [r.total_time_ms for r in sequential_results]
ttft_values = [r.ttft_ms for r in sequential_results]

metrics = _compute_metrics(latencies, ttft_values)
cv = metrics["cv_percent"]

# Decision: Should we continue?
if cv > 10:
    print("⚠ Results unreliable (CV > 10%), recommend stabilizing system")
    # TODO: Add early stopping here
```

### Get Stability Metrics After Concurrent Phase

```python
from turing_bench.stats.drift import detect_drift
from turing_bench.stats.spike import detect_spikes
from turing_bench.stats.distribution import analyze_distribution

concurrent_results = [...]  # List of ConcurrentRunResult
latencies = [r.total_time_ms for r in concurrent_results]

# Compute all stability metrics
drift = detect_drift(latencies)
spikes = detect_spikes(latencies)
distribution = analyze_distribution(latencies)

# Use in report
if drift["has_drift"]:
    print(f"⚠ {drift['message']}")
if spikes["has_spikes"]:
    print(f"⚠ {spikes['message']}")
if distribution["is_fat_tail"]:
    print(f"⚠ Fat tail detected: P99/P95 ratio {distribution['p99_p95_ratio']:.2f}x")
```

---

## Complete Metric Flow in CLI

### Current (What's Implemented)

```
cli.py run() command
  ↓
PHASE 1: Sequential
  ├─ Run 50 times
  ├─ Compute metrics via _compute_metrics()
  │  └─ P50/P95/P99, TTFT, CV
  ├─ Validate via ValidityLayer
  └─ Store in results["sequential"][scenario]

PHASE 2: Concurrent
  ├─ Run 500 requests at fixed RPS
  ├─ Compute metrics via _compute_metrics()
  │  └─ P50/P95/P99, TTFT, CV
  └─ Store in results["workload"][scenario]

PHASE 3: Sweep (optional)
  ├─ Increase concurrency levels
  ├─ Compute metrics per level
  └─ Store in results["sweep"][scenario]

Save baseline/candidate JSON
```

### Next (Recommended Enhancement)

```
cli.py run() command
  ↓
PHASE 1: Sequential
  ├─ Run 50 times
  ├─ Compute metrics + CV
  ├─ Validate via ValidityLayer
  ├─ Check CV → ⚠ If CV > 10%, warn user or STOP ← NEW
  └─ Store in results["sequential"][scenario]

PHASE 2: Concurrent (only if Phase 1 passed)
  ├─ Run 500 requests
  ├─ Compute metrics
  ├─ Compute stability metrics ← NEW
  │  ├─ Drift detection
  │  ├─ Spike detection
  │  └─ Distribution analysis
  └─ Store in results["workload"][scenario]

Report Output ← ENHANCED
├─ VALIDITY GATE
├─ PERFORMANCE METRICS
├─ STABILITY ANALYSIS ← NEW SECTION
│  ├─ CV assessment
│  ├─ Drift: {drift_percent}
│  ├─ Spikes: {spike_count}/{total}
│  └─ Distribution: P99/P95 = {ratio}
└─ RECOMMENDATIONS
```

---

## Integration Checklist

### ✅ Already in Code
- [x] `_compute_metrics()` - Computes P50/P95/P99, TTFT, CV
- [x] `drift.py` - Drift detection module
- [x] `spike.py` - Spike detection module
- [x] `distribution.py` - Distribution analysis module
- [x] Tests for all three modules (14 tests)

### ⏳ Ready to Integrate (Next Steps)

```python
# In turing_bench/report/formatter.py, add:

def format_stability_section(metrics, latencies):
    """Format stability metrics for report."""
    from turing_bench.stats.drift import detect_drift
    from turing_bench.stats.spike import detect_spikes
    from turing_bench.stats.distribution import analyze_distribution

    drift = detect_drift(latencies)
    spikes = detect_spikes(latencies)
    distribution = analyze_distribution(latencies)

    output = []
    output.append("STABILITY ANALYSIS")
    output.append("─" * 50)
    output.append(f"  CV: {metrics['cv_percent']:.1f}%",
                  color=get_cv_color(metrics['cv_percent']))
    output.append(f"  Drift: {drift['drift_percent']:+.1f}%")
    output.append(f"  Spikes: {spikes['spike_count']} / {len(latencies)}")
    output.append(f"  P99/P95 ratio: {distribution['p99_p95_ratio']:.2f}x")

    return "\n".join(output)

def get_cv_color(cv_percent):
    if cv_percent <= 5:
        return "green"
    elif cv_percent <= 10:
        return "yellow"
    else:
        return "red"
```

### ⏳ Optional: CV-Based Early Stopping

```python
# In cli.py run() command, after Phase 1:

if metrics["cv_percent"] > 10:
    click.secho("⚠ Sequential CV too high (>10%)", fg="red")
    click.secho("Results unreliable. Recommendations:", fg="yellow")
    click.echo("  1. Check thermal throttling (check GPU temp)")
    click.echo("  2. Check background processes (top/Task Manager)")
    click.echo("  3. Try again on quieter system")
    # Option A: STOP here
    sys.exit(1)
    # Option B: CONTINUE but mark as noisy
```

---

## Test Coverage for Metrics

### Stability Analysis Tests
**File**: `tests/test_stability_analysis.py`

```
✅ Drift Detection (4 tests)
   - test_no_drift
   - test_positive_drift
   - test_negative_drift
   - test_minimal_samples

✅ Spike Detection (4 tests)
   - test_no_spikes
   - test_single_spike
   - test_multiple_spikes
   - test_spike_threshold_customizable

✅ Distribution Analysis (4 tests)
   - test_normal_distribution
   - test_fat_tail_distribution
   - test_percentile_calculations
   - test_minimal_samples

✅ Integration Tests (2 tests)
   - test_stable_benchmark_run
   - test_problematic_benchmark_run

Total: 14 tests, all passing
```

---

## Summary

**What's Computed**:
- ✅ P50/P95/P99 latency
- ✅ TTFT metrics (time-to-first-token)
- ✅ CV (coefficient of variation)
- ✅ Drift (thermal/system degradation)
- ✅ Spikes (outliers)
- ✅ Distribution (fat tail)

**Where It's Stored**:
```
results["sequential"][scenario]["metrics"] = {...}
results["workload"][scenario]["metrics"] = {...}
+ stability metrics ready to use from individual modules
```

**What's Missing**:
- CV-based early stopping logic (stop Phase 2 if Phase 1 is too noisy)
- Stability section in final report output
- Recommendations display

**Next Step**: Add CV check between Phase 1 and Phase 2 to implement your variance control flow.
