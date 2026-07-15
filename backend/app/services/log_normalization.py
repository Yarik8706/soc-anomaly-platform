from __future__ import annotations

import csv
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import TextIO
from urllib.parse import unquote

from app.services.log_validation import (
    FileValidationResult,
    find_time_column,
    validate_log_file,
)

logger = logging.getLogger(__name__)

DROP_COLUMNS = {"ClusterID", "ClusterName", "TenantID", "TenantName"}
USER_COLUMNS = {"SourceUserName", "DestinationUserName"}
INVALID_USER_TOKENS = {
    "",
    "-",
    "—",
    "–",
    "null",
    "(null)",
    "none",
    "nan",
    "n/a",
    "na",
    "undefined",
    "unknown",
}


class LogNormalizationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class NormalizationConfig:
    input_path: Path
    output_directory: Path


@dataclass(frozen=True, slots=True)
class NormalizedArtifact:
    path: str
    date: str
    source: str
    rows: int


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    artifacts: tuple[NormalizedArtifact, ...]
    user_mapping_path: str
    processed_rows: int
    skipped_rows: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def normalize_log_file(
    config: NormalizationConfig,
    *,
    validation: FileValidationResult | None = None,
) -> NormalizationResult:
    input_path = config.input_path
    validation = validation or validate_log_file(input_path)
    if not validation.is_valid:
        reasons = "; ".join(validation.errors)
        raise LogNormalizationError(f"Log validation failed: {reasons}")
    if validation.encoding is None or validation.delimiter is None:
        raise LogNormalizationError("Validation result lacks encoding or delimiter")

    time_column = find_time_column(list(validation.columns))
    if time_column is None:
        raise LogNormalizationError("A timestamp column is required")

    config.output_directory.mkdir(parents=True, exist_ok=True)
    role = _detect_file_role(input_path.stem)
    owner = _extract_owner(input_path.stem)
    if role == "unknown":
        role = "user" if "." in owner else "host"

    user_mapping: dict[str, str] = {}
    if role == "user":
        owner_token = _base_user_token(owner)
        if owner_token:
            user_mapping[owner_token] = "user001"

    output_handles: dict[Path, TextIO] = {}
    output_writers: dict[Path, csv.DictWriter] = {}
    artifact_rows: dict[tuple[Path, str, str], int] = {}
    processed_rows = 0
    skipped_rows = 0

    output_columns = [
        column for column in validation.columns if column not in DROP_COLUMNS
    ]
    if "Date" not in output_columns:
        output_columns.append("Date")

    try:
        with input_path.open(
            "r",
            encoding=validation.encoding,
            newline="",
        ) as source_file:
            reader = csv.DictReader(source_file, delimiter=validation.delimiter)
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    skipped_rows += 1
                    continue

                timestamp = _parse_timestamp(row.get(time_column, ""))
                if timestamp is None:
                    skipped_rows += 1
                    continue

                normalized_row = {
                    key: value or ""
                    for key, value in row.items()
                    if key is not None and key not in DROP_COLUMNS
                }
                normalized_row[time_column] = timestamp.strftime("%Y-%m-%d %H:%M:%S")
                normalized_row["Date"] = timestamp.date().isoformat()
                _anonymize_users(normalized_row, user_mapping)

                source = "PAN" if _is_pan_traffic(normalized_row) else "SIEM"
                prefix = _output_prefix(role, owner, normalized_row, user_mapping)
                output_path = config.output_directory / (
                    f"{prefix}_{source}_{normalized_row['Date']}.csv"
                )

                writer = output_writers.get(output_path)
                if writer is None:
                    handle = output_path.open("w", encoding="utf-8", newline="")
                    output_handles[output_path] = handle
                    writer = csv.DictWriter(
                        handle,
                        fieldnames=output_columns,
                        extrasaction="ignore",
                    )
                    output_writers[output_path] = writer
                    writer.writeheader()

                writer.writerow(normalized_row)
                key = (output_path, normalized_row["Date"], source)
                artifact_rows[key] = artifact_rows.get(key, 0) + 1
                processed_rows += 1
    except (OSError, csv.Error) as exc:
        for handle in output_handles.values():
            handle.close()
        for output_path in output_handles:
            output_path.unlink(missing_ok=True)
        raise LogNormalizationError(f"Unable to normalize {input_path.name}") from exc
    finally:
        for handle in output_handles.values():
            if not handle.closed:
                handle.close()

    if processed_rows == 0:
        raise LogNormalizationError("No rows contain a supported timestamp")

    mapping_path = _write_user_mapping(config.output_directory, user_mapping)
    artifacts = tuple(
        NormalizedArtifact(
            path=str(path),
            date=date,
            source=source,
            rows=rows,
        )
        for (path, date, source), rows in sorted(
            artifact_rows.items(), key=lambda item: str(item[0][0])
        )
    )

    logger.info(
        "Normalized log file",
        extra={
            "input_path": str(input_path),
            "processed_rows": processed_rows,
            "skipped_rows": skipped_rows,
            "artifact_count": len(artifacts),
        },
    )
    return NormalizationResult(
        artifacts=artifacts,
        user_mapping_path=str(mapping_path),
        processed_rows=processed_rows,
        skipped_rows=skipped_rows,
    )


def _parse_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None

    try:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        pass

    for date_format in (
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%d.%m.%Y %H:%M:%S",
        "%m/%d/%Y %H:%M:%S",
    ):
        try:
            return datetime.strptime(normalized, date_format)
        except ValueError:
            continue
    return None


def _detect_file_role(stem: str) -> str:
    normalized = stem.upper()
    if normalized.startswith(("U.D.", "UD_", "U_", "USER_", "USER.")):
        return "user"
    if (
        normalized.startswith(
            (
                "C.D.",
                "CD_",
                "C_",
                "HOST_",
                "PC_",
                "COMPUTER_",
                "HOST.",
                "TMTP-",
                "SRV-",
                "WS-",
                "WKST-",
            )
        )
        or "TMTP" in normalized
    ):
        return "host"
    return "unknown"


def _extract_owner(stem: str) -> str:
    normalized = stem.strip()
    if normalized.upper().startswith(("U.D.", "C.D.")):
        parts = normalized.split(".")
        return ".".join(parts[2:]) if len(parts) >= 3 else normalized
    if "_" in normalized:
        return normalized.rsplit("_", maxsplit=1)[-1]
    return normalized


def _base_user_token(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = unquote(str(value)).strip()
    if not normalized or normalized.casefold() in INVALID_USER_TOKENS:
        return None
    if normalized.endswith("$"):
        return None
    if "\\" in normalized:
        normalized = normalized.rsplit("\\", maxsplit=1)[-1]
    if "@" in normalized:
        normalized = normalized.split("@", maxsplit=1)[0]
    normalized = normalized.strip().casefold()
    if not normalized or normalized in INVALID_USER_TOKENS:
        return None
    return normalized


def _anonymize_users(row: dict[str, str], user_mapping: dict[str, str]) -> None:
    for column in USER_COLUMNS.intersection(row):
        token = _base_user_token(row[column])
        if token is None:
            continue
        alias = user_mapping.setdefault(token, f"user{len(user_mapping) + 1:03d}")
        row[column] = alias


def _is_pan_traffic(row: dict[str, str]) -> bool:
    return (
        row.get("Name", "").strip().casefold() == "traffic"
        and row.get("DeviceProduct", "").strip().casefold() == "pan-os"
        and "palo alto networks" in row.get("DeviceVendor", "").casefold()
    )


def _output_prefix(
    role: str,
    owner: str,
    row: dict[str, str],
    user_mapping: dict[str, str],
) -> str:
    if role == "user":
        owner_token = _base_user_token(owner)
        prefix = user_mapping.get(owner_token or "", "user000")
    else:
        prefix = _find_hostname(row) or owner or "host"
    return _safe_filename(prefix)


def _find_hostname(row: dict[str, str]) -> str | None:
    for column in (
        "Computer",
        "HostName",
        "DeviceHostName",
        "Host",
        "SourceUserName",
        "DestinationUserName",
    ):
        value = row.get(column, "").strip()
        if value.endswith("$") and len(value) > 1:
            return value[:-1]
        if (
            column.casefold() in {"computer", "hostname", "devicehostname", "host"}
            and value
        ):
            return value
    return None


def _safe_filename(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return sanitized.strip("._") or "unknown"


def _write_user_mapping(
    output_directory: Path,
    user_mapping: dict[str, str],
) -> Path:
    output_path = output_directory / "user_mapping.csv"
    with output_path.open("w", encoding="utf-8", newline="") as mapping_file:
        writer = csv.writer(mapping_file)
        writer.writerow(("user_name", "userXXX"))
        writer.writerows(sorted(user_mapping.items(), key=lambda item: item[1]))
    return output_path
