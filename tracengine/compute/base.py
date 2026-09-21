"""
TRACE Compute Base

Base class for all compute/metric plugins.
Compute modules calculate metrics from signals and events.
"""

from tracengine.data.descriptors import EventSpec, ChannelSpec, RunData
from tracengine.data.resolve import resolve_all, resolve_events
import pandas as pd
from abc import ABC, abstractmethod
from typing import List, Dict, Any


class ComputeBase(ABC):
    """
    Base class for all compute / metric plugins.

    Subclasses must define:
        - name: str
        - version: str (e.g., "1.0.0")
        - required_channels: dict[str, ChannelSpec]
        - required_events: dict[str, EventSpec]

    Optionally override:
        - get_parameters() -> list of parameter definitions

    And implement:
        - compute(run, **inputs) -> pd.DataFrame
    """

    name: str = "UnnamedCompute"
    version: str = "1.0.0"

    required_channels: dict[str, ChannelSpec] = {}
    required_events: dict[str, EventSpec] = {}

    @classmethod
    def get_parameters(cls) -> List[Dict[str, Any]]:
        """
        Return a list of configurable parameters for this compute module.

        Each parameter is a dict with:
        - name: internal name (passed to compute())
        - label: display name for UI
        - type: 'int', 'float', 'bool', 'enum'
        - default: default value
        - min/max: bounds (for numbers)
        - step: increment (for numbers)
        - options: list of choices (for enum)
        - suffix: unit label (optional)
        """
        return []

    def run(
        self,
        run: RunData,
        instance_name: str | None = None,
        export: bool = False,
        project_dir: Any = None,  # Avoid circular type hint issues
        **params,
    ) -> pd.DataFrame:
        """
        Public API: resolve inputs, validate, then compute outputs.

        Args:
            run: The RunData to compute on
            instance_name: Instance name for looking up channel bindings
            export: Whether to export results to project/exports
            project_dir: Project root, forwarded to compute() for settings and used for exports
            **params: Runtime parameter values (from get_parameters)

        Returns:
            DataFrame with computed metrics
        """
        inputs = self._resolve_inputs(run, instance_name)
        result = self.compute(run, **inputs, project_dir=project_dir, **params)

        if export:
            if not project_dir:
                print("Warning: Export requested but project_dir not provided.")
            else:
                self._export_result(run, instance_name, result, project_dir, params)

        return result

    def _export_result(
        self,
        run: RunData,
        instance_name: str | None,
        df: pd.DataFrame,
        project_dir: Any,
        params: dict,
    ) -> None:
        """Export results and provenance to project exports directory."""
        if df is None or df.empty:
            return

        from tracengine.data.loader import save_compute_export, save_compute_provenance
        from pathlib import Path

        project_dir = Path(project_dir)
        exports_dir = project_dir / "exports"

        # Ensure instance name (default to class name if None)
        inst_name = instance_name or self.name

        # Get run ID parts
        run_id = (
            run.subject,
            run.session,
            run.metadata.get("task", "unknown"),
            run.metadata.get("condition", "unknown"),
            run.run,
        )

        # Save CSV
        csv_path = save_compute_export(exports_dir, run_id, inst_name, df)
        print(f"Exported metrics to: {csv_path.name}")

        # Save Provenance
        prov_path = save_compute_provenance(
            exports_dir,
            run_id,
            inst_name,
            run.run_config,
            params,
            self.name,
            self.version,
        )
        print(f"Exported provenance to: {prov_path.name}")

    @abstractmethod
    def compute(self, run: RunData, **inputs) -> pd.DataFrame:
        """
        Compute metrics from resolved inputs.

        Args:
            run: The RunData
            **inputs: Resolved channels as (time, values) tuples,
                      resolved events as lists, plus runtime parameters

        Returns:
            DataFrame with computed metrics
        """
        pass

    def _resolve_inputs(self, run: RunData, instance_name: str | None = None) -> dict:
        """Resolve all required channels and events."""
        resolved = {}

        # Resolve channels
        if self.required_channels:
            channel_refs = resolve_all(
                run, self.required_channels, run.run_config, instance_name
            )
            for role, channel in channel_refs.items():
                t, y = run.get_channel_data(channel)
                resolved[role] = (t, y)

        # Resolve events
        if self.required_events:
            event_data = resolve_events(
                run, self.required_events, run.run_config, instance_name
            )
            resolved.update(event_data)

        return resolved
