from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from app.services.explanations import severity_for_rank

INK = "#1f2937"
BLUE = "#2563eb"
GOLD = "#d4a72c"
ORANGE = "#ea580c"
PINK = "#db2777"
OLIVE = "#708238"
GRID = "#d1d5db"
SEVERITY_COLORS = {
    "critical": PINK,
    "high": ORANGE,
    "medium": GOLD,
    "low": BLUE,
}


def generate_graphical_reports(
    scored: dict[str, pd.DataFrame],
    output_directory: Path,
    *,
    top_pct: float,
) -> dict[str, Path]:
    """Export score previews and daily/weekly/monthly trend charts as PNG+CSV."""
    output_directory.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, Path] = {}
    all_trends: list[pd.DataFrame] = []

    for kind, raw in scored.items():
        if raw.empty:
            continue
        frame = _with_severity(raw)
        top_count = max(1, math.ceil(len(frame) * top_pct))
        top = frame.sort_values("score_combined", ascending=False).head(top_count)
        top_csv = output_directory / f"top_{kind}.csv"
        top_png = output_directory / f"top_{kind}.png"
        top.to_csv(top_csv, index=False)
        _top_bar(top, top_png, f"Top {top_pct:.0%} anomalous {kind}")
        artifacts[f"top_{kind}_csv"] = top_csv
        artifacts[f"top_{kind}_png"] = top_png

        severity_csv = output_directory / f"severity_{kind}.csv"
        severity_png = output_directory / f"severity_{kind}.png"
        severity = _severity_counts(frame)
        severity.to_csv(severity_csv, index=False)
        _severity_pie(severity, severity_png, f"Severity distribution — {kind}")
        artifacts[f"severity_{kind}_csv"] = severity_csv
        artifacts[f"severity_{kind}_png"] = severity_png

        trend = _daily_trend(frame, kind)
        trend_csv = output_directory / f"trend_{kind}_daily.csv"
        trend.to_csv(trend_csv, index=False)
        artifacts[f"trend_{kind}_daily_csv"] = trend_csv
        for metric, suffix, title in (
            ("total", "anomalies", f"Daily anomaly count — {kind}"),
            ("critical", "critical", f"Daily critical severity — {kind}"),
        ):
            path = output_directory / f"trend_{kind}_{suffix}.png"
            _line_chart(trend, path, title, metric)
            artifacts[f"trend_{kind}_{suffix}_png"] = path
        stacked_path = output_directory / f"trend_{kind}_severity_stacked.png"
        _stacked_severity(trend, stacked_path, f"Daily severity composition — {kind}")
        artifacts[f"trend_{kind}_severity_stacked_png"] = stacked_path
        all_trends.append(trend)

    if all_trends:
        combined = pd.concat(all_trends, ignore_index=True)
        combined["date"] = pd.to_datetime(combined["date"])
        for period, rule in (("weekly", "W-SUN"), ("monthly", "ME")):
            trend = (
                combined.set_index("date")
                .groupby("kind")[["total", "critical", "high", "medium", "low"]]
                .resample(rule)
                .sum()
                .reset_index()
            )
            trend["date"] = trend["date"].dt.strftime("%Y-%m-%d")
            csv_path = output_directory / f"{period}_trends.csv"
            png_path = output_directory / f"{period}_trends.png"
            trend.to_csv(csv_path, index=False)
            _multi_kind_trend(trend, png_path, f"{period.title()} anomaly trend")
            artifacts[f"{period}_trends_csv"] = csv_path
            artifacts[f"{period}_trends_png"] = png_path
    return artifacts


def _with_severity(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["severity"] = (
        result.groupby("date")["rank_combined"]
        .transform(lambda ranks: [severity_for_rank(int(rank), len(ranks)) for rank in ranks])
    )
    return result


def _severity_counts(frame: pd.DataFrame) -> pd.DataFrame:
    counts = frame["severity"].value_counts()
    return pd.DataFrame(
        {
            "severity": list(SEVERITY_COLORS),
            "count": [int(counts.get(name, 0)) for name in SEVERITY_COLORS],
        }
    )


def _daily_trend(frame: pd.DataFrame, kind: str) -> pd.DataFrame:
    counts = (
        frame.groupby(["date", "severity"]).size().unstack(fill_value=0).reset_index()
    )
    for severity in SEVERITY_COLORS:
        if severity not in counts:
            counts[severity] = 0
    counts["total"] = counts[list(SEVERITY_COLORS)].sum(axis=1)
    counts["kind"] = kind
    return counts[["date", "kind", "total", *SEVERITY_COLORS]].sort_values("date")


def _top_bar(frame: pd.DataFrame, path: Path, title: str) -> None:
    plot = frame.sort_values("score_combined", ascending=True).tail(30)
    height = max(4.0, min(12.0, 0.32 * len(plot) + 2.0))
    fig, ax = plt.subplots(figsize=(10, height))
    ax.barh(plot["entity"].astype(str), plot["score_combined"], color=BLUE)
    ax.set(xlabel="Combined anomaly score", title=title, xlim=(0, 1))
    _style(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=160, facecolor="white")
    plt.close(fig)


def _severity_pie(frame: pd.DataFrame, path: Path, title: str) -> None:
    nonzero = frame[frame["count"] > 0]
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.pie(
        nonzero["count"],
        labels=nonzero["severity"],
        autopct="%1.1f%%",
        colors=[SEVERITY_COLORS[name] for name in nonzero["severity"]],
        wedgeprops={"edgecolor": "white", "linewidth": 1},
    )
    ax.set_title(title, color=INK)
    fig.tight_layout()
    fig.savefig(path, dpi=160, facecolor="white")
    plt.close(fig)


def _line_chart(frame: pd.DataFrame, path: Path, title: str, column: str) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(frame["date"], frame[column], color=BLUE, marker="o", linewidth=2)
    ax.set(xlabel="Date", ylabel="Entities", title=title, ylim=(0, None))
    ax.tick_params(axis="x", rotation=45)
    _style(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=160, facecolor="white")
    plt.close(fig)


def _stacked_severity(frame: pd.DataFrame, path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    bottom = pd.Series(0, index=frame.index, dtype=float)
    for severity in SEVERITY_COLORS:
        values = frame[severity].astype(float)
        ax.bar(
            frame["date"],
            values,
            bottom=bottom,
            label=severity,
            color=SEVERITY_COLORS[severity],
        )
        bottom += values
    ax.set(xlabel="Date", ylabel="Entities", title=title)
    ax.tick_params(axis="x", rotation=45)
    ax.legend(frameon=False, ncol=4)
    _style(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=160, facecolor="white")
    plt.close(fig)


def _multi_kind_trend(frame: pd.DataFrame, path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    colors = {"users": BLUE, "hosts": ORANGE}
    for kind, group in frame.groupby("kind"):
        ax.plot(
            group["date"],
            group["total"],
            marker="o",
            linewidth=2,
            label=kind,
            color=colors.get(str(kind), OLIVE),
        )
    ax.set(xlabel="Period end", ylabel="Entities", title=title, ylim=(0, None))
    ax.tick_params(axis="x", rotation=45)
    ax.legend(frameon=False)
    _style(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=160, facecolor="white")
    plt.close(fig)


def _style(ax: plt.Axes) -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color=GRID, linewidth=0.7, alpha=0.65)
    ax.set_axisbelow(True)
    ax.title.set_color(INK)
