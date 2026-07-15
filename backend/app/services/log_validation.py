from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path

TIME_COLUMN_CANDIDATES = (
    "Timestamp",
    "EventTime",
    "event_time",
    "time",
    "TimeGenerated",
    "StartTime",
    "EndTime",
)
SUPPORTED_ENCODINGS = ("utf-8-sig", "utf-8", "cp1251")
SUPPORTED_DELIMITERS = ("\t", ",", ";", "|")
DEFAULT_SAMPLE_BYTES = 1024 * 1024
DEFAULT_SAMPLE_ROWS = 1_000
MAX_SAMPLE_LINE_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class FileValidationResult:
    is_valid: bool
    encoding: str | None
    delimiter: str | None
    columns: tuple[str, ...]
    missing_critical_columns: tuple[str, ...]
    errors: tuple[str, ...]
    sampled_rows: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def find_time_column(columns: tuple[str, ...] | list[str]) -> str | None:
    for candidate in TIME_COLUMN_CANDIDATES:
        if candidate in columns:
            return candidate

    for column in columns:
        normalized = column.casefold()
        if "time" in normalized or "timestamp" in normalized or "date" in normalized:
            return column

    return None


def validate_log_file(
    path: Path,
    *,
    sample_bytes: int = DEFAULT_SAMPLE_BYTES,
    sample_rows: int = DEFAULT_SAMPLE_ROWS,
) -> FileValidationResult:
    if sample_bytes <= 0:
        raise ValueError("sample_bytes must be positive")
    if sample_rows <= 0:
        raise ValueError("sample_rows must be positive")
    if not path.is_file():
        raise FileNotFoundError(f"Log file does not exist: {path}")

    with path.open("rb") as source_file:
        raw_sample = source_file.read(sample_bytes)
        if len(raw_sample) == sample_bytes:
            raw_sample += source_file.readline(MAX_SAMPLE_LINE_BYTES)
    if not raw_sample:
        return _invalid_result("File is empty")

    decoded = _decode_sample(raw_sample)
    if decoded is None:
        return _invalid_result("Unable to detect a supported text encoding")

    text, encoding = decoded
    delimiter = _detect_delimiter(text, path.suffix.casefold())
    if delimiter is None:
        return _invalid_result(
            "Unable to detect a supported delimiter",
            encoding=encoding,
        )

    reader = csv.reader(text.splitlines(), delimiter=delimiter)
    try:
        raw_columns = next(reader)
    except StopIteration:
        return _invalid_result(
            "File does not contain a header row",
            encoding=encoding,
            delimiter=delimiter,
        )

    columns = tuple(column.strip() for column in raw_columns)
    errors: list[str] = []

    if len(columns) < 2:
        errors.append("At least two columns are required")
    if any(not column for column in columns):
        errors.append("Header contains an empty column name")
    if len(set(columns)) != len(columns):
        errors.append("Header contains duplicate column names")

    missing_critical_columns: list[str] = []
    if find_time_column(columns) is None:
        missing_critical_columns.append("timestamp")
        errors.append("Missing a timestamp column required for daily normalization")

    sampled_row_count = 0
    malformed_row_count = 0
    for row in reader:
        if not any(cell.strip() for cell in row):
            continue
        sampled_row_count += 1
        if len(row) != len(columns):
            malformed_row_count += 1
        if sampled_row_count >= sample_rows:
            break

    if sampled_row_count == 0:
        errors.append("File does not contain data rows")
    if malformed_row_count:
        errors.append(f"Found {malformed_row_count} malformed rows in the sampled data")

    return FileValidationResult(
        is_valid=not errors,
        encoding=encoding,
        delimiter=delimiter,
        columns=columns,
        missing_critical_columns=tuple(missing_critical_columns),
        errors=tuple(errors),
        sampled_rows=sampled_row_count,
    )


def _decode_sample(raw_sample: bytes) -> tuple[str, str] | None:
    encodings = (
        ("utf-16", *SUPPORTED_ENCODINGS)
        if b"\x00" in raw_sample
        else SUPPORTED_ENCODINGS
    )

    for encoding in encodings:
        try:
            return raw_sample.decode(encoding), encoding
        except UnicodeError:
            continue

    return None


def _detect_delimiter(text: str, suffix: str) -> str | None:
    non_empty_lines = [line for line in text.splitlines() if line.strip()]
    if not non_empty_lines:
        return None

    sample = "\n".join(non_empty_lines[:20])
    try:
        return (
            csv.Sniffer()
            .sniff(sample, delimiters="".join(SUPPORTED_DELIMITERS))
            .delimiter
        )
    except csv.Error:
        preferred = "\t" if suffix in {".tsv", ".txt"} else ","
        if preferred in non_empty_lines[0]:
            return preferred
        return None


def _invalid_result(
    error: str,
    *,
    encoding: str | None = None,
    delimiter: str | None = None,
) -> FileValidationResult:
    return FileValidationResult(
        is_valid=False,
        encoding=encoding,
        delimiter=delimiter,
        columns=(),
        missing_critical_columns=(),
        errors=(error,),
        sampled_rows=0,
    )
