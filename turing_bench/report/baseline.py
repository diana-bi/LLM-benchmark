"""Baseline pinning - save and load baseline JSON files."""

import json
import os
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Dict, Any, Optional, List


class BaselineManager:
    """Manage baseline pinning - save/load for reproducible comparisons."""

    def __init__(self, baselines_dir: str = "./baselines"):
        """
        Initialize baseline manager.

        Args:
            baselines_dir: Directory to store baseline JSON files
        """
        self.baselines_dir = Path(baselines_dir)
        self.baselines_dir.mkdir(parents=True, exist_ok=True)

    def save_baseline(
        self,
        stack_id: str,
        phase: str,
        scenario_results: Dict[str, Any],
        metadata: Dict[str, Any],
        timestamp: Optional[str] = None,
    ) -> str:
        """
        Save benchmark results as baseline or candidate.

        Args:
            stack_id: Identifier for this stack (e.g., "qwen2.5-7b_vllm_a100")
            phase: "baseline" or "candidate"
            scenario_results: Results from all scenarios
              - raw_outputs: List of 50 outputs
              - metrics: ttft_p50, ttft_p95, tps, latency_p50, latency_p95, cv
              - validity: ValidationResult dict
            metadata: Hardware and environment metadata
            timestamp: Optional ISO 8601 timestamp (auto-generated if None)

        Returns:
            Path to saved baseline file

        Raises:
            ValueError: If trying to overwrite existing baseline
        """

        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # Extract date for filename (use local date, not UTC, to avoid timezone mismatch)
        date_str = date.today().isoformat()  # YYYY-MM-DD in local timezone
        filename = f"{stack_id}_{date_str}_{phase}.json"
        filepath = self.baselines_dir / filename

        # Safety check: never overwrite existing baseline, but auto-increment version if needed
        if filepath.exists() and phase == "baseline":
            version = 2
            while filepath.exists():
                versioned_name = f"{stack_id}_{date_str}_v{version}_{phase}.json"
                filepath = self.baselines_dir / versioned_name
                version += 1

        baseline_data = {
            "schema_version": "1.0",
            "stack_id": stack_id,
            "phase": phase,
            "timestamp": timestamp,
            "scenario_version": "v1",
            "hardware_state": metadata,
            "scenarios": scenario_results,
        }

        with open(filepath, "w") as f:
            json.dump(baseline_data, f, indent=2)

        return str(filepath)

    def load_baseline(self, stack_id: str, baseline_file: Optional[str] = None) -> Dict[str, Any]:
        """
        Load a baseline file.

        Args:
            stack_id: Stack ID to search for
            baseline_file: Specific file to load (overrides auto-detection)
                          Can be just filename or full path
                          If None, loads latest baseline for stack_id

        Returns:
            Baseline data dictionary

        Raises:
            FileNotFoundError: If baseline not found
            ValueError: If baseline schema invalid
        """

        if baseline_file:
            # Support both full path and just filename
            filepath = self.baselines_dir / baseline_file if "/" not in baseline_file else Path(baseline_file)
            if not filepath.exists():
                raise FileNotFoundError(f"Baseline file not found: {filepath}")
            with open(filepath, "r") as f:
                data = json.load(f)
                self._validate_schema(data)
                return data

        # Find latest baseline for stack_id (baseline files only)
        matching_files = sorted(
            self.baselines_dir.glob(f"{stack_id}_*_baseline.json"),
            reverse=True  # Most recent first
        )

        if not matching_files:
            raise FileNotFoundError(
                f"No baseline found for stack: {stack_id} "
                f"(searched in {self.baselines_dir})"
            )

        with open(matching_files[0], "r") as f:
            data = json.load(f)
            self._validate_schema(data)
            return data

    def list_baselines(self, stack_id: Optional[str] = None) -> List[str]:
        """
        List available baseline files.

        Args:
            stack_id: Optional filter by stack ID

        Returns:
            List of baseline file names (sorted by date, most recent last)
        """

        if stack_id:
            files = sorted(self.baselines_dir.glob(f"{stack_id}_*_baseline.json"))
        else:
            files = sorted(self.baselines_dir.glob("*_baseline.json"))

        return [f.name for f in files]

    def list_all_candidates(self, stack_id: Optional[str] = None) -> List[str]:
        """
        List all candidate runs (for comparison tracking).

        Args:
            stack_id: Optional filter by stack ID

        Returns:
            List of candidate file names
        """

        if stack_id:
            files = sorted(self.baselines_dir.glob(f"{stack_id}_*_candidate.json"))
        else:
            files = sorted(self.baselines_dir.glob("*_candidate.json"))

        return [f.name for f in files]

    def get_baseline_metrics(self, stack_id: str, baseline_file: Optional[str] = None) -> Dict[str, Dict[str, float]]:
        """
        Extract metrics from baseline for quick comparison.

        Args:
            stack_id: Stack ID
            baseline_file: Optional specific baseline file

        Returns:
            Dict mapping scenario_id to metrics dict
        """
        baseline = self.load_baseline(stack_id, baseline_file)
        return {
            scenario_id: scenario_data.get("metrics", {})
            for scenario_id, scenario_data in baseline.get("scenarios", {}).items()
        }

    def get_baseline_outputs(self, stack_id: str, scenario_id: str, baseline_file: Optional[str] = None) -> List[str]:
        """
        Get raw outputs from baseline for semantic comparison.

        Args:
            stack_id: Stack ID
            scenario_id: Scenario to get outputs for (e.g., "small_prompt_v1")
            baseline_file: Optional specific baseline file

        Returns:
            List of 50 baseline outputs
        """
        baseline = self.load_baseline(stack_id, baseline_file)
        scenario_data = baseline.get("scenarios", {}).get(scenario_id, {})
        return scenario_data.get("raw_outputs", [])

    def _validate_schema(self, data: Dict[str, Any]) -> None:
        """Validate baseline JSON schema."""
        required_fields = [
            "schema_version",
            "stack_id",
            "phase",
            "timestamp",
            "scenario_version",
            "hardware_state",
            "scenarios",
        ]

        for field in required_fields:
            if field not in data:
                raise ValueError(f"Invalid baseline: missing required field '{field}'")

        # Validate each scenario
        scenarios = data.get("scenarios", {})
        if not isinstance(scenarios, dict):
            raise ValueError("Invalid baseline: 'scenarios' must be a dict")

        for scenario_id, scenario_data in scenarios.items():
            required_scenario_fields = ["raw_outputs", "metrics", "validity"]
            for field in required_scenario_fields:
                if field not in scenario_data:
                    raise ValueError(
                        f"Invalid baseline: scenario '{scenario_id}' missing field '{field}'"
                    )

            # Validate raw_outputs is a list
            if not isinstance(scenario_data.get("raw_outputs"), list):
                raise ValueError(
                    f"Invalid baseline: scenario '{scenario_id}' raw_outputs must be a list"
                )

            # Validate metrics is a dict
            if not isinstance(scenario_data.get("metrics"), dict):
                raise ValueError(
                    f"Invalid baseline: scenario '{scenario_id}' metrics must be a dict"
                )

    def promote_candidate_to_baseline(self, candidate_file: str) -> str:
        """
        Promote a candidate run to become the new baseline.

        Args:
            candidate_file: Candidate filename to promote

        Returns:
            New baseline filename

        Raises:
            FileNotFoundError: If candidate file not found
            ValueError: If not a valid candidate file
        """
        candidate_path = self.baselines_dir / candidate_file

        if not candidate_path.exists():
            raise FileNotFoundError(f"Candidate file not found: {candidate_path}")

        if "_candidate.json" not in candidate_file:
            raise ValueError(f"Not a candidate file: {candidate_file}")

        # Load candidate data
        with open(candidate_path, "r") as f:
            data = json.load(f)

        # Change phase to baseline
        data["phase"] = "baseline"
        data["timestamp"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # Create new baseline filename
        new_filename = candidate_file.replace("_candidate.json", "_baseline.json")
        new_path = self.baselines_dir / new_filename

        # Check we're not overwriting an existing baseline with same name
        if new_path.exists():
            raise ValueError(
                f"Baseline with this name already exists: {new_filename}. "
                f"Use a different date."
            )

        # Save as new baseline
        with open(new_path, "w") as f:
            json.dump(data, f, indent=2)

        return new_filename


__all__ = [
    "BaselineManager",
]
