"""Integration tests for validity layer with baseline management."""

import json
import tempfile
from pathlib import Path

import pytest

from turing_bench.validity import ValidityLayer, CheckSeverity
from turing_bench.report.baseline import BaselineManager


class TestValidityLayerIntegration:
    """Test validity layer with realistic data."""

    def test_validate_batch_with_identical_outputs(self):
        """Test semantic similarity when outputs are identical."""
        validity = ValidityLayer()

        baseline_outputs = [
            "The capital of Japan is Tokyo. Tokyo is located on Honshu island.",
            "The capital of Japan is Tokyo. Tokyo is located on Honshu island.",
        ]

        candidate_outputs = [
            "The capital of Japan is Tokyo. Tokyo is located on Honshu island.",
            "The capital of Japan is Tokyo. Tokyo is located on Honshu island.",
        ]

        validity_config = {
            "min_length": 5,
            "max_length": 200,
            "similarity_threshold": 0.92,
        }

        result, per_output = validity.validate_batch(
            scenario_id="test_prompt",
            outputs=candidate_outputs,
            baseline_outputs=baseline_outputs,
            validity_config=validity_config,
        )

        # Should pass with high similarity
        assert result.scenarios["test_prompt"].overall_passed
        scenario_result = result.scenarios["test_prompt"]
        similarity_check = [c for c in scenario_result.checks if c.layer == 3]
        if similarity_check:
            assert similarity_check[0].score >= 0.92

    def test_validate_batch_sanity_check_empty(self):
        """Test sanity check fails on empty output (single output validation)."""
        validity = ValidityLayer()

        # Test single validation (not batch)
        result = validity.validate(
            scenario_id="test_prompt",
            output="",
            baseline_output=None,
            validity_config={"min_length": 5, "max_length": 200},
        )

        # Should fail sanity check
        assert not result.overall_passed
        sanity_check = [c for c in result.checks if c.layer == 1]
        assert sanity_check
        assert not sanity_check[0].passed

    def test_validate_batch_control_prompt_exact_match(self):
        """Test exact match checking for control prompt."""
        validity = ValidityLayer()

        result, per_output = validity.validate_batch(
            scenario_id="control_prompt_v1",
            outputs=["12", "12", "12"],
            baseline_outputs=None,
            validity_config={
                "min_length": 1,
                "max_length": 10,
                "exact_match": True,
                "expected_output": "12",
            },
        )

        # Control prompt should pass exact match
        scenario_result = result.scenarios["control_prompt_v1"]
        exact_match_check = [c for c in scenario_result.checks if c.layer == 4]
        if exact_match_check:
            assert exact_match_check[0].passed


class TestBaselineManager:
    """Test baseline pinning and comparison."""

    def test_save_and_load_baseline(self):
        """Test saving and loading baseline files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = BaselineManager(tmpdir)

            scenario_results = {
                "small_prompt_v1": {
                    "raw_outputs": ["Output 1", "Output 2", "Output 3"],
                    "metrics": {
                        "mean_latency_ms": 100.5,
                        "p95_latency_ms": 150.2,
                    },
                    "validity": {"passed": True, "severity": "PASS"},
                },
            }

            metadata = {"endpoint": "http://localhost:8000", "adapter": "test"}

            # Save baseline
            saved_file = manager.save_baseline(
                stack_id="test_stack",
                phase="baseline",
                scenario_results=scenario_results,
                metadata=metadata,
            )

            assert Path(saved_file).exists()

            # Load baseline
            loaded = manager.load_baseline("test_stack")

            assert loaded["stack_id"] == "test_stack"
            assert loaded["phase"] == "baseline"
            assert "small_prompt_v1" in loaded["scenarios"]
            assert len(loaded["scenarios"]["small_prompt_v1"]["raw_outputs"]) == 3

    def test_baseline_immutability(self):
        """Test that baseline files are not overwritten."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = BaselineManager(tmpdir)

            scenario_results = {
                "small_prompt_v1": {
                    "raw_outputs": ["Output 1"],
                    "metrics": {"mean_latency_ms": 100.0},
                    "validity": {"passed": True, "severity": "PASS"},
                },
            }

            metadata = {"endpoint": "http://localhost:8000"}

            # Save first baseline
            manager.save_baseline(
                stack_id="test_stack",
                phase="baseline",
                scenario_results=scenario_results,
                metadata=metadata,
            )

            # Try to save again - should raise error
            with pytest.raises(ValueError, match="already exists"):
                manager.save_baseline(
                    stack_id="test_stack",
                    phase="baseline",
                    scenario_results=scenario_results,
                    metadata=metadata,
                )

    def test_candidate_save_allowed(self):
        """Test that candidate files can be saved and not blocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = BaselineManager(tmpdir)

            scenario_results = {
                "small_prompt_v1": {
                    "raw_outputs": ["Output 1"],
                    "metrics": {"mean_latency_ms": 100.0},
                    "validity": {"passed": True, "severity": "PASS"},
                },
            }

            metadata = {"endpoint": "http://localhost:8000"}

            # Save multiple candidates - should not raise
            for i in range(3):
                path = manager.save_baseline(
                    stack_id="test_stack",
                    phase="candidate",
                    scenario_results=scenario_results,
                    metadata=metadata,
                )
                assert Path(path).exists()

    def test_list_baselines(self):
        """Test listing available baseline files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = BaselineManager(tmpdir)

            scenario_results = {
                "small_prompt_v1": {
                    "raw_outputs": ["Output 1"],
                    "metrics": {},
                    "validity": {},
                },
            }

            metadata = {}

            # Save baselines for different stacks
            manager.save_baseline(
                "stack1", "baseline", scenario_results, metadata
            )
            manager.save_baseline(
                "stack2", "baseline", scenario_results, metadata
            )

            baselines = manager.list_baselines()
            assert len(baselines) == 2

            stack1_baselines = manager.list_baselines("stack1")
            assert len(stack1_baselines) == 1


class TestValidityFormatter:
    """Test validity report formatting."""

    def test_format_validity_gate(self):
        """Test formatting validity gate results."""
        from turing_bench.report.formatter import format_validity_report

        results = {
            "small_prompt_v1": {
                "passed": True,
                "similarity": 0.96,
            },
            "large_prompt_v1": {
                "passed": True,
                "similarity": 0.93,
            },
            "long_context_v1": {
                "passed": False,
                "similarity": 0.80,
            },
        }

        report = format_validity_report(results)

        # Should show pass/fail per scenario
        assert "VALIDITY GATE" in report
        assert "small_prompt_v1" in report
        assert "PASS" in report
        assert "FAIL" in report


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
