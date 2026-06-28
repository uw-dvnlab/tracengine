"""
TRACE Project Configuration

Dataclasses for project and pipeline configuration.
"""

from typing import Any
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class ProjectPaths:
    """Paths within a project folder."""

    data: Path  # Local data files (or empty if using data_source)
    derived: Path  # Annotations, provenance, metrics
    plugins: Path  # Custom annotators and compute modules
    pipelines: Path  # Pipeline configuration files
    exports: Path  # Aggregated results

    @classmethod
    def from_root(cls, root: Path) -> "ProjectPaths":
        """Create default paths relative to project root."""
        return cls(
            data=root / "data",
            derived=root / "derived",
            plugins=root / "plugins",
            pipelines=root / "pipelines",
            exports=root / "exports",
        )


@dataclass
class PreprocessingStep:
    """A preprocessing operation to apply to a channel."""

    channel: str  # "group:channel_name"
    operations: list[dict]  # [{op: "butter", cutoff: 10, order: 4}, ...]


@dataclass
class AnnotatorStep:
    """Configuration for running an annotator."""

    name: str  # Annotator class name
    channel_bindings: dict[str, str] | None = None  # Override defaults
    save_to: str | None = None  # Output path template


@dataclass
class ComputeStep:
    """Configuration for running a compute module."""

    name: str  # Compute class name
    depends_on: list[str] = field(default_factory=list)  # Annotator names
    channel_bindings: dict[str, str] | None = None  # Override defaults
    output: str | None = None  # Output path template


@dataclass
class ExportConfig:
    """Configuration for exporting results."""

    aggregate: str | None = None  # Path for aggregated metrics
    format: Literal["csv", "json", "parquet"] = "csv"


@dataclass
class PipelineConfig:
    """Complete pipeline configuration."""

    name: str
    description: str = ""
    preprocessing: list[PreprocessingStep] = field(default_factory=list)
    annotators: list[AnnotatorStep] = field(default_factory=list)
    compute: list[ComputeStep] = field(default_factory=list)
    export: ExportConfig | None = None


@dataclass
class ProjectConfig:
    """
    Project-level configuration.

    Loaded from trace-project.yaml in the project root.
    """

    name: str
    root: Path
    paths: ProjectPaths
    data_source: Path | str | None = (
        None  # External session path (overrides paths.data)
    )
    default_channel_bindings: dict[str, str] = field(default_factory=dict)
    default_pipeline: str | None = None
    version: str = "1.0"
    device_settings: dict[str, Any] = field(default_factory=dict)

    def get_data_path(self) -> Path:
        """Get the effective data path (data_source if set, else paths.data)."""
        if self.data_source:
            return Path(self.data_source)
        return self.paths.data

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for YAML serialization."""

        def _to_path_str(p: Path) -> str:
            try:
                # Try to store as relative path to keep config portable
                return str(p.relative_to(self.root))
            except ValueError:
                # Fallback to absolute if not relative to root
                return str(p)

        return {
            "name": self.name,
            "version": self.version,
            "data_source": str(self.data_source) if self.data_source else None,
            "paths": {
                "data": _to_path_str(self.paths.data),
                "derived": _to_path_str(self.paths.derived),
                "plugins": _to_path_str(self.paths.plugins),
                "pipelines": _to_path_str(self.paths.pipelines),
                "exports": _to_path_str(self.paths.exports),
            },
            "default_channel_bindings": self.default_channel_bindings,
            "default_pipeline": self.default_pipeline,
            "device_settings": self.device_settings,
        }
