# Turing Benchmark CLI - Execution Mode Selection

The CLI provides complete control over benchmark execution through command-line flags.

## Quick Start

```bash
# Standard benchmark (sequential + workload)
turing-bench run --endpoint http://localhost:8000 --adapter llama_cpp

# Check if endpoint is conformant
turing-bench check --endpoint http://localhost:8000 --adapter llama_cpp
```

## Execution Modes

### Sequential Only (Correctness Validation)

```bash
turing-bench run \
  --endpoint http://localhost:8000 \
  --adapter llama_cpp \
  --mode sequential
```

**When to use**:
- Quick correctness check before performance testing
- Debugging validity issues
- Unit testing in CI

**What you get**:
- Validity layer results (sanity, structural, semantic, exact-match)
- Per-request latency and TTFT
- Error detection

### Workload Only (Performance Measurement)

```bash
turing-bench run \
  --endpoint http://localhost:8000 \
  --adapter llama_cpp \
  --mode workload
```

**When to use**:
- After sequential passes
- Measuring performance under realistic load
- Comparing baseline vs candidate system

**What you get**:
- Throughput metrics
- Latency percentiles (P50, P95, P99)
- TTFT under load
- Error rates

### Sweep Mode (Capacity Analysis)

```bash
turing-bench run \
  --endpoint http://localhost:8000 \
  --adapter llama_cpp \
  --mode sweep
```

**When to use**:
- Deep system analysis
- Identifying saturation point
- Capacity planning
- Understanding scaling behavior

**What you get**:
- Per-concurrency-level metrics
- Throughput scaling curve
- Latency degradation curve
- Saturation point identification

### Full (Sequential + Workload) — **Recommended Default**

```bash
turing-bench run \
  --endpoint http://localhost:8000 \
  --adapter llama_cpp \
  --mode full
```

Or omit `--mode` (defaults to `full`):

```bash
turing-bench run \
  --endpoint http://localhost:8000 \
  --adapter llama_cpp
```

**When to use**: Standard benchmark run (most common)

**What you get**:
- Full correctness validation
- Performance metrics under load
- If sequential fails, workload is skipped

---

## Sequential Mode Options

Control how sequential validation runs:

```bash
turing-bench run \
  --endpoint http://localhost:8000 \
  --adapter llama_cpp \
  --mode sequential \
  --seq-warmup 10 \
  --seq-runs 100
```

| Flag | Default | Purpose |
|------|---------|---------|
| `--seq-warmup` | From scenario config | Override warmup count |
| `--seq-runs` | 50 | Number of measurement runs |

---

## Workload Mode Options

Control the concurrent workload test:

```bash
turing-bench run \
  --endpoint http://localhost:8000 \
  --adapter llama_cpp \
  --mode workload \
  --workload-rps 32 \
  --workload-concurrency 64 \
  --workload-requests 1000
```

| Flag | Default | Purpose |
|------|---------|---------|
| `--workload-rps` | 16 | Requests per second |
| `--workload-concurrency` | 32 | Max in-flight requests |
| `--workload-requests` | 500 | Total requests to send |

### Examples

**Heavy load (stress test)**:
```bash
turing-bench run \
  --endpoint http://localhost:8000 \
  --adapter llama_cpp \
  --workload-rps 100 \
  --workload-concurrency 128 \
  --workload-requests 2000
```

**Light load (baseline)**:
```bash
turing-bench run \
  --endpoint http://localhost:8000 \
  --adapter llama_cpp \
  --workload-rps 4 \
  --workload-concurrency 8 \
  --workload-requests 100
```

---

## Sweep Mode Options

Control capacity analysis:

```bash
turing-bench run \
  --endpoint http://localhost:8000 \
  --adapter llama_cpp \
  --mode sweep \
  --sweep-levels 1,2,4,8,16,32 \
  --sweep-per-level 50
```

| Flag | Default | Purpose |
|------|---------|---------|
| `--sweep-levels` | 1,2,4,8,16,32,64 | Concurrency levels to test (comma-separated) |
| `--sweep-per-level` | 50 | Requests per level |

### Examples

**Fine-grained sweep (find exact saturation)**:
```bash
turing-bench run \
  --endpoint http://localhost:8000 \
  --adapter llama_cpp \
  --mode sweep \
  --sweep-levels 1,2,3,4,5,6,7,8,10,12,16,20,24,32
```

**Quick sweep (quick capacity estimate)**:
```bash
turing-bench run \
  --endpoint http://localhost:8000 \
  --adapter llama_cpp \
  --mode sweep \
  --sweep-levels 1,4,16,64
```

---

## Scenario Selection

Run specific scenarios instead of all:

```bash
turing-bench run \
  --endpoint http://localhost:8000 \
  --adapter llama_cpp \
  --scenarios small_prompt_v1 large_prompt_v1
```

Omit to run all 4 scenarios (small_prompt, large_prompt, long_context, control_prompt).

---

## Output Saving

Save results to JSON file:

```bash
turing-bench run \
  --endpoint http://localhost:8000 \
  --adapter llama_cpp \
  --output results.json
```

Omit to print results to stdout.

---

## Complete Example Workflows

### Workflow 1: Standard Benchmark Run

```bash
# Correctness validation + performance measurement
turing-bench run \
  --endpoint http://localhost:8000 \
  --adapter llama_cpp \
  --output results.json
```

### Workflow 2: Quick Validation

```bash
# Fast correctness check only
turing-bench run \
  --endpoint http://localhost:8000 \
  --adapter llama_cpp \
  --mode sequential \
  --seq-runs 10
```

### Workflow 3: Deep Performance Analysis

```bash
# Sequential validation + heavy concurrent load + capacity sweep
turing-bench run \
  --endpoint http://localhost:8000 \
  --adapter llama_cpp \
  --mode full

# Then run sweep for capacity analysis
turing-bench run \
  --endpoint http://localhost:8000 \
  --adapter llama_cpp \
  --mode sweep \
  --sweep-levels 1,2,4,8,16,32,64 \
  --sweep-per-level 100 \
  --output sweep_results.json
```

### Workflow 4: CI Integration

```bash
# Quick pre-commit check (sequential only)
turing-bench run \
  --endpoint http://localhost:8000 \
  --adapter llama_cpp \
  --mode sequential \
  --seq-runs 5 \
  --seq-warmup 2

# Full benchmark on main branch (slow but comprehensive)
turing-bench run \
  --endpoint http://localhost:8000 \
  --adapter llama_cpp \
  --output ci_results.json
```

### Workflow 5: Baseline Establishment

```bash
# High-confidence baseline (many runs)
turing-bench run \
  --endpoint http://localhost:8000 \
  --adapter llama_cpp \
  --seq-runs 100 \
  --workload-requests 2000 \
  --output baseline.json
```

---

## Understanding the Output

### Sequential Results

```json
{
  "sequential": {
    "small_prompt_v1": {
      "runs": 50,
      "errors": 0,
      "mean_ttft_ms": 45.2,
      "mean_latency_ms": 120.5
    }
  }
}
```

- `runs`: Number of successful measurement runs
- `errors`: Count of failed requests (should be 0)
- `mean_ttft_ms`: Average time to first token
- `mean_latency_ms`: Average total latency

### Workload Results

```json
{
  "workload": {
    "large_prompt_v1": {
      "requests": 500,
      "errors": 2,
      "successful": 498,
      "mean_latency_ms": 125.3,
      "p50_latency_ms": 110.0,
      "p95_latency_ms": 180.5,
      "p99_latency_ms": 250.0,
      "mean_ttft_ms": 42.1
    }
  }
}
```

- `requests`: Total requests sent
- `errors`: Failed requests
- `successful`: Completed requests
- `p50_latency_ms`, `p95_latency_ms`, `p99_latency_ms`: Latency percentiles
- `mean_ttft_ms`: Average time to first token under load

### Sweep Results

```json
{
  "sweep": {
    "large_prompt_v1": {
      "levels": [
        {
          "concurrency": 1,
          "num_requests": 50,
          "avg_ttft_ms": 45.0,
          "avg_latency_ms": 120.0,
          "p95_latency_ms": 125.0,
          "throughput_rps": 8.3,
          "error_count": 0
        },
        {
          "concurrency": 16,
          "num_requests": 50,
          "avg_ttft_ms": 48.0,
          "avg_latency_ms": 150.0,
          "p95_latency_ms": 175.0,
          "throughput_rps": 106.7,
          "error_count": 0
        },
        {
          "concurrency": 32,
          "num_requests": 50,
          "avg_ttft_ms": 52.0,
          "avg_latency_ms": 300.0,
          "p95_latency_ms": 400.0,
          "throughput_rps": 110.0,
          "error_count": 5
        }
      ]
    }
  }
}
```

Look for the concurrency level where:
- Throughput stops increasing significantly
- Latency starts rising sharply
- Error rate increases

That's your saturation point.

---

## Common Scenarios

### Scenario 1: Is my optimization safe?

1. Run sequential validation:
   ```bash
   turing-bench run --endpoint http://localhost:8000 --adapter llama_cpp --mode sequential
   ```
   - Check: Do all validity checks pass?

2. Run workload benchmark:
   ```bash
   turing-bench run --endpoint http://localhost:8000 --adapter llama_cpp --mode workload
   ```
   - Compare P95 latency to baseline
   - Check: Did performance improve?

### Scenario 2: What's the saturation point?

```bash
turing-bench run --endpoint http://localhost:8000 --adapter llama_cpp --mode sweep --output sweep.json
```

Look at the results JSON and find where throughput stops growing.

### Scenario 3: Did I break something?

```bash
turing-bench run --endpoint http://localhost:8000 --adapter llama_cpp --mode sequential --seq-runs 20
```

If any validity check fails, you broke something.

---
