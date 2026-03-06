from setuptools import setup, find_packages

setup(
    name="turing-bench",
    version="0.1.0",
    description="Turing LLM Benchmark - Service-level validation and performance testing",
    author="Benchmark Team",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "httpx>=0.24.0",
        "pyyaml>=6.0",
        "numpy>=1.24.0",
        "sentence-transformers>=2.2.0",
        "pydantic>=2.0.0",
        "click>=8.1.0",
        "python-dotenv>=1.0.0",
    ],
    entry_points={
        "console_scripts": [
            "turing-bench=turing_bench.cli:main",
        ],
    },
)
