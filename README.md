# Turing LLM Benchmark

A standalone Python CLI tool for service-level validation and performance testing of LLM endpoints.

## What This Benchmark Does

**The Turing benchmark is the final validation gate**, not the primary measurement tool. The correct workflow is:

1. **Project benchmark** (llama-bench / benchmark_app / vLLM scripts)
   → Guides Artemis on optimization opportunities

2. **Artemis optimizes**

3. **Project benchmark again**
   → Confirms internal improvement

4. **Turing benchmark** ← this tool
   → Validates improvement holds at service level
   → Confirms correctness is preserved
   → Produces the publishable number

If you skip steps 1–3 and run Turing directly, you'll get clean numbers but lose diagnostic signal. **Both layers are necessary.**

## Quick Start

### 1. Install Dependencies

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

> `sentence-transformers` is only required for candidate runs (semantic similarity comparison against a baseline). The first baseline run works without it.

### 2. Start a Model Server

The benchmark works with any OpenAI-compatible endpoint. Examples:

**Ollama (local, native macOS/Linux):**
```bash
# Install: https://ollama.com/download
ollama pull qwen2.5:1.5b
ollama serve   # runs on http://localhost:11434
```

**Ollama via Docker:**
```bash
docker-compose up ollama -d
docker exec turing-ollama ollama pull qwen2.5:1.5b
# endpoint: http://localhost:11434
```

**vLLM, llama.cpp, or any other OpenAI-compatible server** works the same way — just point `--endpoint` at it.

### 3. Run the Benchmark

```bash
# Establish baseline
python benchmark.py baseline \
  --endpoint http://localhost:11434 \
  --model qwen2.5:1.5b \
  --hardware cpu

# Run candidate (compares against pinned baseline)
python benchmark.py candidate \
  --endpoint http://localhost:11434 \
  --model qwen2.5:1.5b \
  --hardware cpu
```

**Common flags:**

| Flag | Description |
|------|-------------|
| `--fast` | Reduced runs for quick iteration (25 sequential, 100 concurrent) |
| `--live` | Rich live dashboard during the concurrent phase |
| `--plots` | ASCII time-series and histogram charts in the report |
| `--sweep` | Optional concurrency sweep for saturation analysis |
| `--rps N` | Override target requests-per-second (default: 16) |
| `--requests N` | Override total concurrent request count (default: 500) |

## Architecture

### Directory Structure

```
turing_bench/
├── scenarios/           # Frozen, versioned scenarios (YAML)
├── adapters/            # Backend-specific SSE format configs
├── runner/              # Sequential and concurrent execution
├── validity/            # Multi-layer correctness checks
├── stats/               # Percentiles, CV, distribution analysis,
│   ├── drift.py         #   latency drift detection
│   ├── spike.py         #   spike detection
│   ├── distribution.py  #   fat-tail and bimodal analysis
│   ├── visualize.py     #   ASCII time-series and histogram charts
│   └── live_dashboard.py#   Rich live terminal dashboard
├── report/              # Report formatting and baseline management
└── docs/                # Conformance guide for backend integration
```

### The 4 Scenarios

All scenarios are frozen, versioned YAML files. Changing a scenario = major version bump.

1. **small_prompt_v1** - Pure serving overhead
   - Input: "What is the capital of Japan?"
   - Output: ~20 tokens
   - Measures: TTFT, scheduling latency

2. **large_prompt_v1** - Prefill throughput stress
   - Input: ~1500 tokens of technical content
   - Output: ~120 tokens
   - Measures: PagedAttention, KV-cache efficiency

3. **long_context_v1** - KV-cache memory and attention scaling
   - Input: ~6500 tokens + factual question
   - Output: ~60 tokens (must appear verbatim in input)
   - Measures: Memory pressure, attention scaling

4. **control_prompt_v1** - Determinism drift detection
   - Input: "What is 144 divided by 12?"
   - Output: "12" (exact match)
   - Measures: Semantic drift across optimizations (fp32 → bf16, etc.)

### Execution Order (Non-Negotiable)

For each scenario:

1. **Sequential warmup** (discarded) - GPU cache init, CUDA graphs, JIT compilation
2. **Sequential runs** ×50 → validity gate (correctness)
3. **Concurrent fixed RPS** ×500 → performance (only if sequential passed)
4. **Concurrent sweep** (optional) → saturation analysis

Sequential first isolates per-request behavior cleanly. Concurrent introduces timing noise that makes correctness checks flaky.

### Validity Layer (4 Stages)

Each stage must pass before the next:

**Layer 1: Sanity** (pure string checks)
- Output is not empty
- Doesn't end abruptly mid-sentence
- Token count within bounds

**Layer 2: Structural** (optional, per scenario)
- JSON validity if prompt requests JSON
- Python syntax if prompt requests code

**Layer 3: Semantic** (all non-control scenarios)
- Embedding-based similarity (sentence-transformers)
- Threshold: similarity ≥ 0.92
- Handles precision changes (fp32 → bf16)

**Layer 4: Exact-match** (control prompt only)
- Direct string equality after whitespace strip
- Warning level (not hard fail) - hardware affects T=0 determinism

### Baseline Pinning

When you run `baseline`:
- Executes all scenarios
- Saves full result to `baselines/{stack_id}_{date}_baseline.json`
- Contains: all 50 raw outputs, all metrics, hardware state, timestamp

When you run `candidate`:
- Loads pinned baseline
- Runs all scenarios
- **Compares against pinned outputs** (never against a fresh run)
- Saves result to `baselines/{stack_id}_{date}_candidate.json`

`stack_id` is the key: `qwen2.5-7b_vllm_a100`. Different hardware = different stack, different baselines.

## Observability

The benchmark includes four latency observability signals surfaced in the report:

| Signal | What it reveals |
|--------|----------------|
| **Drift** | Mean latency rising across sequential runs — indicates memory pressure, thermal throttling, or KV-cache eviction |
| **Spikes** | Isolated requests >2.5× the median — garbage collection, OS scheduling jitter, or network glitches |
| **Fat tails** | P99 ≫ P95 — degraded long requests, attention scaling problems |
| **Bimodal** | Two latency clusters — fast cache-hit path vs. slow cache-miss path |

Use `--plots` to include ASCII time-series and histogram charts inline in the report.

Use `--live` to see a Rich terminal dashboard during the concurrent phase, showing running P50/P95/P99, CV, TTFT, spike count, live histogram, and drift signal as requests complete.

## Backend Conformance

The benchmark measures a **deployed service**. We don't ship backend wrappers.

Instead:

1. **Conformance check** - Pre-flight validation
   ```bash
   python benchmark.py check-conformance \
     --endpoint http://localhost:8000
   ```

2. **Adapters** - Handle SSE format variation (one YAML per backend)
   - vLLM: `choices[0].delta.content`
   - llama.cpp: `choices[0].delta.content`
   - _default.yaml: Fallback for conformant endpoints

3. **Conformance guide** - Backend owners implement against this spec (`docs/conformance_guide.md`)

## Development

### Run Tests

```bash
pytest tests/
```

### Docker Services

```bash
# Start Ollama
docker-compose up ollama -d

# Pull a model into the running container
docker exec turing-ollama ollama pull qwen2.5:1.5b

# Logs
docker-compose logs -f ollama

# Stop
docker-compose down
```

## Performance Metrics

The report shows:

- **Validity Gate**: Pass/fail for each scenario with similarity scores
- **Performance**: TTFT (P50/P95), throughput, latency percentiles
- **Stability**: CV (coefficient of variation), drift detection, spike count
- **Observability Analysis**: Per-scenario drift, spike, fat-tail, and bimodal signals

## References

- **Scenario Design**: See `turing_bench/scenarios/` for exact prompts and thresholds
- **Backend Requirements**: See `docs/conformance_guide.md` for what endpoints must implement
- **Adapter Spec**: See `turing_bench/adapters/` for SSE format configuration

---

**Questions?** Run `python benchmark.py --help` or `python benchmark.py baseline --help` for detailed CLI options.
