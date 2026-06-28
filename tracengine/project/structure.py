"""
TRACE Project Structure

Project folder validation, initialization, and loading.
"""

import yaml
from pathlib import Path
from typing import Any

from tracengine.project.config import (
    ProjectConfig,
    ProjectPaths,
    PipelineConfig,
    PreprocessingStep,
    AnnotatorStep,
    ComputeStep,
    ExportConfig,
)


REQUIRED_FOLDERS = ["data", "derived"]
OPTIONAL_FOLDERS = [
    "plugins",
    "plugins/annotators",
    "plugins/compute",
    "pipelines",
    "exports",
    "notebooks",
]
PROJECT_MANIFEST = "trace-project.yaml"


class ProjectValidationError(Exception):
    """Raised when project structure is invalid."""

    pass


def validate_project(path: Path) -> list[str]:
    """
    Validate a project folder structure.

    Args:
        path: Path to project root

    Returns:
        List of warning messages (empty if fully valid)

    Raises:
        ProjectValidationError: If critical structure is missing
    """
    path = Path(path)
    errors = []
    warnings = []

    if not path.exists():
        raise ProjectValidationError(f"Project path does not exist: {path}")

    if not path.is_dir():
        raise ProjectValidationError(f"Project path is not a directory: {path}")

    # Check required folders
    for folder in REQUIRED_FOLDERS:
        folder_path = path / folder
        if not folder_path.exists():
            errors.append(f"Missing required folder: {folder}")

    if errors:
        raise ProjectValidationError(
            f"Invalid project structure:\n" + "\n".join(f"  - {e}" for e in errors)
        )

    # Check optional folders
    for folder in OPTIONAL_FOLDERS:
        folder_path = path / folder
        if not folder_path.exists():
            warnings.append(f"Optional folder not found: {folder}")

    # Check for manifest
    manifest_path = path / PROJECT_MANIFEST
    if not manifest_path.exists():
        warnings.append("No " + PROJECT_MANIFEST + " found; using defaults")

    return warnings


def init_project(path: Path, name: str, device_settings: dict | None = None) -> ProjectConfig:
    """
    Initialize a new project folder structure.

    Args:
        path: Path to project root (will be created if doesn't exist)
        name: Project name
        device_settings: Optional dict of device calibration settings
                         (e.g. tablet_dpi, device_pixel_ratio)

    Returns:
        ProjectConfig for the new project
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)

    # Create all folders
    for folder in REQUIRED_FOLDERS + OPTIONAL_FOLDERS:
        (path / folder).mkdir(parents=True, exist_ok=True)

    # Create default manifest
    paths = ProjectPaths.from_root(path)
    config = ProjectConfig(
        name=name,
        root=path,
        paths=paths,
        default_channel_bindings={},
        default_pipeline=None,
        device_settings=device_settings or {},
    )

    # Write manifest
    manifest_path = path / PROJECT_MANIFEST
    manifest_data = {
        "name": config.name,
        "version": config.version,
        "data_source": None,  # Set to external path if data is elsewhere
        "paths": {
            "data": str(paths.data.relative_to(path)),
            "derived": str(paths.derived.relative_to(path)),
            "plugins": str(paths.plugins.relative_to(path)),
            "pipelines": str(paths.pipelines.relative_to(path)),
            "exports": str(paths.exports.relative_to(path)),
        },
        "default_channel_bindings": {},
        "default_pipeline": None,
        "device_settings": device_settings or {},
    }

    with open(manifest_path, "w") as f:
        yaml.dump(manifest_data, f, default_flow_style=False, sort_keys=False)

    # Create a sample pipeline template
    sample_pipeline = path / "pipelines" / "example.yaml"
    sample_pipeline_data = {
        "name": "example_pipeline",
        "description": "Example pipeline configuration",
        "preprocessing": [],
        "annotators": [],
        "compute": [],
        "export": {"aggregate": None, "format": "csv"},
    }
    with open(sample_pipeline, "w") as f:
        yaml.dump(sample_pipeline_data, f, default_flow_style=False, sort_keys=False)

    # Copy template notebooks for researchers
    _copy_template_notebooks(path / "notebooks")

    return config


def _copy_template_notebooks(notebooks_dir: Path) -> None:
    """Copy template notebooks from tracengine/templates to project notebooks folder."""
    import shutil

    # Locate bundled templates relative to this file
    templates_dir = Path(__file__).parent.parent / "templates"

    if not templates_dir.exists():
        return  # Templates not available (e.g., minimal install)

    # Copy .ipynb notebooks (preferred) and .py cell-format notebooks
    for pattern in ["*.ipynb", "develop_*.py"]:
        for template_file in templates_dir.glob(pattern):
            dest = notebooks_dir / template_file.name
            if not dest.exists():
                shutil.copy(template_file, dest)


def set_config_data_source(config: ProjectConfig, data_source: Path):
    config.data_source = data_source
    return config


def load_project(path: Path) -> ProjectConfig:
    """
    Load a project from disk.

    If no trace-project.yaml exists, uses default structure.

    Args:
        path: Path to project root

    Returns:
        ProjectConfig for the project

    Raises:
        ProjectValidationError: If project structure is invalid
    """
    path = Path(path)
    validate_project(path)  # Raises if invalid

    manifest_path = path / PROJECT_MANIFEST
    if manifest_path.exists():
        with open(manifest_path) as f:
            data = yaml.safe_load(f) or {}
        return _parse_project_config(path, data)
    else:
        # Use defaults
        return ProjectConfig(
            name=path.name,
            root=path,
            paths=ProjectPaths.from_root(path),
            default_channel_bindings={},
            default_pipeline=None,
        )


def save_project(project_root: Path, config: ProjectConfig):
    """
    Save a project to disk.

    Args:
        project_root: Path to project root
        config: ProjectConfig to save
    """
    project_root = Path(project_root)
    validate_project(project_root)  # Raises if invalid

    manifest_path = project_root / PROJECT_MANIFEST
    with open(manifest_path, "w") as f:
        yaml.dump(config.to_dict(), f, default_flow_style=False, sort_keys=False)


def _parse_project_config(root: Path, data: dict[str, Any]) -> ProjectConfig:
    """Parse a trace-project.yaml into ProjectConfig."""
    paths_data = data.get("paths", {})
    paths = ProjectPaths(
        data=root / paths_data.get("data", "data"),
        derived=root / paths_data.get("derived", "derived"),
        plugins=root / paths_data.get("plugins", "plugins"),
        pipelines=root / paths_data.get("pipelines", "pipelines"),
        exports=root / paths_data.get("exports", "exports"),
    )

    # Parse data_source - can be absolute or relative path
    data_source_raw = data.get("data_source")
    data_source = None
    if data_source_raw:
        ds_path = Path(data_source_raw)
        if ds_path.is_absolute():
            data_source = ds_path
        else:
            # Relative to project root
            data_source = root / ds_path

    return ProjectConfig(
        name=data.get("name", root.name),
        root=root,
        paths=paths,
        data_source=data_source,
        default_channel_bindings=data.get("default_channel_bindings", {}),
        default_pipeline=data.get("default_pipeline"),
        version=data.get("version", "1.0"),
        device_settings=data.get("device_settings", {}),
    )


def load_pipeline(path: Path) -> PipelineConfig:
    """
    Load a pipeline configuration from a YAML file.

    Args:
        path: Path to pipeline YAML file

    Returns:
        PipelineConfig
    """
    with open(path) as f:
        data = yaml.safe_load(f)

    preprocessing = [
        PreprocessingStep(
            channel=step["channel"],
            operations=step.get("operations", []),
        )
        for step in data.get("preprocessing", [])
    ]

    annotators = [
        AnnotatorStep(
            name=step["name"],
            channel_bindings=step.get("channel_bindings"),
            save_to=step.get("save_to"),
        )
        for step in data.get("annotators", [])
    ]

    compute = [
        ComputeStep(
            name=step["name"],
            depends_on=step.get("depends_on", []),
            channel_bindings=step.get("channel_bindings"),
            output=step.get("output"),
        )
        for step in data.get("compute", [])
    ]

    export_data = data.get("export")
    export = None
    if export_data:
        export = ExportConfig(
            aggregate=export_data.get("aggregate"),
            format=export_data.get("format", "csv"),
        )

    return PipelineConfig(
        name=data.get("name", path.stem),
        description=data.get("description", ""),
        preprocessing=preprocessing,
        annotators=annotators,
        compute=compute,
        export=export,
    )
