"""Baseline pinning - save and load baseline JSON files."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional


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
    ) -> str:
        """
        Save benchmark results as baseline.

        Args:
            stack_id: Identifier for this stack (e.g., "qwen2.5-7b_vllm_a100")
            phase: "baseline" or "candidate"
            scenario_results: Results from all scenarios
            metadata: Hardware and environment metadata

        Returns:
            Path to saved baseline file
        """

        timestamp = datetime.now().isoformat(timespec="seconds")
        filename = f"{stack_id}_{timestamp.split('T')[0]}_{phase}.json"
        filepath = self.baselines_dir / filename

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
            baseline_file: Specific file to load, or None for latest

        Returns:
            Baseline data dictionary
        """

        if baseline_file:
            filepath = self.baselines_dir / baseline_file
            if not filepath.exists():
                raise FileNotFoundError(f"Baseline file not found: {baseline_file}")
            with open(filepath, "r") as f:
                return json.load(f)

        # Find latest baseline for stack_id
        matching_files = sorted(self.baselines_dir.glob(f"{stack_id}_*_baseline.json"), reverse=True)

        if not matching_files:
            raise FileNotFoundError(f"No baseline found for stack: {stack_id}")

        with open(matching_files[0], "r") as f:
            return json.load(f)

    def list_baselines(self, stack_id: Optional[str] = None) -> list[str]:
        """
        List available baseline files.

        Args:
            stack_id: Optional filter by stack ID

        Returns:
            List of baseline file paths
        """

        if stack_id:
            files = self.baselines_dir.glob(f"{stack_id}_*_baseline.json")
        else:
            files = self.baselines_dir.glob("*_baseline.json")

        return sorted(str(f) for f in files)
