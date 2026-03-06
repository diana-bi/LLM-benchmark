FROM ubuntu:22.04

# Install dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    curl \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Build llama.cpp from source
WORKDIR /app
RUN git clone https://github.com/ggerganov/llama.cpp.git llama-repo && \
    cd llama-repo && \
    make -j$(nproc)

# Create a working directory for models and server
WORKDIR /app/server

# Copy llama-server binary
RUN cp /app/llama-repo/llama-server /app/server/

# Expose the port
EXPOSE 8000

# Environment variables for runtime configuration
ENV MODEL_FILE=model.gguf
ENV GPU_LAYERS=0
ENV CTX_SIZE=2048

# Health check - /v1/models endpoint is always available
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=5 \
    CMD curl -sf http://localhost:8000/v1/models || exit 1

# Default command - uses environment variables for flexibility
CMD ["/bin/sh", "-c", "/app/server/llama-server \
     -m /models/${MODEL_FILE} \
     -ngl ${GPU_LAYERS} \
     -c ${CTX_SIZE} \
     --port 8000 \
     --host 0.0.0.0"]
