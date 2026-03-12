#!/usr/bin/env python
"""Wrapper to use the new integrated CLI."""

import sys
from pathlib import Path

# Add to path
sys.path.insert(0, str(Path(__file__).parent))

from turing_bench.cli import cli

if __name__ == "__main__":
    cli()
