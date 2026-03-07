# Universal Benchmark Design

The Turing benchmark is **truly generic** — it works with any OpenAI-compatible LLM service without backend-specific code or configuration.

## One Adapter Works for Everything

Instead of per-backend adapters (llama_cpp.yaml, vllm.yaml, ollama.yaml, etc.), there is **one universal adapter** (`_default.yaml`) that:

1. **Tries the primary SSE content path first** (OpenAI standard format)
2. **Auto-detects format variations** — if the primary path doesn't work, tries fallback paths
3. **Supports multiple end-of-stream signals** — different backends use different markers
4. **Gracefully handles all variations** — works for vLLM, llama.cpp, Ollama, OpenVINO, custom servers, anything

## How It Works

### Same Benchmark, Any Backend

```bash
# Works with vLLM
turing-bench run --endpoint http://vllm-server:8000 \
  --phase baseline --stack-id my-model-vllm

# Works with llama.cpp
turing-bench run --endpoint http://llama-cpp-server:9000 \
  --phase baseline --stack-id my-model-llama_cpp

# Works with Ollama
turing-bench run --endpoint http://ollama-server:11434 \
  --phase baseline --stack-id my-model-ollama

# Works with OpenVINO (with wrapper)
turing-bench run --endpoint http://openvino-server:8000 \
  --phase baseline --stack-id my-model-openvino

# Works with any custom server
turing-bench run --endpoint http://my-custom-server:5000 \
  --phase baseline --stack-id my-model-custom
```

**All use the same benchmark logic. No code changes needed.**

## Why This Works

### SSE Format Auto-Detection

The benchmark's SSE parser tries paths in this order:

1. **Primary**: `choices[0].delta.content` (OpenAI format — most servers)
2. **Fallback 1**: `content` (llama.cpp simple format)
3. **Fallback 2**: `message.content` (alternative nesting)
4. **Fallback 3**: `delta.content` (another variant)
5. **Fallback 4**: `text` (custom servers)

When it finds a path that yields tokens, it uses that for the entire stream.

### Example: Different SSE Formats

**vLLM sends:**
```json
data: {"choices":[{"delta":{"content":"Hello"}}]}
```

**llama.cpp sends:**
```json
data: {"content":"Hello","stop":false}
```

**Custom server sends:**
```json
data: {"text":"Hello"}
```

**The parser handles all three** by trying each path until one succeeds.

### End-of-Stream Auto-Detection

Different backends use different markers:
- `[DONE]` (OpenAI format)
- `{"stop": true}` (some backends)
- `{"finish_reason": "stop"}` (others)

The parser tries all known signals automatically.

## The Universal Adapter

File: `turing_bench/adapters/_default.yaml`

```yaml
backend: openai_compatible
sse_content_path: "choices[0].delta.content"
fallback_paths:
  - "choices[0].delta.content"
  - "content"
  - "message.content"
  - "delta.content"
  - "text"
done_signal: "[DONE]"
alternate_done_signals:
  - "[DONE]"
  - '{"stop": true}'
  - '{"finish_reason": "stop"}'
concurrent:
  rps: 16
  concurrency: 32
  num_requests: 500
```

This is the **only adapter you need**.

## When to Extend

If a new backend emerges with a **fundamentally different format**:

1. Don't create a new adapter file
2. Instead, add the new path to `fallback_paths` in `_default.yaml`
3. Add any new done signals to `alternate_done_signals`

**That's it.** No new adapters needed.

Example:
```yaml
fallback_paths:
  - "choices[0].delta.content"  # existing
  - "content"
  - "message.content"
  - "delta.content"
  - "text"
  - "token.text"  # new backend variant
```

## Design Principle

> **No backend-specific code.** The benchmark is backend-agnostic by design. Variations are handled via auto-detection in the SSE parser, not via separate adapters.

This ensures:
- ✅ Single, maintainable codebase
- ✅ Works with any OpenAI-compatible service
- ✅ Easy to extend when new backends arrive
- ✅ No coupling to specific frameworks
- ✅ True portability

## For Users

You never need to think about adapters. Just point Turing at any endpoint:

```bash
turing-bench run --endpoint http://your-server:port \
  --phase baseline \
  --stack-id your-model-name
```

It works.
