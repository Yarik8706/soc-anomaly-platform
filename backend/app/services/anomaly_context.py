from __future__ import annotations

from pathlib import Path

import pandas as pd

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
ADDRESS_COLUMNS = ("SourceAddress", "DestinationAddress")
PROCESS_COLUMNS = ("SourceProcessName", "DestinationProcessName")
EVENT_COLUMNS = ("Name", "DeviceEventCategory", "DeviceEventClassID")


class AnomalyContextBuilder:
    def __init__(
        self, input_paths: list[Path], reverse_user_mapping: dict[str, str] | None = None
    ) -> None:
        frames: list[pd.DataFrame] = []
        for path in input_paths:
            frame = pd.read_csv(path, dtype=str, keep_default_na=False)
            frame["_source_file"] = (
                frame["_UploadedSourceFile"]
                if "_UploadedSourceFile" in frame
                else path.name
            )
            frame["_normalized_source_file"] = (
                frame["_NormalizedSourceFile"]
                if "_NormalizedSourceFile" in frame
                else path.name
            )
            frame["_event_date"] = pd.to_datetime(
                frame["Date"] if "Date" in frame else frame.get("Timestamp"),
                errors="coerce",
            ).dt.strftime("%Y-%m-%d")
            frames.append(frame)
        self.events = (
            pd.concat(frames, ignore_index=True, sort=False).fillna("")
            if frames
            else pd.DataFrame()
        )
        self.reverse_user_mapping = reverse_user_mapping or {}

    def build(self, entity_type: str, entity: str, target_date: str) -> dict[str, object]:
        if self.events.empty:
            return _empty_context(entity_type, entity, self.reverse_user_mapping)
        entity_columns = USER_COLUMNS if entity_type == "user" else HOST_COLUMNS
        entity_mask = pd.Series(False, index=self.events.index)
        for column in entity_columns:
            if column in self.events:
                entity_mask |= self.events[column].astype(str).eq(entity)
        selected = self.events[
            self.events["_event_date"].eq(target_date) & entity_mask
        ].drop_duplicates()
        if selected.empty:
            return _empty_context(entity_type, entity, self.reverse_user_mapping)

        raw_timestamp = (
            selected["Timestamp"]
            if "Timestamp" in selected
            else pd.Series(pd.NaT, index=selected.index, dtype="datetime64[ns]")
        )
        timestamp = pd.to_datetime(raw_timestamp, errors="coerce")
        valid_timestamp = timestamp.dropna()
        hour_counts = timestamp.dt.hour.value_counts().head(5)
        time_range = (
            f"{valid_timestamp.min().isoformat()} — {valid_timestamp.max().isoformat()}"
            if not valid_timestamp.empty
            else ""
        )
        active_hours = [f"{int(hour):02d}:00 ({int(count)})" for hour, count in hour_counts.items()]
        processes = _values(selected, PROCESS_COLUMNS)
        event_names = _values(selected, EVENT_COLUMNS)
        ip_addresses = _values(selected, ADDRESS_COLUMNS)
        users = _values(selected, USER_COLUMNS)
        original_users = {
            alias: self.reverse_user_mapping[alias]
            for alias in users
            if alias in self.reverse_user_mapping
        }
        hosts = _values(selected, HOST_COLUMNS)
        source_files = sorted(set(selected["_source_file"].astype(str)))
        normalized_source_files = sorted(
            set(selected["_normalized_source_file"].astype(str))
        )
        original_user = self.reverse_user_mapping.get(entity, "") if entity_type == "user" else ""
        description = _description(
            len(selected),
            time_range,
            active_hours,
            processes,
            event_names,
            ip_addresses,
        )
        return {
            "event_count": int(len(selected)),
            "time_range": time_range,
            "most_active_hours": active_hours,
            "active_hours": sorted({str(value) for value in timestamp.dt.hour.dropna().astype(int)}),
            "processes": processes,
            "event_names": event_names,
            "events": event_names,
            "ip_addresses": ip_addresses,
            "users": users,
            "hosts": hosts,
            "source_files": source_files,
            "normalized_source_files": normalized_source_files,
            "original_user": original_user,
            "original_users": original_users,
            "detailed_description": description,
        }


def build_anomaly_context(
    input_paths: list[Path],
    entity_type: str,
    entity: str,
    target_date: str,
    reverse_user_mapping: dict[str, str] | None = None,
) -> dict[str, object]:
    return AnomalyContextBuilder(input_paths, reverse_user_mapping).build(
        entity_type, entity, target_date
    )


def _values(frame: pd.DataFrame, columns: tuple[str, ...], limit: int = 20) -> list[str]:
    counts: dict[str, int] = {}
    for column in columns:
        if column not in frame:
            continue
        for raw in frame[column].astype(str):
            value = raw.strip()
            if value:
                counts[value] = counts.get(value, 0) + 1
    return [
        value
        for value, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def _description(
    count: int,
    time_range: str,
    hours: list[str],
    processes: list[str],
    events: list[str],
    addresses: list[str],
) -> str:
    parts = [f"Observed {count} source events."]
    if time_range:
        parts.append(f"Activity range: {time_range}.")
    if hours:
        parts.append(f"Peak hours: {', '.join(hours[:5])}.")
    if processes:
        parts.append(f"Processes: {', '.join(processes[:5])}.")
    if events:
        parts.append(f"Event names/classes: {', '.join(events[:5])}.")
    if addresses:
        parts.append(f"IP addresses: {', '.join(addresses[:5])}.")
    return " ".join(parts)


def _empty_context(
    entity_type: str, entity: str, reverse_user_mapping: dict[str, str]
) -> dict[str, object]:
    return {
        "event_count": 0,
        "time_range": "",
        "most_active_hours": [],
        "active_hours": [],
        "processes": [],
        "event_names": [],
        "events": [],
        "ip_addresses": [],
        "users": [],
        "hosts": [],
        "source_files": [],
        "normalized_source_files": [],
        "original_user": reverse_user_mapping.get(entity, "") if entity_type == "user" else "",
        "original_users": {},
        "detailed_description": f"No source events found for {entity_type} {entity}.",
    }
