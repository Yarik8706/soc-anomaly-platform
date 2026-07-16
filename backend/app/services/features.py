from __future__ import annotations

from pathlib import Path

import pandas as pd

ID_COLUMNS = {"entity", "date"}
USER_COLUMNS = ("SourceUserName", "DestinationUserName")
HOST_COLUMNS = (
    "Host",
    "Hostname",
    "SourceHostName",
    "DestinationHostName",
    "SourceAddress",
)


class FeatureBuildError(RuntimeError):
    pass


def build_features(
    input_paths: list[Path], output_directory: Path
) -> dict[str, Path]:
    if not input_paths:
        raise FeatureBuildError("No normalized input artifacts were selected")

    frames: list[pd.DataFrame] = []
    for path in input_paths:
        try:
            frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        except (OSError, UnicodeError, pd.errors.ParserError) as exc:
            raise FeatureBuildError(f"Unable to read normalized artifact {path.name}") from exc
        if frame.empty:
            continue
        frame["_source_file"] = path.name
        frames.append(frame)

    if not frames:
        raise FeatureBuildError("Normalized input artifacts contain no rows")

    events = pd.concat(frames, ignore_index=True, sort=False).fillna("")
    events["date"] = _dates(events)
    events = events[events["date"].notna()].copy()
    if events.empty:
        raise FeatureBuildError("No valid event dates found in normalized artifacts")

    output_directory.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, Path] = {}
    for kind, columns in (("users", USER_COLUMNS), ("hosts", HOST_COLUMNS)):
        feature_frame = _aggregate(events, columns)
        if feature_frame.empty:
            continue
        path = output_directory / f"features_{kind}.csv"
        feature_frame.to_csv(path, index=False)
        outputs[kind] = path

    if not outputs:
        raise FeatureBuildError("No user or host entity columns found")
    return outputs


def _dates(events: pd.DataFrame) -> pd.Series:
    if "Date" in events:
        dates = pd.to_datetime(events["Date"], errors="coerce")
    elif "Timestamp" in events:
        dates = pd.to_datetime(events["Timestamp"], errors="coerce")
    else:
        raise FeatureBuildError("Date or Timestamp column is required")
    return dates.dt.strftime("%Y-%m-%d")


def _aggregate(events: pd.DataFrame, entity_columns: tuple[str, ...]) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for column in entity_columns:
        if column not in events:
            continue
        part = events[events[column].astype(str).str.strip().ne("")].copy()
        if part.empty:
            continue
        part["entity"] = part[column].astype(str).str.strip()
        rows.append(part)
    if not rows:
        return pd.DataFrame()

    expanded = pd.concat(rows, ignore_index=True).drop_duplicates()
    timestamp = pd.to_datetime(expanded.get("Timestamp"), errors="coerce")
    expanded["_hour"] = timestamp.dt.hour
    expanded["_night"] = expanded["_hour"].between(0, 5).astype(int)
    expanded["_business"] = expanded["_hour"].between(9, 17).astype(int)

    dimensions = {
        "unique_destination_addr": "DestinationAddress",
        "unique_source_process": "SourceProcessName",
        "unique_event_class": "DeviceEventClassID",
        "unique_category": "DeviceEventCategory",
        "unique_name": "Name",
    }
    result = (
        expanded.groupby(["entity", "date"], dropna=False)
        .agg(
            events_total=("entity", "size"),
            unique_hours=("_hour", "nunique"),
            night_share=("_night", "mean"),
            business_share=("_business", "mean"),
        )
        .reset_index()
    )
    grouped = expanded.groupby(["entity", "date"], dropna=False)
    for name, column in dimensions.items():
        result[name] = (
            grouped[column].nunique().to_numpy() if column in expanded else 0
        )
    return result.sort_values(["date", "entity"]).reset_index(drop=True)
