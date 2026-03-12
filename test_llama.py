#!/usr/bin/env python
"""Test script for llama.cpp on port 9000 with Qwen model."""

import asyncio
import json
from pathlib import Path

# Add current dir to path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from turing_bench.runner.sequential import SequentialRunner
from turing_bench.runner.concurrent import ConcurrentRunner
from turing_bench.validity import ValidityLayer
from turing_bench.report.baseline import BaselineManager
import yaml


async def main():
    endpoint = "http://localhost:9000"
    stack_id = "qwen-llama-cpp"

    print("\n" + "=" * 70)
    print("TURING LLM BENCHMARK - LLAMA.CPP TEST")
    print("=" * 70)
    print(f"Endpoint: {endpoint}")
    print(f"Stack ID: {stack_id}")
    print()

    # Load adapter config
    adapter_path = Path(__file__).parent / "turing_bench/adapters/_default.yaml"
    with open(adapter_path) as f:
        adapter_config = yaml.safe_load(f)

    # Load scenarios
    scenarios_dir = Path(__file__).parent / "turing_bench/scenarios"
    scenario_files = sorted(scenarios_dir.glob("*.yaml"))

    scenarios = {}
    for f in scenario_files:
        with open(f) as file:
            scenarios[f.stem] = yaml.safe_load(file)

    print(f"Loaded {len(scenarios)} scenarios: {', '.join(scenarios.keys())}")
    print()

    # Initialize components
    validity_layer = ValidityLayer()
    baseline_manager = BaselineManager(str(Path.cwd() / "baselines"))

    # PHASE 1: SEQUENTIAL (test with just one scenario for speed)
    print("=" * 70)
    print("PHASE 1: SEQUENTIAL EXECUTION (Correctness Validation)")
    print("=" * 70)
    print()

    sequential_runner = SequentialRunner(endpoint, adapter_config)

    # Test with control_prompt_v1 first (shortest, fastest)
    test_scenario = "control_prompt_v1"
    scenario_config = scenarios[test_scenario]

    print(f"Testing scenario: {test_scenario}")
    print(f"  Warmup: {scenario_config.get('warmup', 20)} requests")
    print(f"  Measurement: {scenario_config.get('runs', 50)} runs")
    print()

    try:
        results = await sequential_runner.run_scenario(
            scenario_config,
            warmup_requests=5,  # Quick test - fewer warmup
            num_runs=10  # Quick test - fewer runs
        )

        successful = [r for r in results if r.error is None]
        errors = [r for r in results if r.error is not None]

        print(f"Results: {len(successful)} successful, {len(errors)} errors")

        if successful:
            print("\nSample outputs:")
            for i, r in enumerate(successful[:3]):
                print(f"  Run {i+1}: '{r.output[:60]}...' (TTFT: {r.ttft_ms:.1f}ms, Latency: {r.total_time_ms:.1f}ms)")

        if errors:
            print("\nErrors:")
            for r in errors:
                print(f"  Run {r.run_number}: {r.error}")

        print()

        # Validate
        print("Running validity checks...")
        raw_outputs = [r.output for r in successful]

        validity_config = scenario_config.get("validity", {})
        validation_result, per_output = validity_layer.validate_batch(
            scenario_id=test_scenario,
            outputs=raw_outputs,
            baseline_outputs=None,
            validity_config=validity_config,
        )

        scenario_result = validation_result.scenarios.get(test_scenario)
        if scenario_result:
            print(f"Validity: {scenario_result.overall_severity.value}")
            for check in scenario_result.checks:
                status = "PASS" if check.passed else "FAIL"
                print(f"  - Layer {check.layer} ({check.name}): {status}")

        print()
        print("=" * 70)
        print("SUCCESS! Benchmark is working with your llama.cpp")
        print("=" * 70)
        print()
        print("Next steps:")
        print("  1. Run full baseline (all scenarios, 50 runs each):")
        print(f"     python turing_bench.py run-benchmark \\")
        print(f"       --endpoint {endpoint} \\")
        print(f"       --phase baseline \\")
        print(f"       --stack-id {stack_id}")
        print()
        print("  2. After optimization, run candidate:")
        print(f"     python turing_bench.py run-benchmark \\")
        print(f"       --endpoint {endpoint} \\")
        print(f"       --phase candidate \\")
        print(f"       --stack-id {stack_id}")
        print()

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
