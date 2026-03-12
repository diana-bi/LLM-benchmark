#!/bin/bash
# Quick start script for Turing benchmark with llama.cpp

set -e

echo "🚀 Turing Benchmark - llama.cpp Setup"
echo "======================================"
echo ""

# Check if models directory exists and has a model
if [ ! -f "./models/model.gguf" ]; then
    echo "⚠️  No model found at models/model.gguf"
    echo ""
    echo "To continue, download a GGUF model and place it at models/model.gguf"
    echo ""
    echo "Example: Download Qwen2.5-7B-Instruct-GGUF"
    echo "  mkdir -p models"
    echo "  wget -O models/model.gguf <model_url>"
    echo ""
    exit 1
fi

echo "✓ Model found: models/model.gguf"
echo ""

# Build and start Docker services
echo "🐳 Starting Docker services..."
docker-compose up -d

# Wait for service to be healthy
echo "⏳ Waiting for llama.cpp service to be ready..."
max_attempts=30
attempt=0

while [ $attempt -lt $max_attempts ]; do
    if docker-compose ps llama-cpp | grep -q "healthy"; then
        echo "✓ Service is healthy"
        break
    fi

    attempt=$((attempt + 1))
    sleep 2

    if [ $((attempt % 5)) -eq 0 ]; then
        echo "  Still waiting... ($attempt/$max_attempts)"
    fi
done

if [ $attempt -eq $max_attempts ]; then
    echo "✗ Service failed to become healthy"
    echo ""
    echo "Check logs with: docker-compose logs llama-cpp"
    exit 1
fi

echo ""
echo "✓ Service ready on http://localhost:8000"
echo ""

# Check conformance
echo "🔍 Checking endpoint conformance..."
if python turing_bench.py check-conformance-cmd --endpoint http://localhost:8000; then
    echo ""
    echo "✓ Endpoint is conformant"
    echo ""
    echo "Next steps:"
    echo "  1. Run baseline:  python turing_bench.py run-benchmark --endpoint http://localhost:8000 --phase baseline --stack-id test-stack"
    echo "  2. Optimize your service"
    echo "  3. Run candidate: python turing_bench.py run-benchmark --endpoint http://localhost:8000 --phase candidate --stack-id test-stack"
    echo ""
else
    echo "✗ Endpoint is not conformant"
    echo ""
    echo "Check the endpoint logs:"
    echo "  docker-compose logs llama-cpp"
    exit 1
fi
