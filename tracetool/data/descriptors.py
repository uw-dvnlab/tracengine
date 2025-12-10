import pandas as pd
from dataclasses import dataclass


@dataclass
class Signal:
    name: str  # "adhawk_pupils"
    modality: str  # "pupils"
    data: pd.DataFrame
    sampling_rate: float | None


@dataclass
class EventSeries:
    name: str  # "saccade detections"
    events: pd.DataFrame  # columns: ["time", "type", ...]
    source: str  # "detector:saccade_detector"


@dataclass
class RunData:
    subject: str
    session: str
    start_time: pd.DatetimeIndex
    run: str
    metadata: dict[str, str]
    raw_signals: dict[str, Signal]
    detections: dict[str, EventSeries]
    annotations: pd.DataFrame | None
    metrics: pd.DataFrame | None

    def get_signal(self, modality, col):
        time_raw = pd.to_datetime(
            self.raw_signals[modality]["utc"], utc=True, format="mixed"
        )
        time_seconds = (time_raw - self.start_time).dt.total_seconds()

        return (
            time_seconds,
            self.raw_signals[modality][col].values,
        )
