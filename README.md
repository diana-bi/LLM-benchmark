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

### 1. Start the llama.cpp Service

```bash
# Build and start the service
docker-compose up -d llama-cpp

# Verify it's running (wait for healthy status)
docker-compose ps

# Check conformance
python turing_bench.py check-conformance-cmd --endpoint http://localhost:8000
```

You'll need a GGUF model. Download one and place it in `models/model.gguf`:

```bash
# Example: Download a Qwen model
mkdir -p models
# Download your GGUF file to models/model.gguf
```

### 2. Run the Benchmark

```bash
# Run baseline (saves immutable baseline file)
python -m turing_bench run \
  --endpoint http://localhost:8000 \
  --phase baseline \
  --stack-id qwen2.5-7b_llama_cpp

# Compare against baseline (loads pinned baseline, compares)
python -m turing_bench run \
  --endpoint http://localhost:8000 \
  --phase candidate \
  --stack-id qwen2.5-7b_llama_cpp
```

## Architecture

### Directory Structure

```
turing_bench/
├── scenarios/           # Frozen, versioned scenarios (YAML)
├── adapters/           # Backend-specific SSE format configs
├── runner/             # Sequential and concurrent execution
├── validity/           # Multi-layer correctness checks
├── stats/              # Percentiles, CV, distribution analysis
├── report/             # Report formatting and baseline management
└── docs/               # Conformance guide for backend integration
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

When you run `--phase baseline`:
- Executes all scenarios
- Saves full result to `baselines/{stack_id}_{date}_baseline.json`
- Contains: all 50 raw outputs, all metrics, hardware state, timestamp

When you run `--phase candidate`:
- Loads pinned baseline
- Runs all scenarios
- **Compares against pinned outputs** (never against a fresh run)
- Saves result to `baselines/{stack_id}_{date}_candidate.json`

`stack_id` is the key: `qwen2.5-7b_vllm_a100`. Different hardware = different stack, different baselines.

## Backend Conformance

The benchmark measures a **deployed service**. We don't ship backend wrappers.

Instead:

1. **Conformance check** - Pre-flight validation
   ```bash
   python turing_bench.py check-conformance-cmd --endpoint http://localhost:8000
   ```

2. **Adapters** - Handle SSE format variation (one YAML per backend)
   - vLLM: `choices[0].delta.content`
   - llama.cpp: `choices[0].delta.content`
   - _default.yaml: Fallback for conformant endpoints

3. **Conformance guide** - Backend owners implement against this spec (`docs/conformance_guide.md`)

## Development

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run Tests

```bash
pytest tests/
```

### Docker Commands

```bash
# Start services
docker-compose up -d

# Logs
docker-compose logs -f llama-cpp
docker-compose logs -f benchmark

# Run benchmark inside container
docker exec turing-benchmark python turing_bench.py run-benchmark \
  --endpoint http://llama-cpp:8000 \
  --adapter llama_cpp

# Stop services
docker-compose down
```

## Performance Metrics

The report shows:

- **Validity Gate**: Pass/fail for each scenario with similarity scores
- **Performance**: TTFT (P50/P95), throughput, latency percentiles
- **Stability**: CV (coefficient of variation), drift detection

## References

- **Scenario Design**: See `turing_bench/scenarios/` for exact prompts and thresholds
- **Backend Requirements**: See `docs/conformance_guide.md` for what endpoints must implement
- **Adapter Spec**: See `turing_bench/adapters/` for SSE format configuration

---

**Questions?** See `--help` for detailed CLI options.
