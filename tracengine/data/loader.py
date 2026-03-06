"""
TRACE Data Loader

Loads session data from BIDS-style directory structure.
Handles signal loading, annotation loading, and channel provenance.
"""

from tracengine.data.descriptors import (
    RunData,
    SignalGroup,
    Event,
    ChannelProvenance,
    RunConfig,
)
from pathlib import Path
from collections import defaultdict
from datetime import datetime
import re
import pandas as pd
import json

KV_PATTERN = re.compile(r"(?:^|_)(\w+)-([^_]+)")


# =============================================================================
# Filename Parsing
# =============================================================================


def parse_filename(path: Path):
    """Parse BIDS-style filename into key-value pairs.

    Returns:
        (kv_pairs, suffix) where suffix is text after mod- that is NOT
        a key-value pair (e.g., '_phys' in 'mod-ecg_phys' but NOT
        'run-000' in 'mod-imu_run-000').
    """
    stem = path.stem
    kv_pairs = dict(KV_PATTERN.findall(stem))

    suffix = None
    if kv_pairs.get("mod") and "_" in stem:
        after_mod = stem.split(f"mod-{kv_pairs['mod']}_", 1)[-1]
        # Only treat as suffix if it's NOT a key-value pair
        # Key-value pairs match pattern: word-value
        if after_mod and not re.match(r"^\w+-", after_mod):
            suffix = after_mod

    return kv_pairs, suffix


def extract_run_id(kv: dict) -> tuple:
    """Return only the identifying fields for the run."""
    return (
        kv.get("sub"),
        kv.get("ses"),
        kv.get("task"),
        kv.get("condition"),
        kv.get("run"),
    )


def discover_runs(data_dir: Path) -> dict:
    """Discover all runs in a data directory."""
    data_files = list(data_dir.glob("*.csv")) + list(data_dir.glob("*.tsv"))
    runs = defaultdict(list)

    for f in data_files:
        kv, suffix = parse_filename(f)
        run_id = extract_run_id(kv)
        runs[run_id].append((f, kv, suffix))

    return runs


def extract_modality(kv: dict, suffix: str | None) -> str | None:
    """Return modality name for this file (vendor + optional suffix)."""
    if "mod" not in kv:
        return None
    if suffix:
        return f"{kv['mod']}_{suffix}"
    return kv["mod"]


def _get_derived_filename_base(run_id: tuple) -> str:
    """Get the base filename for derived files."""
    sub, ses, task, cond, run_num = run_id
    return f"sub-{sub}_ses-{ses}_task-{task}_condition-{cond}_run-{run_num}"


# =============================================================================
# Annotations Persistence
# =============================================================================


def load_annotations(derived_dir: Path, run_id: tuple) -> dict[str, list[Event]]:
    """Load annotations from a JSON file in the derived directory."""
    base = _get_derived_filename_base(run_id)
    path = derived_dir / f"{base}_annotations.json"

    if not path.exists():
        return {}

    try:
        with open(path, "r") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading annotations from {path}: {e}")
        return {}

    # Handle structure variations
    annotations_dict = {}
    if "annotations" in data and isinstance(data["annotations"], dict):
        annotations_dict = data["annotations"]
    elif "annotations" not in data:
        annotations_dict = data

    # Parse events
    parsed_annotations = {}
    for group_name, event_list in annotations_dict.items():
        if not isinstance(event_list, list):
            continue

        parsed_events = []
        for ev_data in event_list:
            try:
                if "name" not in ev_data or "onset" not in ev_data:
                    continue
                if "event_type" not in ev_data:
                    ev_data["event_type"] = (
                        "interval" if "offset" in ev_data else "timepoint"
                    )

                ev = Event(
                    annotator=ev_data.get("annotator", "Unknown"),
                    name=ev_data["name"],
                    event_type=ev_data.get("event_type"),
                    onset=ev_data["onset"],
                    offset=ev_data.get("offset"),
                    confidence=ev_data.get("confidence"),
                    metadata=ev_data.get("metadata", {}),
                )
                parsed_events.append(ev)
            except Exception:
                continue

        if parsed_events:
            parsed_annotations[group_name] = parsed_events

    return parsed_annotations


# =============================================================================
# Channel Provenance Persistence
# =============================================================================


def load_channel_provenance(
    derived_dir: Path, run_id: tuple
) -> dict[str, ChannelProvenance]:
    """Load channel provenance from derived/channels.json."""
    base = _get_derived_filename_base(run_id)
    path = derived_dir / f"{base}_channels.json"

    if not path.exists():
        return {}

    try:
        with open(path, "r") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading channel provenance from {path}: {e}")
        return {}

    provenance = {}
    for channel_id, prov_data in data.items():
        try:
            provenance[channel_id] = ChannelProvenance(
                parents=prov_data.get("parents", []),
                operation=prov_data.get("operation", "unknown"),
                parameters=prov_data.get("parameters", {}),
                timestamp=(
                    datetime.fromisoformat(prov_data["timestamp"])
                    if "timestamp" in prov_data
                    else datetime.now()
                ),
            )
        except Exception:
            continue

    return provenance


def save_channel_provenance(
    derived_dir: Path, run_id: tuple, provenance: dict[str, ChannelProvenance]
) -> None:
    """Save channel provenance to derived/channels.json."""
    derived_dir.mkdir(parents=True, exist_ok=True)
    base = _get_derived_filename_base(run_id)
    path = derived_dir / f"{base}_channels.json"

    data = {}
    for channel_id, prov in provenance.items():
        data[channel_id] = {
            "parents": prov.parents,
            "operation": prov.operation,
            "parameters": prov.parameters,
            "timestamp": prov.timestamp.isoformat(),
        }

    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# =============================================================================
# Run Config Persistence
# =============================================================================


def load_run_config(derived_dir: Path, run_id: tuple) -> RunConfig | None:
    """Load run configuration from derived/run_config.json."""
    base = _get_derived_filename_base(run_id)
    path = derived_dir / f"{base}_run_config.json"

    if not path.exists():
        return None

    try:
        with open(path, "r") as f:
            data = json.load(f)
        return RunConfig(
            channel_bindings=data.get("channel_bindings", {}),
            parameters=data.get("parameters", {}),
            event_bindings=data.get("event_bindings", {}),
        )
    except Exception as e:
        print(f"Error loading run config from {path}: {e}")
        return None


def save_run_config(derived_dir: Path, run_id: tuple, config: RunConfig) -> None:
    """Save run configuration to derived/run_config.json."""
    derived_dir.mkdir(parents=True, exist_ok=True)
    base = _get_derived_filename_base(run_id)
    path = derived_dir / f"{base}_run_config.json"

    data = {
        "channel_bindings": config.channel_bindings,
        "parameters": config.parameters,
        "event_bindings": config.event_bindings,
    }

    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# =============================================================================
# Compute Output Persistence
# =============================================================================


def save_compute_export(
    exports_dir: Path, run_id: tuple, instance_name: str, df: pd.DataFrame
) -> Path:
    """
    Save compute module output DataFrame to exports directory.
    Filename: {run_base}_{instance_name}_metrics.csv
    """
    exports_dir.mkdir(parents=True, exist_ok=True)
    base = _get_derived_filename_base(run_id)
    # Sanitize instance name for filename
    safe_name = instance_name.replace(" ", "_").replace(":", "_")
    filename = f"{base}_{safe_name}_metrics.csv"
    path = exports_dir / filename

    df.to_csv(path, index=False)
    return path


def save_compute_provenance(
    exports_dir: Path,
    run_id: tuple,
    instance_name: str,
    run_config: RunConfig | None,
    params: dict,
    plugin_name: str,
    plugin_version: str,
) -> Path:
    """
    Save provenance JSON for a compute output.
    Filename: {run_base}_{instance_name}_provenance.json
    """
    exports_dir.mkdir(parents=True, exist_ok=True)
    base = _get_derived_filename_base(run_id)
    safe_name = instance_name.replace(" ", "_").replace(":", "_")
    filename = f"{base}_{safe_name}_provenance.json"
    path = exports_dir / filename

    # Extract relevant bindings for this instance
    channel_bindings = {}
    event_bindings = {}

    if run_config:
        channel_bindings = run_config.channel_bindings.get(instance_name, {})
        event_bindings = run_config.event_bindings.get(instance_name, {})

    provenance = {
        "compute_instance": instance_name,
        "plugin_name": plugin_name,
        "plugin_version": plugin_version,
        "run_id": base,  # Use base string as ID
        "timestamp": datetime.now().isoformat(),
        "channel_bindings": channel_bindings,
        "event_bindings": event_bindings,
        "parameters": params,
        "run_config_path": f"../derived/{base}_run_config.json",
    }

    with open(path, "w") as f:
        json.dump(provenance, f, indent=2)

    return path


# =============================================================================
# Signal Loading
# =============================================================================


def parse_modality_file(path: Path) -> pd.DataFrame:
    """Parse a modality CSV or TSV file."""
    try:
        sep = "\t" if path.suffix.lower() == ".tsv" else ","
        df = pd.read_csv(path, sep=sep)
    except Exception:
        df = pd.DataFrame()
    return df


# =============================================================================
# Session Loading
# =============================================================================


def load_session(path: Path, derived_dir: Path | None = None) -> list[RunData]:
    """
    Load all runs from a session directory.

    Expected structure:
        path/
        ├── processed/      # raw CSV files
        └── derived/        # annotations, provenance, configs (if derived_dir not specified)

    Args:
        path: Session data directory (containing processed/ subfolder)
        derived_dir: Optional separate path for derived outputs. If None, uses path/derived.
    """
    data_dir = path / "processed"
    if derived_dir is None:
        derived_dir = path / "derived"

    runs = discover_runs(data_dir)
    all_run_objects = []

    for run_id, files in runs.items():
        signals = {}
        raw_dfs = {}

        # Load raw data files
        for f, kv, suffix in files:
            modality = extract_modality(kv, suffix)
            df = parse_modality_file(f)
            raw_dfs[modality] = df

        if not raw_dfs:
            continue

        # Get global start time
        try:
            session_start = min(
                pd.to_datetime(df["utc"], utc=True, format="mixed").iloc[0]
                for _, df in raw_dfs.items()
                if not df.empty and "utc" in df.columns
            )
        except ValueError:
            session_start = pd.Timestamp.now(tz="UTC")

        # Create SignalGroup objects
        for modality, df in raw_dfs.items():
            sig = SignalGroup(name=modality, modality=modality, data=df)
            sig.sampling_rate = sig.estimate_sampling_rate()
            signals[modality] = sig

        # Load metadata
        run_metadata = {
            key: value
            for key, value in files[0][1].items()
            if key not in ["sub", "ses", "mod"]
        }

        # Load derived data
        annotations = load_annotations(derived_dir, run_id)
        channel_provenance = load_channel_provenance(derived_dir, run_id)
        run_config = load_run_config(derived_dir, run_id)

        run_obj = RunData(
            subject=run_id[0],
            session=run_id[1],
            start_time=session_start,
            run=run_id[4],
            metadata=run_metadata,
            signals=signals,
            annotations=annotations,
            compute=None,
            channel_provenance=channel_provenance,
            run_config=run_config,
        )

        # Recompute derived channels from provenance
        _recompute_derived_channels(run_obj)

        all_run_objects.append(run_obj)

    return all_run_objects


def _recompute_derived_channels(run: RunData) -> None:
    """
    Recompute derived channels from provenance.
    Uses topological sort to handle chained dependencies.
    Resample operations are applied first (group-level), then per-channel ops.
    """
    if not run.channel_provenance:
        return

    # ------------------------------------------------------------------
    # Phase 1: Apply resample operations (group-level, before per-channel)
    # ------------------------------------------------------------------
    from tracengine.processing.channel_utils import resample_signal_group

    resampled_groups = set()
    for channel_id, prov in run.channel_provenance.items():
        if prov.operation != "resample":
            continue
        if ":" not in channel_id:
            continue
        group_name = channel_id.split(":", 1)[0]
        if group_name in resampled_groups:
            continue  # Already resampled this group

        target_hz = prov.parameters.get("target_hz")
        if target_hz and group_name in run.signals:
            try:
                resample_signal_group(run, group_name, target_hz)
                resampled_groups.add(group_name)
            except Exception as e:
                print(f"Error resampling {group_name}: {e}")

    # ------------------------------------------------------------------
    # Phase 2: Apply per-channel operations (filters, derivatives, etc.)
    # ------------------------------------------------------------------

    # Build dependency graph and sort topologically
    sorted_channels = _topological_sort_channels(run.channel_provenance)

    # Import processing utilities (lazy import to avoid circular deps)
    from tracengine.processing.registry import get_processor
    from tracengine.utils.signal_processing import compute_derivative

    for channel_id in sorted_channels:
        prov = run.channel_provenance[channel_id]

        # Skip resample — already handled in Phase 1
        if prov.operation == "resample":
            continue

        # Parse channel_id -> group:name
        if ":" not in channel_id:
            continue
        group_name, channel_name = channel_id.split(":", 1)

        if group_name not in run.signals:
            continue

        signal_group = run.signals[group_name]

        # Get parent data
        if not prov.parents:
            continue

        parent_id = prov.parents[0]  # Primary parent
        if ":" not in parent_id:
            continue
        parent_group, parent_channel = parent_id.split(":", 1)

        if parent_group != group_name:
            continue  # Cross-group not supported yet

        if parent_channel not in signal_group.data.columns:
            continue

        parent_data = signal_group.data[parent_channel].to_numpy()

        # Apply operation
        try:
            if prov.operation == "derivative":
                time_raw = pd.to_datetime(
                    signal_group.data["utc"], utc=True, format="mixed"
                )
                t_sec = (time_raw - run.start_time).dt.total_seconds().to_numpy()
                order = prov.parameters.get("order", 1)
                result = compute_derivative(t_sec, parent_data, order=order)
            else:
                # Use processor registry for filters
                processor_cls = get_processor(prov.operation)
                if processor_cls:
                    processor = processor_cls()
                    fs = signal_group.sampling_rate or 100.0
                    result = processor.process(parent_data, fs, **prov.parameters)
                else:
                    continue

            # Store result
            signal_group.data[channel_name] = result
        except Exception as e:
            print(f"Error recomputing {channel_id}: {e}")
            continue


def _topological_sort_channels(provenance: dict[str, ChannelProvenance]) -> list[str]:
    """Sort channel IDs by dependency order (parents first)."""
    # Build adjacency
    graph = {ch: [] for ch in provenance}
    for ch, prov in provenance.items():
        for parent in prov.parents:
            if parent in graph:
                graph[parent].append(ch)

    # Kahn's algorithm
    in_degree = {ch: 0 for ch in provenance}
    for ch, prov in provenance.items():
        for parent in prov.parents:
            if parent in in_degree:
                in_degree[ch] += 1

    queue = [ch for ch, deg in in_degree.items() if deg == 0]
    result = []

    while queue:
        ch = queue.pop(0)
        result.append(ch)
        for neighbor in graph.get(ch, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    return result


# =============================================================================
# Utility Functions
# =============================================================================


def list_modalities(session_path: Path) -> list[str]:
    """List all modalities in a session."""
    data_dir = session_path / "processed"
    data_files = list(data_dir.glob("*.csv")) + list(data_dir.glob("*.tsv"))
    modalities = set()
    for f in data_files:
        kv, suffix = parse_filename(f)
        mod_name = extract_modality(kv, suffix)
        if mod_name:
            modalities.add(mod_name)
    return sorted(modalities)


def get_modality_channels(run_object: RunData) -> dict[str, list[str]]:
    """Get all channels for each modality in a run."""
    modality_channels = {}
    for modality, signal_group in run_object.signals.items():
        modality_channels[modality] = signal_group.list_channels()
    return modality_channels


# =============================================================================
# Project-Aware Loading
# =============================================================================


def load_session_from_project(project_config) -> list[RunData]:
    """
    Load all runs from a project, applying project defaults.

    Args:
        project_config: ProjectConfig object from tracengine.project

    Returns:
        List of RunData objects with project defaults applied
    """
    # Use project's derived directory for loading derived outputs
    runs = load_session(
        project_config.get_data_path(), derived_dir=project_config.paths.derived
    )

    # Apply default channel bindings from project to runs without config
    if project_config.default_channel_bindings:
        for run in runs:
            if run.run_config is None:
                run.run_config = RunConfig(
                    channel_bindings=project_config.default_channel_bindings.copy()
                )
            else:
                # Merge: run-specific bindings override project defaults
                merged = project_config.default_channel_bindings.copy()
                merged.update(run.run_config.channel_bindings)
                run.run_config.channel_bindings = merged

    return runs
