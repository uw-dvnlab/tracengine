"""
TRACE Channel Utilities

Central utilities for creating and managing derived channels.
All signal processing that affects annotation or compute must go through here.

GUIDING RULE: If a transformation affects annotation or compute,
it must produce a persistent derived channel.
"""

from tracengine.data.descriptors import (
    RunData,
    Channel,
    ChannelProvenance,
)
from tracengine.processing.registry import get_processor
from tracengine.utils.signal_processing import compute_derivative
from datetime import datetime
import pandas as pd
import numpy as np


# =============================================================================
# Naming Convention
# =============================================================================

# Format: {base}_{op1}_{op2}...
# | Operation         | Suffix       | Example            |
# |-------------------|--------------|-------------------|
# | Butterworth       | _bf{cutoff}  | X_bf10            |
# | Savitzky-Golay    | _sg          | X_sg              |
# | Rolling Mean      | _rm{window}  | X_rm5             |
# | Derivative        | _dN          | X_d1, X_d2        |
# | Detrend           | _dt          | X_dt              |
# | Resample          | _rs{hz}      | X_rs100           |


def get_derived_name(base_name: str, operation: str, params: dict) -> str:
    """
    Generate a derived channel name based on operation and parameters.

    Args:
        base_name: The source channel name (may already have suffixes)
        operation: The operation being applied
        params: Operation parameters

    Returns:
        New channel name with appropriate suffix
    """
    if operation == "butter":
        cutoff = int(params.get("cutoff", 10))
        return f"{base_name}_bf{cutoff}"
    elif operation == "savitzky_golay":
        return f"{base_name}_sg"
    elif operation == "rolling_mean":
        window = int(params.get("window_size", 5))
        return f"{base_name}_rm{window}"
    elif operation == "derivative":
        order = int(params.get("order", 1))
        return f"{base_name}_d{order}"
    elif operation == "detrend":
        return f"{base_name}_dt"
    elif operation == "resample":
        hz = int(params.get("target_hz", 100))
        return f"{base_name}_rs{hz}"
    else:
        # Generic suffix
        return f"{base_name}_{operation}"


# =============================================================================
# Derived Channel Creation
# =============================================================================


def create_derived_channel(
    run: RunData,
    group_name: str,
    source_channel: str,
    operation: str,
    params: dict,
    custom_suffix: str | None = None,
) -> Channel:
    """
    Create a derived channel and store it in the RunData.

    This is the central function for all signal processing that should
    persist and be available to annotators/compute.

    Args:
        run: The RunData to modify
        group_name: Name of the SignalGroup (modality)
        source_channel: Name of the source channel
        operation: Operation to apply ("butter", "derivative", etc.)
        params: Operation-specific parameters
        custom_suffix: Optional custom name instead of auto-generated

    Returns:
        Channel reference to the new derived channel

    Raises:
        KeyError: If group or source channel not found
        ValueError: If operation fails
    """
    if group_name not in run.signals:
        raise KeyError(f"SignalGroup '{group_name}' not found in run")

    signal_group = run.signals[group_name]

    if source_channel not in signal_group.data.columns:
        raise KeyError(f"Channel '{source_channel}' not found in group '{group_name}'")

    # Generate derived name
    if custom_suffix:
        derived_name = f"{source_channel}_{custom_suffix}"
    else:
        derived_name = get_derived_name(source_channel, operation, params)

    # Get source data
    source_data = signal_group.data[source_channel].to_numpy()

    # Handle missing values if requested
    if params.get("interpolate_missing", False):
        # Interpolate NaNs: linear for interior, bfill/ffill for edges
        interp_series = pd.Series(source_data).interpolate().bfill().ffill()
        source_data = interp_series.to_numpy()
        print(
            f"[create_derived_channel] Interpolated NaNs, remaining: {np.sum(np.isnan(source_data))}"
        )

    # Apply operation
    if operation == "derivative":
        time_raw = pd.to_datetime(signal_group.data["utc"], utc=True, format="mixed")
        t_sec = (time_raw - run.start_time).dt.total_seconds().to_numpy()
        order = params.get("order", 1)
        result = compute_derivative(t_sec, source_data, order=order)
    else:
        # Use processor registry for filters
        processor_cls = get_processor(operation)
        if processor_cls is None:
            raise ValueError(f"Unknown operation: {operation}")

        processor = processor_cls()
        fs = signal_group.sampling_rate or 100.0
        # Filter out non-processor params
        processor_params = {
            k: v for k, v in params.items() if k != "interpolate_missing"
        }
        result = processor.process(source_data, fs, **processor_params)

    # Store result in SignalGroup
    signal_group.data[derived_name] = result

    # Create Channel reference
    channel = Channel.from_parts(group_name, derived_name)

    # Register provenance
    parent_id = f"{group_name}:{source_channel}"
    run.channel_provenance[channel.id] = ChannelProvenance(
        parents=[parent_id],
        operation=operation,
        parameters=params,
        timestamp=datetime.now(),
    )

    return channel


def create_filter_channel(
    run: RunData,
    group_name: str,
    source_channel: str,
    filter_type: str,
    **filter_params,
) -> Channel:
    """
    Convenience function to create a filtered channel.

    Args:
        run: The RunData to modify
        group_name: Name of the SignalGroup
        source_channel: Name of the source channel
        filter_type: Filter type ("butter", "savitzky_golay", "rolling_mean")
        **filter_params: Filter-specific parameters

    Returns:
        Channel reference to the filtered channel
    """
    return create_derived_channel(
        run=run,
        group_name=group_name,
        source_channel=source_channel,
        operation=filter_type,
        params=filter_params,
    )


def create_averaged_channel(
    run: RunData,
    source_channels: list[tuple[str, str]],
    target_group: str,
    output_name: str,
    interpolate_missing: bool = True,
) -> Channel:
    """
    Create an averaged channel from multiple source channels.

    Args:
        run: The RunData to modify
        source_channels: List of (group_name, channel_name) tuples
        target_group: Group to store the result in
        output_name: Name for the new averaged channel
        interpolate_missing: Whether to interpolate NaNs before averaging

    Returns:
        Channel reference to the averaged channel

    Raises:
        KeyError: If any source channel is not found
        ValueError: If channels have different lengths
    """
    if len(source_channels) < 2:
        raise ValueError("Need at least 2 channels to average")

    # Collect data from all source channels
    data_arrays = []
    parent_ids = []

    for group_name, channel_name in source_channels:
        if group_name not in run.signals:
            raise KeyError(f"SignalGroup '{group_name}' not found")

        signal_group = run.signals[group_name]

        if channel_name not in signal_group.data.columns:
            raise KeyError(f"Channel '{channel_name}' not found in '{group_name}'")

        data = signal_group.data[channel_name].to_numpy().copy()

        if interpolate_missing:
            interp_series = pd.Series(data).interpolate().bfill().ffill()
            data = interp_series.to_numpy()

        data_arrays.append(data)
        parent_ids.append(f"{group_name}:{channel_name}")

    # Verify all arrays have same length
    lengths = [len(arr) for arr in data_arrays]
    if len(set(lengths)) > 1:
        raise ValueError(f"Channel lengths differ: {lengths}")

    # Compute average
    stacked = np.stack(data_arrays, axis=0)
    averaged = np.nanmean(stacked, axis=0)

    # Store in target group
    if target_group not in run.signals:
        raise KeyError(f"Target group '{target_group}' not found")

    run.signals[target_group].data[output_name] = averaged

    # Create Channel reference
    channel = Channel.from_parts(target_group, output_name)

    # Register provenance
    run.channel_provenance[channel.id] = ChannelProvenance(
        parents=parent_ids,
        operation="average",
        parameters={"interpolate_missing": interpolate_missing},
        timestamp=datetime.now(),
    )

    return channel


def create_derivative_channel(
    run: RunData,
    group_name: str,
    source_channel: str,
    order: int = 1,
) -> Channel:
    """
    Convenience function to create a derivative channel.

    Args:
        run: The RunData to modify
        group_name: Name of the SignalGroup
        source_channel: Name of the source channel
        order: Derivative order (1=velocity, 2=acceleration)

    Returns:
        Channel reference to the derivative channel
    """
    return create_derived_channel(
        run=run,
        group_name=group_name,
        source_channel=source_channel,
        operation="derivative",
        params={"order": order},
    )


# =============================================================================
# Batch Operations
# =============================================================================


def apply_processing_chain(
    run: RunData,
    group_name: str,
    source_channel: str,
    operations: list[tuple[str, dict]],
) -> Channel:
    """
    Apply a chain of operations to create a derived channel.

    Args:
        run: The RunData to modify
        group_name: Name of the SignalGroup
        source_channel: Starting channel name
        operations: List of (operation, params) tuples

    Returns:
        Channel reference to the final derived channel

    Example:
        # Filter then derivative
        channel = apply_processing_chain(
            run, "tablet_motion", "X",
            [("butter", {"cutoff": 10}), ("derivative", {"order": 1})]
        )
        # Creates: X → X_bf10 → X_bf10_d1
    """
    current_channel = source_channel

    for operation, params in operations:
        channel = create_derived_channel(
            run=run,
            group_name=group_name,
            source_channel=current_channel,
            operation=operation,
            params=params,
        )
        current_channel = channel.name

    return channel


def save_derived_channels(run: RunData, derived_dir) -> None:
    """
    Save all channel provenance for a run.

    Args:
        run: The RunData with provenance to save
        derived_dir: Path to the derived directory
    """
    from tracengine.data.loader import save_channel_provenance
    from pathlib import Path

    if not isinstance(derived_dir, Path):
        derived_dir = Path(derived_dir)

    # We need to reconstruct run_id from run
    run_id = (
        run.subject,
        run.session,
        run.metadata.get("task"),
        run.metadata.get("condition"),
        run.run,
    )

    save_channel_provenance(derived_dir, run_id, run.channel_provenance)


# =============================================================================
# Resample (whole SignalGroup)
# =============================================================================


def resample_signal_group(
    run: RunData,
    group_name: str,
    target_hz: float,
) -> None:
    """
    Resample an entire SignalGroup to a new uniform sampling rate.

    Uses interpolation so it handles both uniform and non-uniform
    (variable-rate) input correctly.

    The SignalGroup's DataFrame is replaced in-place with the resampled
    data and its sampling_rate is updated.

    Args:
        run: The RunData to modify
        group_name: Name of the SignalGroup to resample
        target_hz: Target sampling frequency in Hz

    Raises:
        KeyError: If group not found
        ValueError: If target_hz is invalid or data is too short
    """
    if group_name not in run.signals:
        raise KeyError(f"SignalGroup '{group_name}' not found in run")

    if target_hz <= 0:
        raise ValueError(f"target_hz must be positive, got {target_hz}")

    signal_group = run.signals[group_name]
    df = signal_group.data

    if "utc" not in df.columns:
        raise ValueError(f"SignalGroup '{group_name}' has no 'utc' column")

    if len(df) < 2:
        raise ValueError(f"SignalGroup '{group_name}' has fewer than 2 samples")

    # Build source time axis in seconds (relative to first sample)
    time_raw = pd.to_datetime(df["utc"], utc=True, format="mixed")
    t_origin = time_raw.iloc[0]
    t_sec = (time_raw - t_origin).dt.total_seconds().to_numpy()

    # Build new uniform time grid at target_hz
    duration = t_sec[-1] - t_sec[0]
    n_new = max(int(round(duration * target_hz)) + 1, 2)
    t_new = np.linspace(t_sec[0], t_sec[-1], n_new)

    # Interpolate each numeric channel onto the new grid
    data_channels = signal_group.list_channels()
    new_data = {}

    for col in data_channels:
        values = df[col].to_numpy(dtype=float)
        new_data[col] = np.interp(t_new, t_sec, values)

    # Interpolate utc timestamps
    t_raw_ns = time_raw.values.astype(np.int64)
    t_new_ns = np.interp(t_new, t_sec, t_raw_ns.astype(float)).astype(np.int64)
    new_utc = pd.to_datetime(t_new_ns, utc=True)

    # Build new DataFrame
    new_df = pd.DataFrame(new_data)
    new_df.insert(0, "utc", new_utc)

    # Record provenance for each channel
    old_hz = signal_group.sampling_rate or 0
    for col in data_channels:
        channel_id = f"{group_name}:{col}"
        run.channel_provenance[channel_id] = ChannelProvenance(
            parents=[channel_id],
            operation="resample",
            parameters={"target_hz": target_hz, "source_hz": old_hz},
            timestamp=datetime.now(),
        )

    # Replace in-place
    signal_group.data = new_df
    signal_group.sampling_rate = target_hz


def reset_signal_group_resample(
    run: RunData,
    group_name: str,
    data_dir,
) -> None:
    """
    Reset a signal group to its original data from disk, clearing any
    resample provenance.

    Args:
        run: The RunData to modify
        group_name: Name of the SignalGroup to reset
        data_dir: Path to the processed/ directory containing source CSVs
    """
    from pathlib import Path
    from tracengine.data.loader import (
        discover_runs,
        extract_modality,
        parse_modality_file,
    )

    if group_name not in run.signals:
        raise KeyError(f"SignalGroup '{group_name}' not found in run")

    data_dir = Path(data_dir)

    # Find the source file for this run + modality
    run_id = (
        run.subject,
        run.session,
        run.metadata.get("task"),
        run.metadata.get("condition"),
        run.run,
    )

    runs = discover_runs(data_dir)
    if run_id not in runs:
        raise FileNotFoundError(f"Run {run_id} not found in {data_dir}")

    # Find the file matching this modality
    source_file = None
    for f, kv, suffix in runs[run_id]:
        modality = extract_modality(kv, suffix)
        if modality == group_name:
            source_file = f
            break

    if source_file is None:
        raise FileNotFoundError(
            f"No source file for modality '{group_name}' in {data_dir}"
        )

    # Reload original data
    df = parse_modality_file(source_file)

    signal_group = run.signals[group_name]
    signal_group.data = df
    signal_group.sampling_rate = signal_group.estimate_sampling_rate()

    # Clear resample provenance for this group
    to_remove = [
        ch_id
        for ch_id, prov in run.channel_provenance.items()
        if prov.operation == "resample" and ch_id.startswith(f"{group_name}:")
    ]
    for ch_id in to_remove:
        del run.channel_provenance[ch_id]
