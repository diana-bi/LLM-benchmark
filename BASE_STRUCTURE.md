# Turing LLM Benchmark - Base Structure

A complete base structure for the Turing LLM Benchmark, ready for the team to add features on top.

```
/i/diana-bi/benchmark/
├── Dockerfile                    # llama.cpp service (fixed)
├── docker-compose.yml            # Docker setup (fixed)
├── requirements.txt              # Python dependencies
├── setup.py                      # Package setup
├── README.md                     # Main documentation
├── start.sh                      # Quick start script
│
├── turing_bench.py              # CLI entrypoint (root level)
│
├── turing_bench/                # Python package
│   ├── __init__.py
│   │
│   ├── runner/                  # Execution engines
│   │   ├── __init__.py
│   │   ├── conformance.py       # Pre-flight check
│   │   ├── sequential.py        # Sequential execution
│   │   ├── concurrent.py        # Concurrent execution
│   │   └── sse_parser.py        # Stream parsing + TTFT
│   │
│   ├── validity/                # 4-layer correctness validation
│   │   ├── __init__.py
│   │   ├── sanity.py           # Layer 1: String bounds
│   │   ├── structural.py       # Layer 2: JSON/code format
│   │   ├── semantic.py         # Layer 3: Embedding similarity
│   │   └── exact_match.py      # Layer 4: Control prompt
│   │
│   ├── stats/                   # Metrics calculation
│   │   ├── __init__.py
│   │   ├── percentiles.py      # P50/P95/P99
│   │   └── cv.py               # Coefficient of variation
│   │
│   ├── report/                  # Results management
│   │   ├── __init__.py
│   │   ├── formatter.py        # Report formatting
│   │   └── baseline.py         # Baseline save/load
│   │
│   ├── scenarios/               # FROZEN scenario definitions (never edit)
│   │   ├── small_prompt_v1.yaml
│   │   ├── large_prompt_v1.yaml
│   │   ├── long_context_v1.yaml
│   │   └── control_prompt_v1.yaml
│   │
│   └── adapters/                # Backend-specific SSE formats
│       ├── _default.yaml        # Any OpenAI-compatible endpoint
│       └── llama_cpp.yaml       # llama.cpp specific
│
├── baselines/                   # Output directory for baseline JSONs
├── results/                     # Output directory for results
├── models/                      # Model files (qwen2.5-*.gguf)
└── .gitignore
```

