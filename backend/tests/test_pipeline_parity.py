import csv
from pathlib import Path
from uuid import uuid4

import pandas as pd

from app.models.analysis_run import AnalysisRun
from app.models.uploaded_file import UploadedFile
from app.services.anonymization import load_reverse_mapping, prepare_analysis_inputs
from app.services.pipeline import resolve_analysis_dates


def test_period_resolution_scores_every_requested_available_date() -> None:
    available = [f"2026-07-{day:02d}" for day in range(1, 16)]
    assert resolve_analysis_dates(
        AnalysisRun(scope="week", target_date="2026-07-15"), available
    ) == available[-7:]
    assert resolve_analysis_dates(
        AnalysisRun(scope="month", target_date="2026-07-15"), available
    ) == available
    assert resolve_analysis_dates(
        AnalysisRun(scope="range", start_date="2026-07-05", end_date="2026-07-08"),
        available,
    ) == available[4:8]
    assert resolve_analysis_dates(AnalysisRun(scope="all"), available) == available


def test_run_mapping_reconciles_upload_aliases_without_collisions(tmp_path: Path) -> None:
    uploads: list[UploadedFile] = []
    for index, real_user in enumerate(("alice", "bob", "alice"), start=1):
        source = tmp_path / f"source_{index}.csv"
        pd.DataFrame(
            {
                "Timestamp": ["2026-07-15 10:00:00"],
                "Date": ["2026-07-15"],
                "SourceUserName": ["user001"],
                "DestinationUserName": ["user001"],
            }
        ).to_csv(source, index=False)
        mapping = tmp_path / f"mapping_{index}.csv"
        with mapping.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(("user_name", "userXXX"))
            writer.writerow((real_user, "user001"))
        uploads.append(
            UploadedFile(
                id=uuid4(),
                filename=source.name,
                content_type="text/csv",
                size=source.stat().st_size,
                storage_path=str(source),
                status="normalized",
                normalization_result={
                    "artifacts": [{"path": str(source)}],
                    "user_mapping_path": str(mapping),
                },
            )
        )

    bundle = prepare_analysis_inputs(uploads, tmp_path / "prepared")
    aliases = [pd.read_csv(path).loc[0, "SourceUserName"] for path in bundle.paths]
    assert aliases == ["user001", "user002", "user001"]
    assert load_reverse_mapping(bundle.user_mapping_path) == {
        "user001": "alice",
        "user002": "bob",
    }
