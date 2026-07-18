from __future__ import annotations

from pathlib import Path

import pandas as pd

ID_COLUMNS = {"entity", "date"}
USER_COLUMNS = ("SourceUserName", "DestinationUserName")
HOST_COLUMNS = (
    "Host",
    "Hostname",
    "HostName",
    "Computer",
    "DeviceHostName",
    "SourceHostName",
    "DestinationHostName",
    "SourceAddress",
)
USER_VALUE_COLUMNS = ("SourceUserName", "DestinationUserName")

SOURCE_FEATURES = (
    "events_total",
    "unique_destination_addr",
    "unique_source_process",
    "unique_event_class",
    "unique_category",
    "unique_name",
    "unique_hours",
    "night_share",
    "business_share",
    "unique_users",
)
FEATURE_COLUMNS = (
    "day_of_week",
    "is_weekend",
    *(f"siem_{name}" for name in SOURCE_FEATURES),
    *(f"pan_{name}" for name in SOURCE_FEATURES),
    "pan_share_of_all_events",
)


class FeatureBuildError(RuntimeError):
    pass


def build_features(
    input_paths: list[Path], output_directory: Path
) -> dict[str, Path]:
    """Build separate SIEM/PAN daily features for every user and host."""
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
        frame["_source_kind"] = _source_kind(frame, path.name)
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


def available_feature_dates(feature_paths: dict[str, Path]) -> list[str]:
    dates: set[str] = set()
    for path in feature_paths.values():
        frame = pd.read_csv(path, usecols=["date"], dtype=str)
        parsed = pd.to_datetime(frame["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        dates.update(parsed.dropna().tolist())
    return sorted(dates)


def _dates(events: pd.DataFrame) -> pd.Series:
    if "Date" in events:
        dates = pd.to_datetime(events["Date"], errors="coerce")
    elif "Timestamp" in events:
        dates = pd.to_datetime(events["Timestamp"], errors="coerce")
    else:
        raise FeatureBuildError("Date or Timestamp column is required")
    return dates.dt.strftime("%Y-%m-%d")


def _source_kind(frame: pd.DataFrame, filename: str) -> pd.Series:
    filename_is_pan = "_PAN_" in filename.upper() or filename.upper().endswith("_PAN.CSV")
    if filename_is_pan:
        return pd.Series("PAN", index=frame.index, dtype="string")
    required = {"Name", "DeviceProduct", "DeviceVendor"}
    if not required.issubset(frame.columns):
        return pd.Series("SIEM", index=frame.index, dtype="string")
    pan_mask = (
        frame["Name"].astype(str).str.strip().str.casefold().eq("traffic")
        & frame["DeviceProduct"].astype(str).str.strip().str.casefold().eq("pan-os")
        & frame["DeviceVendor"]
        .astype(str)
        .str.casefold()
        .str.contains("palo alto networks", na=False)
    )
    return pd.Series("SIEM", index=frame.index, dtype="string").mask(pan_mask, "PAN")


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
    result_rows: list[dict[str, int | float | str]] = []
    for (entity, date), group in expanded.groupby(["entity", "date"], sort=True):
        parsed_date = pd.Timestamp(date)
        row: dict[str, int | float | str] = {
            "entity": str(entity),
            "date": str(date),
            "day_of_week": int(parsed_date.dayofweek),
            "is_weekend": int(parsed_date.dayofweek >= 5),
        }
        for source, prefix in (("SIEM", "siem"), ("PAN", "pan")):
            source_events = group[group["_source_kind"].eq(source)]
            row.update(_source_metrics(source_events, prefix))
        total = int(row["siem_events_total"]) + int(row["pan_events_total"])
        row["pan_share_of_all_events"] = (
            float(row["pan_events_total"]) / total if total else 0.0
        )
        result_rows.append(row)

    result = pd.DataFrame(result_rows)
    for column in FEATURE_COLUMNS:
        if column not in result:
            result[column] = 0
    return result[["entity", "date", *FEATURE_COLUMNS]].sort_values(
        ["date", "entity"], kind="mergesort"
    ).reset_index(drop=True)


def _source_metrics(events: pd.DataFrame, prefix: str) -> dict[str, int | float]:
    raw_timestamp = (
        events["Timestamp"]
        if "Timestamp" in events
        else pd.Series(pd.NaT, index=events.index, dtype="datetime64[ns]")
    )
    timestamp = pd.to_datetime(raw_timestamp, errors="coerce")
    valid_hours = timestamp.dt.hour.dropna()
    return {
        f"{prefix}_events_total": int(len(events)),
        f"{prefix}_unique_destination_addr": _nunique(events, "DestinationAddress"),
        f"{prefix}_unique_source_process": _nunique(events, "SourceProcessName"),
        f"{prefix}_unique_event_class": _nunique(events, "DeviceEventClassID"),
        f"{prefix}_unique_category": _nunique(events, "DeviceEventCategory"),
        f"{prefix}_unique_name": _nunique(events, "Name"),
        f"{prefix}_unique_hours": int(valid_hours.nunique()),
        f"{prefix}_night_share": _hour_share(valid_hours, 0, 5),
        f"{prefix}_business_share": _hour_share(valid_hours, 9, 17),
        f"{prefix}_unique_users": _unique_values(events, USER_VALUE_COLUMNS),
    }


def _nunique(frame: pd.DataFrame, column: str) -> int:
    if column not in frame:
        return 0
    values = frame[column].astype(str).str.strip()
    return int(values[values.ne("")].nunique())


def _unique_values(frame: pd.DataFrame, columns: tuple[str, ...]) -> int:
    available = [column for column in columns if column in frame]
    if not available:
        return 0
    values = pd.concat([frame[column].astype(str) for column in available], ignore_index=True)
    values = values.str.strip()
    values = values[values.ne("") & ~values.str.endswith("$", na=False)]
    return int(values.nunique())


def _hour_share(hours: pd.Series, start: int, end: int) -> float:
    if hours.empty:
        return 0.0
    return float(hours.between(start, end).mean())
