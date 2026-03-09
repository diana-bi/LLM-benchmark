"""Test CLI integration with full benchmark flow."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from turing_bench.cli import (
    _compute_metrics,
    _validate_sequential_results,
)
from turing_bench.validity import ValidityLayer


class TestCLIHelpers:
    """Test CLI helper functions."""

    def test_compute_metrics_basic(self):
        """Test metric computation from latency data."""
        latencies = [100.0, 110.0, 120.0, 130.0, 140.0]
        ttft_values = [10.0, 11.0, 12.0, 13.0, 14.0]

        metrics = _compute_metrics(latencies, ttft_values)

        assert "mean_latency_ms" in metrics
        assert "p50_latency_ms" in metrics
        assert "p95_latency_ms" in metrics
        assert "p99_latency_ms" in metrics
        assert "mean_ttft_ms" in metrics
        assert "p50_ttft_ms" in metrics
        assert "p95_ttft_ms" in metrics
        assert "cv_percent" in metrics

        # Check values make sense
        assert metrics["mean_latency_ms"] == pytest.approx(120.0)
        assert metrics["p50_latency_ms"] == 120.0
        assert metrics["p95_latency_ms"] >= 130.0

    def test_compute_metrics_no_ttft(self):
        """Test metric computation without TTFT data."""
        latencies = [100.0, 110.0, 120.0]

        metrics = _compute_metrics(latencies)

        assert "mean_latency_ms" in metrics
        assert "mean_ttft_ms" not in metrics
        assert metrics["mean_latency_ms"] == pytest.approx(110.0)

    def test_compute_metrics_cv_calculation(self):
        """Test coefficient of variation calculation."""
        # Constant values should have CV = 0
        latencies = [100.0] * 10
        metrics = _compute_metrics(latencies)
        assert metrics["cv_percent"] == 0.0

        # Variable values should have non-zero CV
        latencies = [100.0, 150.0, 50.0, 100.0, 150.0]
        metrics = _compute_metrics(latencies)
        assert metrics["cv_percent"] > 0.0

    def test_validate_sequential_results(self):
        """Test validity validation from sequential results."""
        validity = ValidityLayer()

        raw_outputs = [
            "Tokyo is the capital of Japan.",
            "Tokyo is the capital of Japan.",
        ]

        is_valid, scenario_result, severity = _validate_sequential_results(
            scenario_id="small_prompt_v1",
            raw_outputs=raw_outputs,
            baseline_outputs=raw_outputs,  # Use same as baseline
            scenario_config={
                "validity": {
                    "min_length": 5,
                    "max_length": 100,
                    "similarity_threshold": 0.92,
                }
            },
            validity_layer=validity,
        )

        # Should pass with identical outputs
        assert is_valid
        assert severity in ["PASS", "WARN"]

    def test_validate_sequential_results_empty_outputs(self):
        """Test validation fails on empty outputs."""
        validity = ValidityLayer()

        is_valid, scenario_result, severity = _validate_sequential_results(
            scenario_id="test",
            raw_outputs=[],
            baseline_outputs=None,
            scenario_config={"validity": {}},
            validity_layer=validity,
        )

        # Should fail with empty outputs
        assert not is_valid


class TestCLIIntegration:
    """Test full CLI integration."""

    def test_cli_imports(self):
        """Test that CLI module imports correctly."""
        from turing_bench.cli import cli
        assert cli is not None

    def test_baseline_manager_in_cli(self):
        """Test that baseline manager is available in CLI."""
        from turing_bench.cli import BaselineManager
        assert BaselineManager is not None

    def test_validity_layer_in_cli(self):
        """Test that validity layer is available in CLI."""
        from turing_bench.cli import ValidityLayer
        assert ValidityLayer is not None


class TestCLIWorkflow:
    """Test typical CLI workflow scenarios."""

    def test_baseline_phase_workflow(self):
        """Test baseline phase workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from turing_bench.report.baseline import BaselineManager

            manager = BaselineManager(tmpdir)

            # Simulate baseline run
            scenario_results = {
                "small_prompt_v1": {
                    "raw_outputs": ["Output 1", "Output 2", "Output 3"],
                    "metrics": {"mean_latency_ms": 100.5, "p95_latency_ms": 150.2},
                    "validity": {"passed": True, "severity": "PASS"},
                },
                "large_prompt_v1": {
                    "raw_outputs": ["Output A", "Output B", "Output C"],
                    "metrics": {"mean_latency_ms": 200.5, "p95_latency_ms": 250.2},
                    "validity": {"passed": True, "severity": "PASS"},
                },
            }

            # Save baseline
            baseline_file = manager.save_baseline(
                stack_id="test-stack",
                phase="baseline",
                scenario_results=scenario_results,
                metadata={"endpoint": "http://localhost:8000"},
            )

            # Verify file was created
            assert Path(baseline_file).exists()
            assert "baseline" in baseline_file

            # Load it back
            loaded = manager.load_baseline("test-stack")
            assert loaded["phase"] == "baseline"
            assert "small_prompt_v1" in loaded["scenarios"]

    def test_candidate_phase_workflow(self):
        """Test candidate phase workflow with baseline comparison."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from turing_bench.report.baseline import BaselineManager

            manager = BaselineManager(tmpdir)

            baseline_results = {
                "small_prompt_v1": {
                    "raw_outputs": ["Baseline output 1", "Baseline output 2"],
                    "metrics": {"mean_latency_ms": 100.0, "p95_latency_ms": 150.0},
                    "validity": {"passed": True, "severity": "PASS"},
                },
            }

            # Save baseline first
            baseline_file = manager.save_baseline(
                stack_id="test-stack",
                phase="baseline",
                scenario_results=baseline_results,
                metadata={"endpoint": "http://localhost:8000"},
            )

            # Load baseline
            baseline_data = manager.load_baseline("test-stack")
            assert baseline_data["phase"] == "baseline"

            # Now save candidate
            candidate_results = {
                "small_prompt_v1": {
                    "raw_outputs": ["Candidate output 1", "Candidate output 2"],
                    "metrics": {"mean_latency_ms": 95.0, "p95_latency_ms": 140.0},
                    "validity": {"passed": True, "severity": "PASS"},
                },
            }

            candidate_file = manager.save_baseline(
                stack_id="test-stack",
                phase="candidate",
                scenario_results=candidate_results,
                metadata={"endpoint": "http://localhost:8000"},
            )

            # Verify candidate was saved
            assert Path(candidate_file).exists()
            assert "candidate" in candidate_file

            # Verify baseline is still unchanged
            baseline_again = manager.load_baseline("test-stack")
            assert baseline_again["phase"] == "baseline"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
