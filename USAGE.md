# Turing LLM Benchmark — Complete CLI Reference

A production benchmark for LLM serving systems. Validates correctness with a 4-layer validity gate, then measures performance under concurrent load.

---

## Quick Start (30 seconds)

### 1. Start your LLM service

```bash
# Example: Start llama.cpp locally
docker-compose up -d
# Or start vLLM, Ollama, etc. — any OpenAI-compatible endpoint
```

### 2. Create a baseline (run once, keep forever)

```bash
python benchmark.py baseline \
  --endpoint http://localhost:9000 \
  --model qwen2.5-7b \
  --hardware cpu
```

Saves: `baselines/qwen2.5-7b_cpu_2026-03-12_baseline.json`

### 3. Optimize your service

(Quantization, batching, model tuning, etc.)

### 4. Measure after optimization (auto-compares to baseline)

```bash
python benchmark.py candidate \
  --endpoint http://localhost:9000 \
  --model qwen2.5-7b \
  --hardware cpu
```

Shows: improvement/regression % vs baseline

---

## Common Workflows

### Workflow 1: New Hardware Setup

```bash
# Create baseline for this hardware tier
python benchmark.py baseline \
  --endpoint http://my-a100-server:8000 \
  --model qwen2.5-7b \
  --hardware a100

# Results saved to: baselines/qwen2.5-7b_a100_2026-03-12_baseline.json
# Share this file with your team — it's the golden reference
```

### Workflow 2: Quick Iteration During Development

```bash
# Fast smoke test (lower concurrency, fewer requests)
python benchmark.py candidate \
  --endpoint http://localhost:9000 \
  --model qwen2.5-7b \
  --hardware cpu \
  --rps 4 \
  --requests 100
```

Runs in ~5 minutes instead of 40 minutes.

### Workflow 3: Skip Memory-Intensive Scenarios

```bash
# Avoid long_context_v1 on memory-constrained hardware
python benchmark.py baseline \
  --endpoint http://localhost:9000 \
  --model qwen2.5-7b \
  --hardware cpu \
  --scenarios control_prompt_v1 \
  --scenarios small_prompt_v1 \
  --scenarios large_prompt_v1
```

### Workflow 4: Capacity Analysis (Saturation Curve)

```bash
# Include optional concurrency sweep
python benchmark.py candidate \
  --endpoint http://localhost:9000 \
  --model qwen2.5-7b \
  --hardware a100 \
  --sweep
```

Measures throughput at concurrency levels: 1, 2, 4, 8, 16, 32, 64.
Identifies saturation point.

### Workflow 5: A/B Optimization Comparison

```bash
# Create baseline on version A
python benchmark.py baseline \
  --endpoint http://localhost:9000 \
  --model qwen2.5-7b \
  --hardware a100

# Deploy version B
# ... apply optimization ...

# Compare against A
python benchmark.py candidate \
  --endpoint http://localhost:9000 \
  --model qwen2.5-7b \
  --hardware a100

# Report shows: P95 latency improvement/regression, stability changes
```

### Workflow 6: List and Manage Baselines

```bash
# See all baselines for a hardware setup
python benchmark.py list --stack-id qwen2.5-7b_a100

# Promote a successful candidate to be the new baseline
python benchmark.py promote baselines/qwen2.5-7b_a100_2026-03-12_candidate.json
```

---

## Full CLI Reference

### Main Commands

#### `baseline` — Establish golden reference

```bash
python benchmark.py baseline [OPTIONS]
```

**What it does:**
1. Runs all 4 scenarios sequentially (validity gate)
2. Runs all 4 scenarios concurrently (performance measurement)
3. Saves immutable baseline file

**Options:**
- `--endpoint` (required): LLM service URL (e.g., `http://localhost:9000`)
- `--model` (required): Model name (e.g., `qwen2.5-7b`, `llama2-70b`)
- `--hardware` (required): Hardware identifier (e.g., `cpu`, `a100`, `xeon`, `macos`)
- `--scenarios` (optional): Run only specific scenarios (can be used multiple times)
- `--sweep`: Include optional concurrency sweep (saturation analysis)

**Example:**
```bash
python benchmark.py baseline \
  --endpoint http://localhost:9000 \
  --model qwen2.5-7b \
  --hardware a100 \
  --scenarios small_prompt_v1 \
  --scenarios large_prompt_v1
```

---

#### `candidate` — Measure after optimization

```bash
python benchmark.py candidate [OPTIONS]
```

**What it does:**
1. Loads pinned baseline from disk (never compares against fresh run)
2. Runs all 4 scenarios (same as baseline)
3. Compares metrics against baseline
4. Saves candidate file with deltas

**Options:**
- `--endpoint` (required): Same as baseline
- `--model` (required): Same as baseline (must match baseline)
- `--hardware` (required): Same as baseline (must match baseline)
- `--rps` (optional): Requests per second (default: 16)
- `--requests` (optional): Total concurrent requests (default: 500)
- `--scenarios` (optional): Run only specific scenarios
- `--sweep`: Include saturation analysis

**Example:**
```bash
# Standard comparison
python benchmark.py candidate \
  --endpoint http://localhost:9000 \
  --model qwen2.5-7b \
  --hardware a100

# Fast iteration (low concurrency)
python benchmark.py candidate \
  --endpoint http://localhost:9000 \
  --model qwen2.5-7b \
  --hardware a100 \
  --rps 4 \
  --requests 50

# With capacity analysis
python benchmark.py candidate \
  --endpoint http://localhost:9000 \
  --model qwen2.5-7b \
  --hardware a100 \
  --sweep
```

---

#### `list` — View baseline inventory

```bash
python benchmark.py list [OPTIONS]
```

**What it does:**
Lists all saved baselines and candidate files.

**Options:**
- `--stack-id` (optional): Filter by stack ID (e.g., `qwen2.5-7b_a100`)

**Example:**
```bash
# All baselines and candidates
python benchmark.py list

# Only for this hardware+model
python benchmark.py list --stack-id qwen2.5-7b_a100
```

**Output:**
```
BASELINE  qwen2.5-7b_a100_2026-03-10_baseline.json
BASELINE  qwen2.5-7b_cpu_2026-03-05_baseline.json
CANDIDATE qwen2.5-7b_a100_2026-03-12_candidate.json
```

---

#### `promote` — Promote candidate to baseline

```bash
python benchmark.py promote <candidate_file>
```

**What it does:**
Moves a candidate file to baseline status (renames `_candidate` → `_baseline`).

**Options:**
- `candidate_file` (required): Path to candidate JSON

**Example:**
```bash
python benchmark.py promote baselines/qwen2.5-7b_a100_2026-03-12_candidate.json

# Result: qwen2.5-7b_a100_2026-03-12_baseline.json
```

---

### Global Options (All Commands)

None — all options are command-specific.

---

## Understanding the Report

### VALIDITY GATE

```
VALIDITY GATE
────────────────────────────────────────────────────────────────────
  control_prompt_v1              PASS
  large_prompt_v1                PASS
  long_context_v1                PASS
  small_prompt_v1                PASS
```

Each scenario must **PASS** validity checks before concurrent phase runs.
- **PASS**: Output is correct (semantic similarity ≥ 0.92, sanity checks)
- **WARN**: Minor issues (non-determinism on control prompt)
- **FAIL**: Output is wrong → concurrent phase skipped

---

### PERFORMANCE METRICS

```
PERFORMANCE METRICS (concurrent phase)
────────────────────────────────────────────────────────────────────
  Scenario               P95        P99       TTFT      CV      ERR
  control_prompt_v1    2316ms     2890ms      0.5ms   79.6%    0.0%
  large_prompt_v1      FAILED (no concurrent data)
  long_context_v1      6918ms     7600ms      0.5ms   19.7%    0.0%
  small_prompt_v1      6403ms     7100ms      0.5ms   36.4%    2.1%
```

**Columns:**
- **Scenario**: Scenario name
- **P95**: 95th percentile latency (SLA-relevant)
- **P99**: 99th percentile latency (tail behavior)
- **TTFT**: Time-to-first-token (latency before first output)
- **CV**: Coefficient of variation (stability, lower is better)
- **ERR**: Error rate (% of requests that failed)

**What healthy looks like:**
- P95 < 500ms on modern GPU
- P95 < 2000ms on CPU
- CV < 15% (consistent performance)
- ERR = 0.0% (no timeouts/failures)

---

### COMPARISON vs BASELINE

```
COMPARISON vs BASELINE
────────────────────────────────────────────────────────────────────
  Scenario               P95 latency        TTFT            CV
  control_prompt_v1      +662.7% worse      +2742% worse    +113% worse
  small_prompt_v1        +513.3% worse      +54.0% worse    +186% worse
  large_prompt_v1        (no concurrent data)
  long_context_v1        +19.3% worse       -5.0% better    -8.2% better
```

**Interpretation:**
- **Negative % = improvement** (faster/more stable)
- **Positive % = regression** (slower/less stable)
- **Colors**: Green (better), Red (worse), White (same)

---

### FILES SAVED

```
FILES SAVED
────────────────────────────────────────────────────────────────────
  qwen2.5-7b_a100_2026-03-12_candidate.json   ← this run
  qwen2.5-7b_a100_2026-03-10_baseline.json    ← reference
```

Both files are saved to `baselines/` directory:
- **Baseline**: Reference metrics (pinned, immutable)
- **Candidate**: Latest run (can be promoted to baseline)

---

## Interpreting Results

### Good Signs
- Validity Gate: All PASS ✓
- P95 latency stable (within 10% of baseline)
- CV < 15% (consistent behavior)
- No errors (ERR = 0.0%)
- Improvement % negative (faster than baseline)

### Warning Signs
- CV > 20% (high variance, system instability)
- ERR > 5% (requests timing out, server under stress)
- large_prompt_v1 or long_context_v1 concurrent fails (memory issue)
- P95 latency doubled (optimization broke something)

### Failure Cases
- Any scenario FAIL on validity gate → output is semantically wrong
- All concurrent requests timeout → server overloaded
- TTFT regressed 10× → first-token generation bottleneck

---

## Stack ID Convention

Stack IDs follow this pattern:

```
{model}_{hardware}
```

**Examples:**
```
qwen2.5-7b_cpu              # Qwen 7B on CPU
qwen2.5-7b_a100             # Qwen 7B on A100 GPU
llama2-70b_h100             # Llama 2 70B on H100
mistral-7b_xeon_cpu         # Mistral 7B on Xeon CPU
```

**Why this matters:**
- Each hardware tier needs its own baseline
- Baselines are identified by stack ID
- Candidate must match baseline stack ID or you'll get "baseline not found"

---

## Troubleshooting

### Error: "No baseline found for qwen2.5-7b_cpu"

**Cause**: You ran `candidate` before `baseline` for this stack.

**Fix**:
```bash
python benchmark.py baseline \
  --endpoint http://localhost:9000 \
  --model qwen2.5-7b \
  --hardware cpu
```

---

### Error: "All requests failed" on long_context_v1

**Cause**: Server ran out of memory or timed out under concurrent load.

**Fix**: Skip that scenario or reduce concurrency:
```bash
python benchmark.py candidate \
  --endpoint http://localhost:9000 \
  --model qwen2.5-7b \
  --hardware cpu \
  --scenarios small_prompt_v1 \
  --scenarios large_prompt_v1 \
  --rps 4 \
  --requests 100
```

---

### Error: "DeprecationWarning: datetime.utcnow()"

**Cause**: Running on Python 3.12+.

**Fix**: Will be fixed in next release. Safe to ignore for now.

---

### Server responds but benchmark hangs

**Cause**: Server is slow (especially on CPU models).

**Solution**: Increase timeout via environment variable:
```bash
TIMEOUT_SECONDS=120 python benchmark.py baseline ...
```

---

## Advanced Topics

### Running in CI/CD

```bash
# Quick smoke test (5 minutes)
python benchmark.py candidate \
  --endpoint http://staging-server:8000 \
  --model qwen2.5-7b \
  --hardware a100 \
  --rps 4 \
  --requests 50

# Exit code 0 = success, 1 = failure or regression
```

### Comparing Multiple Runs

```bash
# Baseline run 1
python benchmark.py baseline --endpoint ... --model qwen2.5-7b --hardware a100

# Candidate run 2
python benchmark.py candidate --endpoint ... --model qwen2.5-7b --hardware a100

# Candidate run 3 (e.g., after another optimization)
python benchmark.py candidate --endpoint ... --model qwen2.5-7b --hardware a100

# View all saved runs
python benchmark.py list --stack-id qwen2.5-7b_a100
```

### Understanding Coefficient of Variation (CV)

CV = std_deviation / mean × 100%

| CV | Interpretation |
|----|----|
| < 10% | Excellent (consistent, predictable) |
| 10-20% | Good (acceptable for production) |
| 20-30% | Caution (system under stress or noisy) |
| > 30% | Poor (high variance, unreliable) |

---

## Observability: Understanding Why Performance Changed

Latency numbers tell you *what* changed (P95 went from 500ms to 600ms) but not *why*. The **Observability Analysis** section automatically appears in every report to reveal root causes through four stability signals:

**Drift** = progressive slowdown over time (memory growth, thermal throttling, resource leak)
**Spikes** = isolated outliers >2.5× median latency (GC pauses, context switches, I/O wait)
**Fat Tail** = P99/P95 ratio >1.5× (occasional very slow requests not captured by P95)
**Bimodal** = two distinct latency populations (mode switching, batching effects, cache hit/miss boundary)

### Example Report

```
OBSERVABILITY ANALYSIS
────────────────────────────────────────────────────────────────────
  control_prompt_v1
      Drift:        No drift detected (+0.3%)
      Spikes:       0 spikes (0.0%)
      Fat tail:     P99/P95 ratio: 1.2×   OK
      Bimodal:      No

  small_prompt_v1
  ⚠   Drift:        +6.2% (progressive slowdown)
  ⚠   Spikes:       2 spikes (4.0%)
  ⚠   Fat tail:     P99/P95 ratio: 1.8×   WARN
      Bimodal:      No
```

**Color coding:** Green = OK, Yellow = warning. If ANY signal fires for a scenario, a ⚠ marker appears.

### What Each Signal Means

| Signal | Threshold | Indicates | Common Cause |
|--------|-----------|-----------|--------------|
| **Drift** | >5% slowdown trend | Progressive degradation | Memory leak, thermal throttle, resource exhaustion |
| **Spikes** | >2.5× median | Intermittent delays | GC pauses, context switches, I/O contention |
| **Fat Tail** | P99/P95 > 1.5× | Occasional outliers | Request queuing, mode switching, batching effects |
| **Bimodal** | Largest gap > 5× median gap | Two distinct populations | Cache hit/miss boundary, routing to different paths |

The raw latency list is saved in the baseline JSON for deeper analysis. See **[OBSERVABILITY.md](OBSERVABILITY.md)** for detailed signal interpretation and debugging.

---

## See Also

- **[SCENARIOS.md](SCENARIOS.md)** — What each scenario measures
- **[OBSERVABILITY.md](OBSERVABILITY.md)** — Stability signals explained (drift, spikes, fat-tail, bimodal)
- **[README.md](README.md)** — Architecture and design
- **[baselines/](baselines/)** — Saved baseline and candidate files
