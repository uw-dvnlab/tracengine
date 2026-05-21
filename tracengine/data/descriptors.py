"""
TRACE Data Descriptors

Core data model for signals, channels, events, and run data.

GUIDING RULE: If a transformation affects annotation or compute,
it must produce a persistent derived channel.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


# =============================================================================
# Specs - Declarative requirements for plugins
# =============================================================================


@dataclass(frozen=True)
class EventSpec:
    """Declares what kind of event a plugin requires."""

    event_type: str  # semantic type (movement, saccade, etc.)
    kind: Literal["interval", "timepoint"]


@dataclass(frozen=True)
class ChannelSpec:
    """
    Declares what channel a plugin requires.
    Used by both AnnotatorBase and ComputeBase for unified resolution.
    """

    semantic_role: str  # e.g. "trunk_angular_velocity", "stylus_x"
    allow_derived: bool = True  # if True, resolver may pick derived channels


# Legacy alias for backward compatibility during migration
SignalSpec = ChannelSpec


# =============================================================================
# Channel System
# =============================================================================


@dataclass(frozen=True)
class Channel:
    """
    Reference to a column in a SignalGroup.
    Channels do not store data - they reference columns.

    ID format: "group_name:channel_name" (e.g. "tablet_motion:X_bf10_d1")
    """

    id: str  # "tablet_motion:X_bf10_d1"
    group: str  # "tablet_motion"
    name: str  # "X_bf10_d1"

    @classmethod
    def from_parts(cls, group: str, name: str) -> "Channel":
        return cls(id=f"{group}:{name}", group=group, name=name)


@dataclass
class ChannelProvenance:
    """
    Records how a derived channel was created.
    Stored in RunData.channel_provenance, keyed by channel ID.
    """

    parents: list[str]  # parent channel IDs
    operation: str  # "butter", "derivative", "detrend", etc.
    parameters: dict  # operation-specific params
    timestamp: datetime = field(default_factory=datetime.now)


# =============================================================================
# Signal Group (replaces Signal)
# =============================================================================


@dataclass
class SignalGroup:
    """
    Container for all channels from one modality.
    Columns in `data` are individual channels.

    Example: SignalGroup for "tablet_motion" might have columns:
        X, Y, X_bf10, X_bf10_d1, etc.
    """

    name: str  # e.g. "tablet_motion"
    modality: str  # e.g. "tablet_motion"
    data: pd.DataFrame  # columns = channels, must include "utc"
    sampling_rate: float | None = None

    def estimate_sampling_rate(self) -> float | None:
        """Estimate sampling rate from the 'utc' column."""
        if self.data is None or "utc" not in self.data.columns:
            return None

        time_raw = pd.to_datetime(self.data["utc"], utc=True, format="mixed")
        if len(time_raw) < 2:
            return None

        dt = np.median(np.diff(time_raw.values.astype("datetime64[ns]")).astype(np.int64)) / 1e9
        if dt <= 0:
            return None

        return 1.0 / dt

    def get_channel(self, channel_name: str) -> Channel:
        """Get a Channel reference for a column in this group."""
        if channel_name not in self.data.columns:
            raise KeyError(f"Channel '{channel_name}' not in group '{self.name}'")
        return Channel.from_parts(self.name, channel_name)

    def list_channels(self) -> list[str]:
        """List all non-time columns as channel names."""
        return [
            col
            for col in self.data.columns
            if col.lower() not in ("utc", "time", "timestamp")
        ]


# Legacy alias for backward compatibility during migration
Signal = SignalGroup


# =============================================================================
# Events
# =============================================================================


@dataclass
class Event:
    """A detected or annotated event in the data."""

    annotator: str
    name: str
    event_type: str
    onset: float  # seconds relative to run start
    offset: float | None  # None for timepoint events
    confidence: float | None
    metadata: dict[str, str]


# =============================================================================
# Run Configuration
# =============================================================================


@dataclass
class RunConfig:
    """
    Per-run configuration that binds ChannelSpecs to resolved channels.
    Persisted to derived/run_config.json.

    Bindings are scoped by instance name:
        channel_bindings = {
            "PeakAnnotator_X": {"signal": "tablet_motion:X"},
            "SummaryStats_vel": {"signal": "optotrak_motion:velocity"}
        }
    """

    channel_bindings: dict[str, dict[str, str]] = field(
        default_factory=dict
    )  # instance_name -> role -> channel_id

    parameters: dict[str, dict[str, any]] = field(
        default_factory=dict
    )  # instance_name -> param_name -> value

    event_bindings: dict[str, dict[str, str]] = field(
        default_factory=dict
    )  # instance_name -> role -> annotation_group_name


# =============================================================================
# Run Data
# =============================================================================


@dataclass
class RunData:
    """
    Complete data for a single run/trial.
    This is the primary data container passed to annotators and compute modules.
    """

    subject: str
    session: str
    start_time: pd.Timestamp
    run: str
    metadata: dict[str, str]
    signals: dict[str, SignalGroup]  # modality -> SignalGroup
    annotations: dict[str, list[Event]]
    compute: dict[str, pd.DataFrame] | None
    channel_provenance: dict[str, ChannelProvenance] = field(default_factory=dict)
    run_config: RunConfig | None = None

    # Legacy property for backward compatibility
    @property
    def raw_signals(self) -> dict[str, SignalGroup]:
        """Deprecated: Use 'signals' instead."""
        return self.signals

    def get_signal(self, modality: str, channel: str) -> tuple[np.ndarray, np.ndarray]:
        """
        Get time and value arrays for a channel.

        Returns:
            (time_seconds, values) - time is relative to run start
        """
        if modality not in self.signals:
            return np.array([]), np.array([])

        signal_group = self.signals[modality]
        df = signal_group.data

        if channel not in df.columns:
            return np.array([]), np.array([])

        time_raw = pd.to_datetime(df["utc"], utc=True, format="mixed")
        time_seconds = (time_raw - self.start_time).dt.total_seconds().to_numpy()

        return time_seconds, df[channel].to_numpy()

    def get_channel_data(self, channel: Channel) -> tuple[np.ndarray, np.ndarray]:
        """Get time and values for a Channel object."""
        return self.get_signal(channel.group, channel.name)
