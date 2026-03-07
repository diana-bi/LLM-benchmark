# Turing Benchmark CLI - API-Level Usage

The Turing benchmark is a **deployed service testing tool**. You point it at an already-running LLM service and it validates correctness plus measures performance.

## Core Concept

The benchmark **always runs three internal phases**:

1. **Sequential Execution** — Correctness validation gate (mandatory)
   - One request at a time, 50 runs per scenario
   - If validity fails: stops immediately, no performance numbers reported

2. **Concurrent Workload** — Performance measurement (primary metric)
   - Multiple concurrent requests at fixed RPS
   - 500 requests per scenario
   - Only runs if sequential validation passes

3. **Optional Sweep** — Capacity analysis (exploratory, off by default)
   - Gradually increases concurrency to find saturation point
   - Run with `--sweep` flag if you want it
   - Results reported separately, never compared to baseline

## Quick Start

### 1. Establish a Baseline (Run Once, Pin Forever)

```bash
turing-bench run \
  --endpoint http://localhost:8000 \
  --adapter llama_cpp \
  --phase baseline \
  --stack-id qwen2.5-7b_vllm_a100
```

This runs all 3 phases, validates correctness, measures performance, and saves results to `baselines/`.

### 2. Measure After Optimization (Compare to Baseline)

```bash
turing-bench run \
  --endpoint http://localhost:8000 \
  --adapter llama_cpp \
  --phase candidate \
  --stack-id qwen2.5-7b_vllm_a100
```

Compares against the pinned baseline. Reports improvement/regression.

### 3. Optional: Include Capacity Analysis

Add `--sweep` to explore system capacity:

```bash
turing-bench run \
  --endpoint http://localhost:8000 \
  --adapter llama_cpp \
  --phase candidate \
  --stack-id qwen2.5-7b_vllm_a100 \
  --sweep
```

---

## CLI Options

### Required Options

| Option | Purpose | Example |
|--------|---------|---------|
| `--endpoint` | LLM service URL | `http://localhost:8000` |
| `--adapter` | Backend type (SSE format) | `llama_cpp`, `vllm`, `ollama`, `openvino`, `_default` |
| `--stack-id` | Unique hardware/software identifier | `qwen2.5-7b_vllm_a100`, `qwen2.5-7b_openvino_xeon` |

### Phase Selection

| Option | Meaning |
|--------|---------|
| `--phase baseline` | Establish reference (first run, pin forever) |
| `--phase candidate` | Measure after optimization (default if omitted) |

### Optional Options

| Option | Purpose | Default |
|--------|---------|---------|
| `--scenarios` | Run specific scenarios (space-separated) | All scenarios |
| `--warmup-requests` | Override warmup count | From adapter config |
| `--sweep` | Enable capacity sweep phase | Disabled |
| `--output` | Save results to JSON file | Print to stdout |

### Examples

**Specific scenarios only:**
```bash
turing-bench run \
  --endpoint http://localhost:8000 \
  --adapter llama_cpp \
  --phase candidate \
  --stack-id qwen2.5-7b_vllm_a100 \
  --scenarios small_prompt_v1 large_prompt_v1
```

**Custom warmup (override adapter config):**
```bash
turing-bench run \
  --endpoint http://localhost:8000 \
  --adapter llama_cpp \
  --phase candidate \
  --stack-id qwen2.5-7b_vllm_a100 \
  --warmup-requests 5
```

**Save results to file:**
```bash
turing-bench run \
  --endpoint http://localhost:8000 \
  --adapter llama_cpp \
  --phase candidate \
  --stack-id qwen2.5-7b_vllm_a100 \
  --output results_2026-03-07.json
```

---

## Pre-Flight Check (Optional)

Before running the full benchmark, check if your endpoint is conformant:

```bash
turing-bench check \
  --endpoint http://localhost:8000 \
  --adapter llama_cpp
```

Returns:
- `✓ Endpoint is conformant` — ready to benchmark
- `✗ Endpoint is not conformant` — endpoint has issues, fix first

---

## Understanding the Output

### Sequential Phase

```json
{
  "sequential": {
    "small_prompt_v1": {
      "runs": 50,
      "successful": 50,
      "errors": 0,
      "mean_ttft_ms": 45.2,
      "mean_latency_ms": 120.5,
      "raw_outputs": ["...50 strings..."]
    }
  }
}
```

- **runs**: Total measurement runs
- **successful**: Requests that completed
- **errors**: Failed requests (should be 0)
- **mean_ttft_ms**: Average time to first token
- **mean_latency_ms**: Average total latency
- **raw_outputs**: Full outputs (used for semantic similarity check against baseline)

If **errors > 0** or any validity check fails: concurrent phase is skipped.

### Concurrent Workload Phase

```json
{
  "workload": {
    "large_prompt_v1": {
      "requests": 500,
      "successful": 498,
      "errors": 2,
      "mean_latency_ms": 125.3,
      "p50_latency_ms": 110.0,
      "p95_latency_ms": 180.5,
      "p99_latency_ms": 250.0,
      "mean_ttft_ms": 42.1
    }
  }
}
```

- **requests**: Total requests sent
- **successful**: Completed requests
- **errors**: Failed requests
- **p50/p95/p99**: Latency percentiles (50th, 95th, 99th percentile)
- **mean_ttft_ms**: Average time to first token under load

### Sweep Phase (Optional)

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
- Throughput stops increasing
- P95 latency rises sharply
- Error rate increases

That's your **saturation point**. For this example: saturation occurs around concurrency=32.

---

## Typical Workflows

### Workflow 1: Establish Baseline

```bash
# Run once, pin forever
turing-bench run \
  --endpoint http://localhost:8000 \
  --adapter llama_cpp \
  --phase baseline \
  --stack-id qwen2.5-7b_vllm_a100 \
  --output baselines/qwen2.5-7b_vllm_a100_baseline.json
```

**What happens:**
1. Sequential runs (50 per scenario) — validates correctness
2. Concurrent workload (500 per scenario) — measures performance
3. Results saved to `baselines/` — **never overwritten**

### Workflow 2: Measure Optimization Impact

```bash
# 1. Do your optimization
# 2. Run candidate benchmark
turing-bench run \
  --endpoint http://localhost:8000 \
  --adapter llama_cpp \
  --phase candidate \
  --stack-id qwen2.5-7b_vllm_a100 \
  --output results_after_optimization.json

# 3. Compare results to baseline
# The tool will load the pinned baseline and show improvement/regression
```

### Workflow 3: Capacity Planning

Find system saturation point:

```bash
turing-bench run \
  --endpoint http://localhost:8000 \
  --adapter llama_cpp \
  --phase baseline \
  --stack-id qwen2.5-7b_vllm_a100 \
  --sweep \
  --output capacity_analysis.json
```

### Workflow 4: CI Integration

Quick validation on every commit:

```bash
# Fast pre-commit check (sequential only, 10 warmup, 10 runs)
turing-bench run \
  --endpoint http://localhost:8000 \
  --adapter llama_cpp \
  --phase candidate \
  --stack-id ci-test \
  --warmup-requests 1 \
  --scenarios small_prompt_v1 control_prompt_v1

# Full baseline on release branches (slow but comprehensive)
turing-bench run \
  --endpoint http://localhost:8000 \
  --adapter llama_cpp \
  --phase baseline \
  --stack-id qwen2.5-7b_vllm_a100 \
  --output release_baseline.json
```

---

## Stack ID Naming Convention

`stack_id` uniquely identifies a hardware/software combination. Use:

```
{model}_{framework}_{hardware}
```

Examples:
- `qwen2.5-7b_vllm_a100` — Qwen 2.5 7B, vLLM, A100 GPU
- `qwen2.5-7b_vllm_rtx3090` — Qwen 2.5 7B, vLLM, RTX 3090 GPU
- `qwen2.5-7b_openvino_xeon` — Qwen 2.5 7B, OpenVINO, Xeon CPU
- `qwen2.5-1.5b_openvino_luna_lake` — Qwen 2.5 1.5B, OpenVINO, Luna Lake CPU
- `deepseek-67b_vllm_2xa100` — DeepSeek 67B, vLLM, 2× A100 GPU

Baselines are stored **per stack**. Never compare baselines across hardware.

---

## Adapter Configuration

Adapters define how the benchmark parses each backend's SSE format.

Built-in adapters:
- `_default` — OpenAI-compatible baseline (works for most)
- `llama_cpp` — llama.cpp specific format
- `vllm` — vLLM specific format
- `ollama` — Ollama specific format
- `openvino` — OpenVINO specific format

Adapter files live in `turing_bench/adapters/` and specify:
- Backend SSE format differences (e.g., which JSON path contains the token)
- RPS and concurrency defaults for this hardware type
- Warmup defaults (GPU vs CPU)

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Benchmark completed successfully |
| `1` | Sequential validation failed; concurrent phase skipped |
| `2` | Setup error (missing adapter, endpoint unreachable) |

---

## Troubleshooting

### "Endpoint is not conformant"

```
turing-bench check --endpoint http://localhost:8000 --adapter llama_cpp
✗ Endpoint is not conformant
```

**Fix**: Ensure the service is running and exposes `/v1/chat/completions` with streaming.

### "All requests failed" in sequential phase

Check:
- Is the endpoint reachable?
- Does it support streaming (`stream: true`)?
- Are there timeouts or errors in the service logs?

### "Sequential validation FAILED" but I want workload results anyway

You can't. The sequential phase is a **mandatory correctness gate**. If it fails:
- There's a problem with the service
- Performance numbers aren't trustworthy
- Fix the issue first, then re-run

### High error rate in concurrent phase

May indicate:
- Service is overloaded at the configured RPS
- Network instability
- Service hanging on certain inputs

Check service logs and try reducing RPS in adapter config.

---

## Advanced: Custom Adapter

To support a new backend, create `turing_bench/adapters/mybackend.yaml`:

```yaml
backend: mybackend
hardware_type: gpu  # gpu or cpu
warmup_default: 20
concurrent:
  rps: 16
  concurrency: 32
  num_requests: 500
sse_content_path: "choices[0].delta.content"  # JSON path to token
done_signal: "[DONE]"
```

Then:
```bash
turing-bench run --endpoint http://localhost:8000 --adapter mybackend ...
```

---
