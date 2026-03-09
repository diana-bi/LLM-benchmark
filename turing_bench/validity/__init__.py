"""Validity layer modules for multi-stage correctness verification."""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any
from enum import Enum

from .sanity import sanity_check
from .structural import structural_check
from .semantic import semantic_check
from .exact_match import exact_match_check


class CheckSeverity(Enum):
    """Check result severity level."""
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass
class CheckResult:
    """Result of a single validity check."""
    layer: int
    name: str
    passed: bool
    severity: CheckSeverity
    message: str
    score: Optional[float] = None  # For similarity scores

    def __repr__(self):
        return f"{self.name}: {self.severity.value} - {self.message}"


@dataclass
class ScenarioValidityResult:
    """Validity results for a single scenario."""
    scenario_id: str
    checks: List[CheckResult] = field(default_factory=list)
    overall_passed: bool = True
    overall_severity: CheckSeverity = CheckSeverity.PASS

    def add_check(self, check: CheckResult):
        """Add a check result and update overall status."""
        self.checks.append(check)

        # Update overall severity (FAIL > WARN > PASS)
        if check.severity == CheckSeverity.FAIL:
            self.overall_severity = CheckSeverity.FAIL
            self.overall_passed = False
        elif check.severity == CheckSeverity.WARN and self.overall_severity != CheckSeverity.FAIL:
            self.overall_severity = CheckSeverity.WARN

    def get_similarity_score(self) -> Optional[float]:
        """Get semantic similarity score if available."""
        for check in self.checks:
            if check.layer == 3 and check.score is not None:
                return check.score
        return None


@dataclass
class ValidationResult:
    """Complete validation result across all scenarios."""
    scenarios: Dict[str, ScenarioValidityResult] = field(default_factory=dict)
    overall_passed: bool = True
    overall_severity: CheckSeverity = CheckSeverity.PASS
    failed_reason: Optional[str] = None

    def add_scenario_result(self, scenario_id: str, result: ScenarioValidityResult):
        """Add scenario result and update overall status."""
        self.scenarios[scenario_id] = result

        # Update overall severity (FAIL > WARN > PASS)
        if result.overall_severity == CheckSeverity.FAIL:
            self.overall_severity = CheckSeverity.FAIL
            self.overall_passed = False
        elif result.overall_severity == CheckSeverity.WARN and self.overall_severity != CheckSeverity.FAIL:
            self.overall_severity = CheckSeverity.WARN

    def get_mean_similarity(self) -> Optional[float]:
        """Get mean semantic similarity across all scenarios (for non-control prompts)."""
        similarities = []
        for scenario_id, result in self.scenarios.items():
            # Skip control prompt for mean calculation
            if scenario_id == "control_prompt_v1":
                continue
            score = result.get_similarity_score()
            if score is not None:
                similarities.append(score)

        if similarities:
            return sum(similarities) / len(similarities)
        return None


class ValidityLayer:
    """
    Multi-layer validity checker.

    Layers run in order:
    1. Sanity (mandatory, all scenarios)
    2. Structural (optional per scenario)
    3. Semantic similarity (all except control)
    4. Exact-match (control prompt only)
    """

    def __init__(self, embedding_cache: Optional[Any] = None):
        """
        Initialize validity layer.

        Args:
            embedding_cache: Optional embedding model cache to avoid reloading
        """
        self.embedding_cache = embedding_cache

    def validate(
        self,
        scenario_id: str,
        output: str,
        baseline_output: Optional[str] = None,
        validity_config: Optional[Dict[str, Any]] = None,
        scenario_config: Optional[Dict[str, Any]] = None,
    ) -> ScenarioValidityResult:
        """
        Run all applicable validity layers for a scenario.

        Args:
            scenario_id: Scenario identifier (e.g., "small_prompt_v1")
            output: Generated output to validate
            baseline_output: Reference baseline output (for semantic check)
            validity_config: Validity configuration from scenario YAML
                {
                  "min_length": 10,
                  "max_length": 150,
                  "similarity_threshold": 0.92,
                  "exact_match": false,
                  "check_json": false,
                  "check_python": false
                }
            scenario_config: Full scenario config (for context)

        Returns:
            ScenarioValidityResult with all checks
        """
        if validity_config is None:
            validity_config = {}
        if scenario_config is None:
            scenario_config = {}

        result = ScenarioValidityResult(scenario_id=scenario_id)

        # Layer 1: Sanity (mandatory)
        min_length = validity_config.get("min_length", 5)
        max_length = validity_config.get("max_length", 1000)
        passed, message = sanity_check(output, min_length, max_length)

        check = CheckResult(
            layer=1,
            name="Sanity",
            passed=passed,
            severity=CheckSeverity.PASS if passed else CheckSeverity.FAIL,
            message=message,
        )
        result.add_check(check)

        # If Layer 1 failed, stop here
        if not passed:
            result.overall_passed = False
            return result

        # Layer 2: Structural (optional)
        check_json = validity_config.get("check_json", False)
        check_python = validity_config.get("check_python", False)

        if check_json or check_python:
            passed, message = structural_check(output, check_json, check_python)
            check = CheckResult(
                layer=2,
                name="Structural",
                passed=passed,
                severity=CheckSeverity.PASS if passed else CheckSeverity.FAIL,
                message=message,
            )
            result.add_check(check)

            # If Layer 2 failed, stop here
            if not passed:
                result.overall_passed = False
                return result

        # Layer 3: Semantic similarity (all except control)
        if scenario_id != "control_prompt_v1":
            if baseline_output is not None:
                similarity_threshold = validity_config.get("similarity_threshold", 0.92)
                passed, message, similarity = semantic_check(
                    output,
                    baseline_output,
                    similarity_threshold=similarity_threshold,
                    embedding_cache=self.embedding_cache,
                )

                # For semantic: >= 0.92 is PASS, 0.85-0.92 is WARN, < 0.85 is FAIL
                if similarity >= similarity_threshold:
                    severity = CheckSeverity.PASS
                    final_passed = True
                elif similarity >= 0.85:
                    severity = CheckSeverity.WARN
                    final_passed = True  # WARN doesn't block, only FAIL blocks
                else:
                    severity = CheckSeverity.FAIL
                    final_passed = False

                check = CheckResult(
                    layer=3,
                    name="SemanticSimilarity",
                    passed=final_passed,
                    severity=severity,
                    message=message,
                    score=similarity,
                )
                result.add_check(check)

                # If Layer 3 failed (FAIL severity), stop here
                if severity == CheckSeverity.FAIL:
                    result.overall_passed = False
                    return result

        # Layer 4: Exact-match (control prompt only)
        if scenario_id == "control_prompt_v1":
            expected_output = validity_config.get("expected_output", "12")
            passed, message = exact_match_check(output, expected_output)

            # Exact match returns WARN level, not FAIL
            check = CheckResult(
                layer=4,
                name="ExactMatch",
                passed=passed,
                severity=CheckSeverity.WARN if not passed else CheckSeverity.PASS,
                message=message,
            )
            result.add_check(check)

        return result

    def validate_batch(
        self,
        scenario_id: str,
        outputs: List[str],
        baseline_outputs: Optional[List[str]] = None,
        validity_config: Optional[Dict[str, Any]] = None,
        scenario_config: Optional[Dict[str, Any]] = None,
    ) -> Tuple[ValidationResult, Dict[int, ScenarioValidityResult]]:
        """
        Validate multiple outputs (e.g., 50 sequential runs).

        Args:
            scenario_id: Scenario identifier
            outputs: List of outputs to validate
            baseline_outputs: List of baseline outputs (for semantic comparison)
            validity_config: Validity configuration
            scenario_config: Scenario configuration

        Returns:
            Tuple of (ValidationResult, dict of per-output results)
            Only the first output is used for baseline comparison (semantic check)
        """
        validation_result = ValidationResult()
        per_output_results = {}

        # Use only first baseline output for semantic comparison
        baseline_output = baseline_outputs[0] if baseline_outputs else None

        for idx, output in enumerate(outputs):
            scenario_result = self.validate(
                scenario_id,
                output,
                baseline_output=baseline_output,
                validity_config=validity_config,
                scenario_config=scenario_config,
            )
            per_output_results[idx] = scenario_result

            # Update overall validation result
            # We care most about consistency - if any output fails Layer 1-2, the scenario fails
            if scenario_result.overall_severity == CheckSeverity.FAIL:
                validation_result.overall_passed = False
                validation_result.overall_severity = CheckSeverity.FAIL
                break  # Stop on first failure

        # Aggregate scenario result
        final_scenario_result = ScenarioValidityResult(scenario_id=scenario_id)

        # For semantic check: use mean of all similarities
        similarities = []
        exact_matches = []

        for per_output in per_output_results.values():
            for check in per_output.checks:
                if check.layer == 3 and check.score is not None:
                    similarities.append(check.score)
                elif check.layer == 4 and check.passed:
                    exact_matches.append(True)

        # Add semantic check with mean similarity
        if similarities:
            mean_similarity = sum(similarities) / len(similarities)
            similarity_threshold = validity_config.get("similarity_threshold", 0.92) if validity_config else 0.92

            if mean_similarity >= similarity_threshold:
                severity = CheckSeverity.PASS
            elif mean_similarity >= 0.85:
                severity = CheckSeverity.WARN
            else:
                severity = CheckSeverity.FAIL

            check = CheckResult(
                layer=3,
                name="SemanticSimilarity",
                passed=severity != CheckSeverity.FAIL,
                severity=severity,
                message=f"Mean semantic similarity: {mean_similarity:.3f}",
                score=mean_similarity,
            )
            final_scenario_result.add_check(check)

            if severity == CheckSeverity.FAIL:
                validation_result.overall_passed = False
                validation_result.overall_severity = CheckSeverity.FAIL

        # Add exact match check (control prompt)
        if scenario_id == "control_prompt_v1" and exact_matches:
            match_rate = len(exact_matches) / len(per_output_results)
            check = CheckResult(
                layer=4,
                name="ExactMatch",
                passed=match_rate == 1.0,
                severity=CheckSeverity.PASS if match_rate == 1.0 else CheckSeverity.WARN,
                message=f"Exact match rate: {match_rate*100:.1f}%",
                score=match_rate,
            )
            final_scenario_result.add_check(check)

        validation_result.add_scenario_result(scenario_id, final_scenario_result)

        return validation_result, per_output_results


__all__ = [
    "ValidityLayer",
    "ValidationResult",
    "ScenarioValidityResult",
    "CheckResult",
    "CheckSeverity",
    "sanity_check",
    "structural_check",
    "semantic_check",
    "exact_match_check",
]
