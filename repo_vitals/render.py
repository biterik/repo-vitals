"""Render stage: turn snapshot + history into the published artifacts.

M1 scope: VITALS.json (latest snapshot + a first cut of derived metrics)
plus the dry-run file layout. REPORT.md and index.html arrive in M3/M4;
rendering stays a pure function of history + templates so everything can be
rebuilt from the vitals branch alone.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from repo_vitals.merge import dump_history


def build_vitals(snapshot: dict, history: dict[str, dict]) -> dict:
    """VITALS.json content: the latest snapshot plus derived rollups."""
    return {**snapshot, "derived": _derived(snapshot, history)}


def _derived(snapshot: dict, history: dict[str, dict]) -> dict:
    end = dt.date.fromisoformat(snapshot["date"])
    return {
        "views_last_7d": _window_sum(history, "views", end, 7),
        "views_last_30d": _window_sum(history, "views", end, 30),
        "clones_last_7d": _window_sum(history, "clones", end, 7),
        "clones_last_30d": _window_sum(history, "clones", end, 30),
        "history_days": len(history),
    }


def _window_sum(history, kind, end, days):
    """Sum of daily counts over the window, or None if no day has data."""
    start = (end - dt.timedelta(days=days - 1)).isoformat()
    values = [
        rec[kind]["count"]
        for day, rec in history.items()
        if start <= day <= end.isoformat() and kind in rec
    ]
    return sum(values) if values else None


def write_outputs(out_dir: str | Path, snapshot: dict, history: dict[str, dict]) -> list[Path]:
    """Write snapshots/<date>.json, history.ndjson, and VITALS.json under out_dir."""
    out = Path(out_dir)
    (out / "snapshots").mkdir(parents=True, exist_ok=True)

    snapshot_path = out / "snapshots" / f"{snapshot['date']}.json"
    snapshot_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")

    history_path = out / "history.ndjson"
    history_path.write_text(dump_history(history), encoding="utf-8")

    vitals_path = out / "VITALS.json"
    vitals_path.write_text(
        json.dumps(build_vitals(snapshot, history), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return [snapshot_path, history_path, vitals_path]
