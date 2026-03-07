# Turing LLM Benchmark: Three Execution Modes

The benchmark supports three distinct execution modes, each serving a different purpose in the evaluation workflow.

---

## Mode 1: Sequential Execution (Validity Gate)

**Purpose**: Validate correctness and detect regressions before measuring performance.

**How it works**:
- Sends **one request at a time** to the service
- Waits for full response before sending the next request
- Each request runs in isolation, unaffected by batching or scheduling
- Collects: Time-to-first-token (TTFT), output, correctness metrics

**What it measures**:
- Per-request correctness via the 4-layer validity system:
  1. Sanity checks (non-empty, no truncation, length bounds)
  2. Structural checks (JSON/code format if applicable)
  3. Semantic similarity (embedding-based, threshold ≥0.92)
  4. Exact-match checks (control prompts only, temperature=0)
- Regression signals (e.g., whether behavior changed since baseline)

**Failure behavior**:
- If **any validity check fails**, the entire benchmark run stops
- Performance measurements are never reported with broken validity
- This is the "gate" — nothing goes through without correctness

**When to use**:
- Always. This is the primary correctness safeguard.
- On every code change, refactor, or optimization attempt
- Before running concurrent workload testing

**Configuration** (from scenario YAML):
```yaml
warmup: 20           # Warmup runs (discarded)
runs: 50             # Measurement runs
temperature: 0.0     # Deterministic
seed: 42             # Fixed seed for reproducibility
```

**Implementation**: `turing_bench.runner.SequentialRunner`

---

## Mode 2: Concurrent Workload (Performance Measurement)

**Purpose**: Measure real performance metrics under a realistic serving workload.

**How it works**:
- Sends **multiple requests concurrently** at a fixed request-per-second (RPS) rate
- All requests are launched according to a schedule (e.g., 16 RPS = one request every 62.5ms)
- Responses are collected as they arrive (in any order)
- Metrics are aggregated across all requests

**What it measures**:
- **Throughput**: Tokens generated per second across all requests
- **Latency**: Wall-clock time per request (p50, p95, p99)
- **TTFT**: Time to first token under load
- **Stability**: Coefficient of variation (CV ≤5% is reliable)
- **Error rate**: Percentage of failed requests

**Why fixed RPS?**:
- Makes results comparable across runs and backends
- Prevents some systems from being "faster" simply by getting lucky with request ordering
- Simulates realistic serving conditions where requests arrive at a steady rate
- Ensures reproducible benchmarks: baseline vs. candidate comparisons are fair

**Failure behavior**:
- Collects metrics even if some requests fail (records error count)
- Performance is reported but flagged if error rate is significant
- Results are only valid if validity checks from **Sequential mode** passed

**When to use**:
- After Sequential validation passes
- When comparing performance between two implementations
- To measure the impact of an optimization on the deployed system

**Configuration** (from scenario YAML):
```yaml
concurrent:
  rps: 16           # Requests per second
  concurrency: 32   # Max in-flight requests
  num_requests: 500 # Total requests to send
```

**Implementation**: `turing_bench.runner.ConcurrentRunner`

---

## Mode 3: Concurrent Sweep (Capacity Analysis — Optional)

**Purpose**: Explore system capacity and identify saturation point under increasing load.

**How it works**:
- Runs the same scenario **repeatedly at increasing concurrency levels**
- Default levels: [1, 2, 4, 8, 16, 32, 64] concurrent requests
- At each level, observes how throughput and latency change
- Identifies the "knee" where throughput stops scaling and latency rises sharply

**What it measures**:
- How throughput **scales** with concurrency
- How latency **degrades** as load increases
- Where the system reaches saturation
- System capacity (maximum sustained throughput)

**Example output**:
```
Concurrency 1:   50 req/s, P95 latency 20ms
Concurrency 2:   95 req/s, P95 latency 21ms
Concurrency 4:  180 req/s, P95 latency 22ms
Concurrency 8:  350 req/s, P95 latency 25ms
Concurrency 16: 600 req/s, P95 latency 35ms   ← knee point
Concurrency 32: 620 req/s, P95 latency 80ms   ← saturation
Concurrency 64: 610 req/s, P95 latency 150ms  ← degrading
```

**When to use**:
- **Optional** — not required for standard benchmarking
- When doing deep system analysis or capacity planning
- When comparing backends and need to understand scaling limits
- When tuning configuration (e.g., batch size, GPU memory)

**Configuration** (user-specified at runtime):
```python
await sweep_runner.run_scenario_sweep(
    scenario,
    concurrency_levels=[1, 2, 4, 8, 16, 32, 64],
    requests_per_level=50
)
```

**Implementation**: `turing_bench.runner.SweepRunner`

---

## Execution Workflow

### Standard Benchmark Run (Sequential + Concurrent Workload)

```
┌─────────────────────────────────────┐
│ Sequential Execution                │
│ (50 runs per scenario, 1 at a time) │
├─────────────────────────────────────┤
│ ✓ Validity checks pass?             │
│ ✓ Regression signals ok?            │
│ ✓ Control prompt exact-match?       │
└─────────────────────────────────────┘
            │
            ├─ NO → Stop. Report failure.
            │
            └─ YES → Continue
                    ▼
        ┌─────────────────────────────────────┐
        │ Concurrent Workload                 │
        │ (500 requests at fixed RPS)         │
        ├─────────────────────────────────────┤
        │ Measure: throughput, latency, TTFT  │
        │ Report: p50, p95, p99, CV           │
        └─────────────────────────────────────┘
                    │
                    ▼
        ┌─────────────────────────────────────┐
        │ Baseline Comparison                 │
        │ (if baseline exists)                │
        ├─────────────────────────────────────┤
        │ Compare against pinned baseline     │
        │ Report: improvement/regression      │
        └─────────────────────────────────────┘
```

### Deep Analysis Run (Sequential + Sweep)

For capacity planning or detailed system characterization:

```
Sequential (same as above)
    │
    ├─ NO → Stop
    │
    └─ YES → Continue
            ▼
        ┌──────────────────────────────────────┐
        │ Concurrent Sweep                     │
        │ (run scenario at 7 concurrency       │
        │  levels, 50 requests each)           │
        ├──────────────────────────────────────┤
        │ Observe: scaling curve, saturation   │
        │ Report: capacity analysis            │
        └──────────────────────────────────────┘
```

---

## Key Design Principles

### 1. Sequential Validates First
- Prevents performance improvements from breaking correctness
- Correctness is non-negotiable; performance must serve it
- If Sequential fails, the entire run is invalidated

### 2. Concurrent Workload is Primary Performance Metric
- Real-world systems receive concurrent requests
- Fairness: fixed RPS enables true cross-system comparison
- Sequential and Concurrent results **are never averaged or combined**

### 3. Sweep is Optional but Valuable
- Provides insights into system scaling behavior
- Useful for capacity planning and architecture decisions
- Not required for standard "did we improve?" benchmarking

### 4. All Modes Use Streaming
- All requests use `stream: true`
- Enables TTFT measurement
- Reflects real-world LLM serving (where streaming is common)

---

## Typical Results Reporting

### Standard Run
```
Scenario: large_prompt_v1
────────────────────────────────────────
Sequential Validation: ✓ PASS
  - Sanity checks: 50/50 ✓
  - Semantic similarity: avg 0.94 ✓
  - Exact-match (control): 50/50 ✓

Concurrent Workload (500 requests @ 16 RPS):
  - Throughput: 24.5 tok/s
  - P50 Latency: 18ms
  - P95 Latency: 45ms
  - P99 Latency: 120ms
  - Variance (CV): 2.1% (stable)
  - Errors: 0

Comparison vs Baseline:
  - Throughput: ↑ +8.2% ✓
  - Latency (P95): ↑ -12% ✓ (faster)
  - Validity: ↔ same ✓
```

### Capacity Analysis Run
```
Scenario: large_prompt_v1 (Capacity Sweep)
────────────────────────────────────────
Concurrency │ Throughput │ P95 Latency │ Status
──────────────────────────────────────────────
1           │   50 req/s │     20ms    │ baseline
2           │   95 req/s │     21ms    │ scaling
4           │  180 req/s │     22ms    │ scaling
8           │  350 req/s │     25ms    │ scaling
16          │  600 req/s │     35ms    │ peak region
32          │  620 req/s │     80ms    │ saturation ⚠
64          │  610 req/s │    150ms    │ degrading ⚠

Recommendation: Optimal concurrency is 16; beyond 32 capacity is wasted.
```

---

## Implementation Notes for the Team

When extending the benchmark, remember:

- **Sequential** is the validity gate. Always run first.
- **Concurrent Workload** is the primary performance measurement. This is what gets reported in "improvement" claims.
- **Sweep** is exploratory. Optional but valuable for deep analysis.

Each mode is independent:
- Sequential results should not affect Concurrent results
- Concurrent and Sweep both use their own configuration
- Baseline comparisons apply only to Concurrent metrics (not Sequential or Sweep)

---
