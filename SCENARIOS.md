# Turing LLM Benchmark Scenarios (v1 - Frozen)

All scenarios are **frozen** at version 1. Changing a scenario = major version bump. This document describes what each scenario measures and what "healthy" performance looks like.

---

## Scenario 1: control_prompt_v1 — Determinism & Semantic Drift

**Purpose**: Detect semantic drift when optimizations change precision (fp32 → bf16, quantization, etc.)

**Prompt**: "What is 144 divided by 12? Answer with only the number."

**Expected Output**: `"12"` (exact match, 1 token)

**Measurement**: Exact-match correctness only (not a performance scenario)

**Why This Matters**:
- Numerical precision changes often show up as different outputs at T=0
- A model with `bf16` quantization might output `"12.0"` instead of `"12"`
- Control prompt catches these semantic drift issues before they propagate to user-facing features

**Healthy P95 (baseline)**:
- Not measured (sequential only, no concurrent phase)
- Just verify it passes exact-match validation

**Failure Modes**:
- Output is empty → model didn't generate anything
- Output is `"11"` or `"13"` → model has semantic drift issue (alert + warning)
- Output is `"12.0"` → quantization or precision change (warning level)

---

## Scenario 2: small_prompt_v1 — Pure Serving Overhead

**Purpose**: Measure baseline latency and TTFT with minimal model computation

**Prompt**: "What is the capital of Japan?"

**Expected Output**: ~20 tokens describing Tokyo

**Token Range**: Input ~15 tokens, Output ~20 tokens

**Measurement**:
- Sequential: 50 runs → validity gate (semantic similarity ≥ 0.92)
- Concurrent: 500 requests @ 16 RPS → P95 latency, TTFT, CV

**Why This Matters**:
- Minimal GPU/CPU computation (quick to respond)
- Isolates serving infrastructure overhead
- Ideal for measuring scheduling latency, request queuing, GPU context switching
- Regression here → problem in the service layer, not the model

**Healthy P95 by Hardware**:
| Hardware | P95 Latency | TTFT | CV |
|----------|-------------|------|------|
| A100 | 50-150ms | 5-15ms | <10% |
| H100 | 30-100ms | 3-10ms | <8% |
| Xeon CPU | 500-1500ms | 50-200ms | <15% |
| Apple M1/M2 | 800-2500ms | 100-300ms | <20% |

**Failure Modes**:
- P95 > 2000ms on GPU → GC pauses, thermal throttling, or network latency
- TTFT > 500ms → model loading issue or first-token generation bottleneck
- CV > 20% → system instability, background load, or resource contention

---

## Scenario 3: large_prompt_v1 — Prefill Throughput Stress

**Purpose**: Measure how efficiently the model handles large prompt inputs (prefill phase)

**Prompt**: ~1000 tokens of HTTP/1.1 protocol technical content

**Expected Output**: ~40 tokens (2-3 sentence summary of the input)

**Token Range**: Input ~1000, Output ~40 tokens

**Measurement**:
- Sequential: 50 runs → validity gate (semantic similarity ≥ 0.92)
- Concurrent: 500 requests @ 16 RPS → P95 latency, CV

**Why This Matters**:
- KV-cache efficiency shows up here
- PagedAttention and attention mask optimizations reduce latency
- Large prefill stress-tests memory bandwidth and attention computation
- Regression here → attention mechanism or KV-cache degradation

**Healthy P95 by Hardware**:
| Hardware | P95 Latency | CV |
|----------|-------------|------|
| A100 | 500-2000ms | <15% |
| H100 | 300-1200ms | <10% |
| Xeon CPU | 3000-8000ms | <20% |
| Apple M1/M2 | 5000-12000ms | <25% |

**Failure Modes**:
- P95 doubles → KV-cache issue or attention mask optimization regressed
- CV > 25% → memory bandwidth saturation, GC pauses, or thermal throttling
- Concurrent phase fails (timeout) → server memory exceeded or queue overflow

---

## Scenario 4: long_context_v1 — KV-Cache Memory & Attention Scaling

**Purpose**: Measure how memory and attention mechanisms scale with context length

**Prompt**: ~1200 tokens of U.S. Constitution text + factual question at end

**Expected Output**: ~30 tokens, must include answer appearing verbatim in the input

**Token Range**: Input ~1200, Output ~30 tokens

**Measurement**:
- Sequential: 50 runs → validity gate (semantic similarity ≥ 0.92 + answer must appear in input)
- Concurrent: 500 requests @ 16 RPS → P95 latency, CV

**Why This Matters**:
- KV-cache is the biggest memory consumer in long context
- Attention computation is O(n²) in context length
- Measures if optimizations (sparse attention, retrieval augmentation) are working
- Regression here → memory fragmentation, OOM, or attention optimization issue

**Healthy P95 by Hardware**:
| Hardware | P95 Latency | CV | Notes |
|----------|-------------|------|-------|
| A100 | 2000-5000ms | <15% | 80GB memory, no issues |
| H100 | 1500-4000ms | <12% | Large HBM, fast attention |
| Xeon CPU | 8000-20000ms | <20% | Thin memory, slow for long context |
| Apple M1/M2 | 10000-30000ms | <25% | Unified memory, CPU-bound attention |

**Failure Modes**:
- Sequential phase passes but concurrent fails → server OOM under parallel load
- All concurrent requests timeout → KV-cache allocation issue
- CV > 30% → memory fragmentation, GC pauses, or thermal throttling
- P95 > 2× baseline → attention recomputation or cache miss pattern

---

## Scenario Relationship & Interpretation

### Sequential Phase Tells You:
- **Correctness**: Is the model producing sensible output?
- **Per-request behavior**: What's the latency in isolation (no interference)?

### Concurrent Phase Tells You:
- **System capacity**: How does the service handle simultaneous requests?
- **Stability**: Does latency remain consistent (low CV)?
- **Saturation point**: When does P95 start degrading?

### Comparing Baselines vs Candidates:
- **Improvement**: Candidate P95 < Baseline P95 → optimization worked
- **Regression**: Candidate P95 > Baseline P95 → something broke
- **Instability**: Candidate CV >> Baseline CV → system under stress or noisy environment

---

## Running Subsets of Scenarios

Use the `--scenarios` flag to run only specific scenarios:

```bash
# Fast check (small prompt only)
python benchmark.py baseline --endpoint ... --model ... --hardware ... \
  --scenarios small_prompt_v1

# Skip memory-intensive scenarios on memory-constrained hardware
python benchmark.py baseline --endpoint ... --model ... --hardware ... \
  --scenarios control_prompt_v1 --scenarios small_prompt_v1

# Run large scenarios only
python benchmark.py baseline --endpoint ... --model ... --hardware ... \
  --scenarios large_prompt_v1 --scenarios long_context_v1
```

---

## Frozen Invariants (Do Not Change)

These properties are **never** changed without a major version bump:

| Invariant | Reason |
|-----------|--------|
| Scenario ID (control_prompt_v1, etc.) | Baselines are identified by scenario ID |
| Prompt text | Semantic meaning must remain constant |
| Expected token count | Helps validate model behavior |
| Seed & Temperature | Reproducibility |
| Min/max length bounds | Sanity checks must be consistent |
| Similarity threshold (0.92) | Prevents false negatives on semantic checks |
| Number of concurrent requests (500) | Stress test level must be consistent |

Changing any of these requires:
1. Version bump (v1 → v2)
2. All new baselines created from scratch
3. Old v1 baselines archived, not deleted
