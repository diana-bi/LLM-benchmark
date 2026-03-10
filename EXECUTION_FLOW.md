# Turing LLM Benchmark - Execution Flow & Metrics

## Three Execution Modes (All Run Automatically)

```
python -m turing_bench run --endpoint http://localhost:8000 --phase baseline --stack-id mystack
                                            ↓
                    ┌─────────────────────────────────────────┐
                    │   AUTOMATIC EXECUTION (3 phases)        │
                    └─────────────────────────────────────────┘
                                    ↓
         ┌──────────────────────────┴──────────────────────────┐
         ↓                          ↓                          ↓
    PHASE 1              PHASE 2                          PHASE 3
    SEQUENTIAL           CONCURRENT WORKLOAD               SWEEP
    (Mandatory)          (Mandatory)                        (Optional)
    Correctness          Performance                        Capacity
```

---

## PHASE 1: SEQUENTIAL EXECUTION (Correctness Gate)

### What It Does
- Sends **ONE request at a time** (sequential)
- Runs each scenario **50 times** (configurable via scenario YAML)
- **Validates correctness** before moving to performance
- Measures **per-request latency cleanly** (no batching effects)

### Code Location
```
turing_bench/runner/sequential.py
  └─ class SequentialRunner
     └─ async def run_scenario(scenario, warmup_requests=20, num_runs=50)
```

### Process

```
SEQUENTIAL PHASE
├─ Warmup (20 requests, discarded)
│  └─ GPU cache init, CUDA graph capture, JIT compilation
│
└─ Measurement (50 runs, validated)
   ├─ Run 1: Request → Output → ValidityLayer checks
   │         └─ Layer 1: Sanity (empty, length)
   │         └─ Layer 2: Structural (JSON, syntax)
   │         └─ Layer 3: Semantic similarity (embedding)
   │         └─ Layer 4: Exact-match (control only)
   │
   ├─ Run 2: Request → Output → ValidityLayer checks
   │
   ├─ ...
   │
   └─ Run 50: Request → Output → ValidityLayer checks

DECISION POINT:
├─ ANY FAIL layer → STOP HERE, report error
└─ ALL PASS → Continue to Phase 2
```

### Output Collected Per Run

Each run generates a `SequentialRunResult`:

```python
@dataclass
class SequentialRunResult:
    scenario_id: str           # "small_prompt_v1"
    run_number: int            # 1-50
    output: str                # "Tokyo is the capital of Japan..."
    ttft_ms: float             # 45.2 (Time to First Token)
    output_tokens: int         # 45
    total_time_ms: float       # 120.5 (full response time)
    error: str | None = None   # None if success
```

### Where Metrics Go

```
results["sequential"][scenario_name] = {
    "runs": 50,
    "successful": 50,
    "errors": 0,
    "metrics": {
        "mean_ttft_ms": 45.0,
        "p50_ttft_ms": 44.0,
        "p95_ttft_ms": 60.0,
        "mean_latency_ms": 120.5,
        "p50_latency_ms": 118.0,
        "p95_latency_ms": 180.2,
        "p99_latency_ms": 220.5,
        "cv_percent": 8.3,  # Coefficient of Variation
    },
    "raw_outputs": [output1, output2, ..., output50],
}
```

---

## PHASE 2: CONCURRENT WORKLOAD (Performance Measurement)

### What It Does
- Sends **multiple requests simultaneously** at fixed RPS
- Runs **500 requests** at controlled rate (e.g., 16 RPS)
- **Only runs if Phase 1 passed** (validity gate success)
- Measures **throughput and latency under realistic load**

### Code Location
```
turing_bench/runner/concurrent.py
  └─ class ConcurrentRunner
     └─ async def run_scenario(scenario, rps=16, num_requests=500)
```

### Process

```
CONCURRENT WORKLOAD
├─ Fixed RPS Rate Control
│  └─ RPS from adapter config (e.g., 16 RPS for A100)
│  └─ Concurrency auto-calculated (e.g., 32 concurrent tasks)
│
└─ Send 500 requests at controlled rate
   ├─ Request 1,2,3,...,16 start simultaneously (concurrency=32)
   ├─ As requests finish, new ones start (maintain fixed RPS)
   │
   ├─ Request 1: 120ms latency, 45.2ms TTFT
   ├─ Request 2: 115ms latency, 44.8ms TTFT
   ├─ ...
   └─ Request 500: 125ms latency, 46.1ms TTFT

NO VALIDITY CHECKS HERE (already validated in Phase 1)
Focus purely on performance under load
```

### Output Collected Per Request

Each request generates a `ConcurrentRunResult`:

```python
@dataclass
class ConcurrentRunResult:
    scenario_id: str           # "small_prompt_v1"
    request_number: int        # 1-500
    output: str                # Output (not validated again)
    ttft_ms: float             # 45.2
    output_tokens: int         # 45
    total_time_ms: float       # 120.5
    error: str | None = None
```

### Where Metrics Go

```
results["workload"][scenario_name] = {
    "requests": 500,
    "successful": 500,
    "errors": 0,
    "metrics": {
        "mean_ttft_ms": 45.0,
        "p50_ttft_ms": 44.0,
        "p95_ttft_ms": 60.0,
        "mean_latency_ms": 120.5,
        "p50_latency_ms": 118.0,
        "p95_latency_ms": 180.2,
        "p99_latency_ms": 220.5,
        "cv_percent": 8.3,
    },
}
```

---

## PHASE 3: CONCURRENT SWEEP (Optional Capacity Analysis)

### What It Does
- **Gradually increases concurrency** (1, 2, 4, 8, 16, 32, 64)
- Measures latency and throughput **at each level**
- Identifies **saturation point** (where latency spike, throughput plateaus)
- **Optional** (only if `--sweep` flag passed)
- Results **never compared to baseline** (purely exploratory)

### Code Location
```
turing_bench/runner/sweep.py
  └─ class SweepRunner
     └─ async def run_scenario_sweep(scenario, concurrency_levels=[1,2,4...64])
```

### Process

```
SWEEP (OPTIONAL - Only with --sweep flag)
├─ Concurrency 1:   50 requests at concurrency=1
│                   └─ Baseline performance
│
├─ Concurrency 2:   50 requests at concurrency=2
│                   └─ Latency increases? Throughput scales?
│
├─ Concurrency 4:   50 requests at concurrency=4
│
├─ Concurrency 8:   50 requests at concurrency=8
│
├─ ...
│
└─ Concurrency 64:  50 requests at concurrency=64
                    └─ System saturated?

OUTPUT: Curve showing latency vs concurrency
        Helps identify sweet spot and capacity limits
```

### Where Metrics Go

```
results["sweep"][scenario_name] = {
    "concurrency_1": {
        "num_requests": 50,
        "avg_latency_ms": 120.0,
        "p95_latency_ms": 150.0,
        "throughput_rps": 8.3,
    },
    "concurrency_2": {...},
    ...
    "concurrency_64": {
        "num_requests": 50,
        "avg_latency_ms": 450.0,  # Increased!
        "p95_latency_ms": 600.0,  # Saturation!
        "throughput_rps": 8.5,    # Plateaued
    },
}
```

---

## Metrics Collection & Locations

### Metrics Computed (in both Phase 1 & 2)

```
turing_bench/stats/
├─ percentiles.py
│  └─ calculate_percentiles(latencies)
│     └─ Returns: P50, P95, P99, mean, min, max
│
├─ cv.py
│  └─ calculate_cv(latencies)
│     └─ Returns: Coefficient of Variation (%)
│        ├─ ≤ 5% = RELIABLE
│        ├─ 5-10% = NOISY
│        └─ > 10% = UNRELIABLE
│
├─ drift.py  ← NEW
│  └─ detect_drift(latencies)
│     └─ Compares first half vs second half
│        └─ Returns: drift_percent (thermal throttling?)
│
├─ spike.py  ← NEW
│  └─ detect_spikes(latencies)
│     └─ Finds outliers (> median × 2.5)
│        └─ Returns: spike_count, spike_percent
│
└─ distribution.py  ← NEW
   └─ analyze_distribution(latencies)
      └─ Analyzes shape (fat tail?)
         └─ Returns: P99/P95 ratio, skewness
```

### Where Each Metric Lives

```
results = {
    "validity": {
        "small_prompt_v1": {
            "passed": True,
            "severity": "PASS",
            "checks": [...]  ← Layer 1,2,3,4 results
        }
    },

    "sequential": {
        "small_prompt_v1": {
            "metrics": {
                "mean_ttft_ms": 45.0,    ← TTFT
                "p50_ttft_ms": 44.0,
                "p95_ttft_ms": 60.0,
                "mean_latency_ms": 120.5,  ← P50/P95/P99
                "p50_latency_ms": 118.0,
                "p95_latency_ms": 180.2,
                "p99_latency_ms": 220.5,
                "cv_percent": 8.3,       ← CV
            }
        }
    },

    "workload": {
        "small_prompt_v1": {
            "metrics": {
                "mean_ttft_ms": 45.0,
                "p95_latency_ms": 180.2,
                "cv_percent": 8.3,
            }
        }
    },
}

# Stability metrics (ready to use in report)
drift = detect_drift(latencies)           ← drift.py
spikes = detect_spikes(latencies)         ← spike.py
distribution = analyze_distribution(lat)  ← distribution.py
```

---

## Control Flow (Your Diagram)

```
                        ┌─ Sequential Phase
                        │
    run benchmark   ────┤─ Check CV
                        │   ├─ CV ≤ 5%  → GREEN: reliable
                        │   ├─ 5% < CV ≤ 10% → YELLOW: noisy
                        │   └─ CV > 10% → RED: unreliable (STOP)
                        │
                        ├─ Concurrent Workload Phase
                        │
                        ├─ Stabilize system if noisy
                        │
                        ├─ Re-run if needed
                        │
                        └─ Compare reports
                            ├─ significant improvement? → YES
                            └─ No reliable difference? → NO
```

**CURRENTLY IMPLEMENTED**: Phases 1, 2, 3 all work
**TODO**: CV-based early stopping logic

---

## How to Use All Three Modes

```bash
# Just baseline & candidate (Phase 1 + 2)
python -m turing_bench run \
  --endpoint http://localhost:8000 \
  --phase baseline \
  --stack-id mystack

# With optional capacity sweep (Phase 1 + 2 + 3)
python -m turing_bench run \
  --endpoint http://localhost:8000 \
  --phase baseline \
  --stack-id mystack \
  --sweep
```

---

## Summary

| Phase | Mode | Purpose | Requests | Duration | Required? |
|-------|------|---------|----------|----------|-----------|
| 1 | Sequential | Correctness validation | 1 at a time | ~5 min | ✅ YES |
| 2 | Concurrent Workload | Performance measurement | 500 at fixed RPS | ~5-10 min | ✅ YES |
| 3 | Sweep | Capacity analysis | Increasing concurrency | ~10 min | ⏳ Optional |

**All three run automatically.** Phase 3 only if `--sweep` flag is passed.
