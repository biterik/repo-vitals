"""Merge stage: fold a daily snapshot into the long-term per-day history.

The traffic API returns a rolling 14-day window; consecutive runs overlap
~13 days and GitHub retro-adjusts recent days. The merge rule is: history is
keyed by UTC date, and for overlapping days the snapshot with the newer
`collected_at` wins. Gaps (> 14 days without a run) stay as explicit holes —
never interpolated.

History is stored as NDJSON, one line per day, sorted by date. Each day
record may hold:

  date                traffic-window fields        point-in-time fields
  ----                ----------------------       --------------------
  "2026-07-06"        views, clones                popularity, referrers,
                      (guarded by                  paths, releases, activity
                      traffic_updated_at)          (guarded by observed_at)

Traffic-window fields can be written for any day covered by some run's
14-day window; point-in-time fields exist only for days on which a run
actually happened. Both guards compare `collected_at` timestamps (ISO-8601
UTC with trailing Z, so lexicographic comparison is chronological); a rerun
with equal-or-newer timestamp overwrites, which makes same-day reruns
idempotent while an out-of-order merge of an older snapshot never clobbers
newer data.
"""

from __future__ import annotations

import json
from pathlib import Path

TRAFFIC_KINDS = ("views", "clones")


def merge_snapshot(history: dict[str, dict], snapshot: dict) -> dict[str, dict]:
    """Merge one snapshot into history (dict keyed by date). Mutates and returns it."""
    collected_at = snapshot["collected_at"]
    traffic = snapshot.get("traffic") or {}

    for kind in TRAFFIC_KINDS:
        for day, counts in (traffic.get(kind) or {}).items():
            rec = history.setdefault(day, {"date": day})
            if collected_at >= rec.get("traffic_updated_at", ""):
                rec[kind] = counts
                rec["traffic_updated_at"] = collected_at

    day = snapshot["date"]
    rec = history.setdefault(day, {"date": day})
    if collected_at >= rec.get("observed_at", ""):
        rec["observed_at"] = collected_at
        if snapshot.get("popularity") is not None:
            rec["popularity"] = snapshot["popularity"]
        if traffic.get("referrers") is not None:
            rec["referrers"] = traffic["referrers"]
        if traffic.get("paths") is not None:
            rec["paths"] = traffic["paths"]
        if snapshot.get("releases") is not None:
            rec["releases"] = summarize_releases(snapshot["releases"])
        if snapshot.get("activity") is not None:
            rec["activity"] = snapshot["activity"]

    return history


def summarize_releases(releases: list[dict]) -> list[dict]:
    """Per-day release record: total downloads per tag (assets stay in raw snapshots)."""
    return [
        {
            "tag": r.get("tag"),
            "downloads": sum(a.get("downloads", 0) for a in r.get("assets", [])),
        }
        for r in releases
    ]


def rebuild_history(snapshots: list[dict]) -> dict[str, dict]:
    """Regenerate history from raw snapshots alone (the audit-trail guarantee).

    Snapshots are merged in collected_at order; the result is identical to
    having merged them incrementally as they were collected.
    """
    history: dict[str, dict] = {}
    for snapshot in sorted(snapshots, key=lambda s: s["collected_at"]):
        merge_snapshot(history, snapshot)
    return history


def load_history(path: str | Path) -> dict[str, dict]:
    """Read history.ndjson into a dict keyed by date. Missing file -> empty history."""
    path = Path(path)
    history: dict[str, dict] = {}
    if not path.exists():
        return history
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            history[rec["date"]] = rec
    return history


def dump_history(history: dict[str, dict]) -> str:
    """Serialize history as NDJSON, one day per line, sorted by date."""
    lines = [
        json.dumps(history[day], sort_keys=True, separators=(",", ":"))
        for day in sorted(history)
    ]
    return "\n".join(lines) + ("\n" if lines else "")
