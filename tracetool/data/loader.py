# %%
from tracetool.data.descriptors import RunData
from pathlib import Path
from collections import defaultdict
import re
import pandas as pd

KV_PATTERN = re.compile(r"(?:^|_)(\w+)-([^_]+)")


def parse_filename(path: Path):
    stem = path.stem
    kv_pairs = dict(KV_PATTERN.findall(stem))

    # The part after mod-X_YYY
    # If there is final modality descriptor after an underscore
    if kv_pairs.get("mod") and "_" in stem:
        after_mod = stem.split(f"mod-{kv_pairs['mod']}_", 1)[-1]
    else:
        after_mod = None

    return kv_pairs, after_mod


def extract_run_id(kv: dict):
    """Return only the identifying fields for the run."""
    return (
        kv.get("sub"),
        kv.get("ses"),
        kv.get("task"),
        kv.get("condition"),
        kv.get("run"),
    )


def discover_runs(data_dir: Path):
    data_files = list(data_dir.glob("*.csv"))

    runs = defaultdict(list)

    for f in data_files:
        kv, suffix = parse_filename(f)
        run_id = extract_run_id(kv)
        runs[run_id].append((f, kv, suffix))

    return runs


def extract_modality(kv: dict, suffix: str | None):
    """Return modality name for this file (vendor + optional suffix)"""
    if "mod" not in kv:
        return None
    if suffix:
        return f"{kv['mod']}_{suffix}"
    return kv["mod"]


def parse_modality_file(path: Path) -> pd.DataFrame:
    """
    Stub for parsing a modality CSV.
    Replace with real parsing logic later.
    """
    try:
        df = pd.read_csv(path)
    except Exception:
        df = pd.DataFrame()
    return df


def load_session(path: Path):
    data_dir = path / "processed"
    derived_dir = path / "derived"

    runs = discover_runs(data_dir)

    all_run_objects = []

    for run_id, files in runs.items():
        signals = {}
        for f, kv, suffix in files:
            modality = extract_modality(kv, suffix)
            signals[modality] = parse_modality_file(f)  # <-- your parser

        # get global start time
        session_start = min(
            pd.to_datetime(df["utc"], utc=True, format="mixed").iloc[0]
            for _, df in signals.items()
        )

        # get metadata
        run_metadata = {
            key: value
            for key, value in files[0][1].items()
            if not key in ["sub", "ses", "mod"]
        }

        # TO IMPLEMENT
        # det = load_detections(derived_dir, run_id)
        # ann = load_annotations(derived_dir, run_id)
        # met = load_metrics(derived_dir, run_id)

        run_obj = RunData(
            subject=run_id[0],
            session=run_id[1],
            start_time=session_start,
            run=run_id[4],
            metadata=run_metadata,
            raw_signals=signals,
            detections={},
            annotations=None,
            metrics=None,
        )
        all_run_objects.append(run_obj)

    return all_run_objects


def list_modalities(session_path: Path):
    data_dir = session_path / "processed"
    data_files = list(data_dir.glob("*.csv"))
    modalities = set()
    for f in data_files:
        kv, suffix = parse_filename(f)
        mod_name = extract_modality(kv, suffix)
        if mod_name:
            modalities.add(mod_name)
    return sorted(modalities)


def get_modality_columns(run_object):
    modality_plot_signals = {}
    for modality, signal in run_object.raw_signals.items():
        mod_columns = [
            col
            for col in signal.columns
            if not "time" in col.lower() and not "utc" in col.lower()
        ]
        modality_plot_signals[modality] = mod_columns

    return modality_plot_signals


path = Path("/home/abdulzaf/Documents/data/dvn-lab/proposed/sub-01/ses-01")
runs = load_session(path)
dict_plot_signals = get_modality_columns(runs[0])
