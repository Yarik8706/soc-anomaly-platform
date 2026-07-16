from __future__ import annotations

from pathlib import Path

import pandas as pd

USER_COLUMNS = ("SourceUserName", "DestinationUserName")
HOST_COLUMNS = (
    "Host",
    "Hostname",
    "SourceHostName",
    "DestinationHostName",
    "SourceAddress",
)


def build_anomaly_context(
    input_paths: list[Path], entity_type: str, entity: str, target_date: str
) -> dict[str, list[str] | int]:
    matches: list[pd.DataFrame] = []
    entity_columns = USER_COLUMNS if entity_type == "user" else HOST_COLUMNS
    for path in input_paths:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        dates = pd.to_datetime(
            frame["Date"] if "Date" in frame else frame.get("Timestamp"),
            errors="coerce",
        ).dt.strftime("%Y-%m-%d")
        mask = dates.eq(target_date)
        entity_mask = pd.Series(False, index=frame.index)
        for column in entity_columns:
            if column in frame:
                entity_mask |= frame[column].astype(str).eq(entity)
        selected = frame[mask & entity_mask]
        if not selected.empty:
            matches.append(selected)

    if not matches:
        return {"event_count": 0}
    events = pd.concat(matches, ignore_index=True).drop_duplicates()
    timestamp = pd.to_datetime(events.get("Timestamp"), errors="coerce")
    return {
        "event_count": int(len(events)),
        "ip_addresses": _values(events, ("SourceAddress", "DestinationAddress")),
        "processes": _values(events, ("SourceProcessName", "DestinationProcessName")),
        "events": _values(events, ("Name", "DeviceEventCategory", "DeviceEventClassID")),
        "users": _values(events, USER_COLUMNS),
        "active_hours": sorted({str(value) for value in timestamp.dt.hour.dropna().astype(int)}),
    }


def _values(frame: pd.DataFrame, columns: tuple[str, ...], limit: int = 20) -> list[str]:
    values: set[str] = set()
    for column in columns:
        if column in frame:
            values.update(value.strip() for value in frame[column].astype(str) if value.strip())
    return sorted(values)[:limit]
