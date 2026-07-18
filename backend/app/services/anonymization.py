from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from app.models.uploaded_file import UploadedFile

USER_COLUMNS = ("SourceUserName", "DestinationUserName")


class AnonymizationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AnalysisInputBundle:
    paths: tuple[Path, ...]
    user_mapping_path: Path
    reverse_mapping_path: Path


def prepare_analysis_inputs(
    uploads: list[UploadedFile], output_directory: Path
) -> AnalysisInputBundle:
    """Reconcile per-upload aliases into one collision-free mapping for a run."""
    output_directory.mkdir(parents=True, exist_ok=True)
    upload_mappings = {str(upload.id): _read_upload_mapping(upload) for upload in uploads}
    real_users = sorted(
        {
            real_user
            for mapping in upload_mappings.values()
            for real_user in mapping.values()
            if real_user
        },
        key=str.casefold,
    )
    global_mapping = {
        real_user: f"user{index:03d}"
        for index, real_user in enumerate(real_users, start=1)
    }

    paths: list[Path] = []
    for upload in uploads:
        result = upload.normalization_result or {}
        local_alias_to_real = upload_mappings[str(upload.id)]
        for index, artifact in enumerate(result.get("artifacts", []), start=1):
            source_path = Path(str(artifact.get("path", "")))
            if not source_path.is_file():
                continue
            try:
                frame = pd.read_csv(source_path, dtype=str, keep_default_na=False)
            except (OSError, UnicodeError, pd.errors.ParserError) as exc:
                raise AnonymizationError(
                    f"Unable to prepare normalized artifact {source_path.name}"
                ) from exc
            for column in USER_COLUMNS:
                if column not in frame:
                    continue
                frame[column] = frame[column].map(
                    lambda value: _global_alias(
                        str(value), local_alias_to_real, global_mapping
                    )
                )
            frame["_UploadedSourceFile"] = upload.filename
            frame["_NormalizedSourceFile"] = source_path.name
            destination = output_directory / f"{upload.id}_{index:03d}_{source_path.name}"
            frame.to_csv(destination, index=False)
            paths.append(destination)

    if not paths:
        raise AnonymizationError("Selected uploads have no normalized artifacts")

    mapping_path = output_directory / "user_mapping.csv"
    with mapping_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("user_name", "userXXX"))
        writer.writerows((real, alias) for real, alias in global_mapping.items())

    reverse_path = output_directory / "user_mapping_reverse.json"
    reverse_path.write_text(
        json.dumps(
            {alias: real for real, alias in global_mapping.items()},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return AnalysisInputBundle(tuple(paths), mapping_path, reverse_path)


def load_reverse_mapping(mapping_path: Path | None) -> dict[str, str]:
    if mapping_path is None or not mapping_path.is_file():
        return {}
    frame = pd.read_csv(mapping_path, dtype=str, keep_default_na=False)
    if not {"user_name", "userXXX"}.issubset(frame.columns):
        return {}
    return dict(zip(frame["userXXX"], frame["user_name"], strict=False))


def _read_upload_mapping(upload: UploadedFile) -> dict[str, str]:
    result = upload.normalization_result or {}
    value = result.get("user_mapping_path")
    if not value or not (path := Path(str(value))).is_file():
        return {}
    try:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    except (OSError, UnicodeError, pd.errors.ParserError):
        return {}
    if not {"user_name", "userXXX"}.issubset(frame.columns):
        return {}
    # local alias -> original user; scoped to this upload to avoid alias collisions.
    return dict(zip(frame["userXXX"], frame["user_name"], strict=False))


def _global_alias(
    value: str,
    local_alias_to_real: dict[str, str],
    global_mapping: dict[str, str],
) -> str:
    real_user = local_alias_to_real.get(value)
    if real_user is not None:
        return global_mapping[real_user]
    # Keep technical and already-anonymous values untouched when no reverse map exists.
    return global_mapping.get(value, value)
