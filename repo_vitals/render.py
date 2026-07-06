"""Render stage: turn snapshot + history into the published artifacts.

Rendering is a pure function of history + templates (§7.9): the `render`
CLI subcommand can rebuild VITALS.json, REPORT.md, and the badge endpoints
from the vitals branch data alone at any time.
"""

from __future__ import annotations

import datetime as dt
import importlib.resources
import json
import urllib.parse
from pathlib import Path

import jinja2

from repo_vitals.derived import compute_derived
from repo_vitals.merge import dump_history

_env = jinja2.Environment(
    loader=jinja2.PackageLoader("repo_vitals", "templates"),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
)
_env.filters["dash"] = lambda v: "–" if v is None else v

SPARK_BLOCKS = "▁▂▃▄▅▆▇█"
SPARK_DAYS = 30


def build_vitals(snapshot: dict, history: dict[str, dict]) -> dict:
    """VITALS.json content: the latest snapshot plus derived rollups."""
    return {**snapshot, "derived": compute_derived(snapshot, history)}


def sparkline(values) -> str:
    """Unicode sparkline; None (day without data) renders as '·'."""
    present = [v for v in values if v is not None]
    if not present:
        return ""
    lo, hi = min(present), max(present)
    span = (hi - lo) or 1
    return "".join(
        "·" if v is None else SPARK_BLOCKS[round((v - lo) / span * 7)]
        for v in values
    )


def daily_series(history, kind, end, days):
    """Daily counts for the trailing window, None where history has a hole."""
    out = []
    for offset in range(days - 1, -1, -1):
        day = (end - dt.timedelta(days=offset)).isoformat()
        rec = history.get(day)
        out.append(rec[kind]["count"] if rec and kind in rec else None)
    return out


def badge_url(repo, branch, filename):
    raw = f"https://raw.githubusercontent.com/{repo}/{branch}/badge/{filename}"
    return "https://img.shields.io/endpoint?url=" + urllib.parse.quote_plus(raw)


def build_badges(snapshot: dict, derived: dict) -> dict[str, dict]:
    """shields.io endpoint JSON files (§6): badge/<name>.json."""
    stars = derived.get("stars_now")
    gained = derived.get("stars_gained_30d")
    stars_msg = "n/a" if stars is None else str(stars)
    if stars is not None and gained:
        stars_msg += f" (+{gained}/30d)" if gained > 0 else f" ({gained}/30d)"

    views = derived.get("views_last_7d")
    prev = derived.get("views_prev_7d")
    if views is None:
        views_msg, views_color = "no data", "lightgrey"
    else:
        views_msg = f"{views}/wk"
        if prev is None:
            views_color = "blue"
        else:
            views_color = "brightgreen" if views > prev else ("orange" if views < prev else "blue")

    score = derived["health"]["score"]
    health_color = ("brightgreen" if score >= 70 else
                    "yellowgreen" if score >= 55 else
                    "yellow" if score >= 40 else
                    "orange" if score >= 25 else "red")

    def endpoint(label, message, color):
        return {"schemaVersion": 1, "label": label, "message": str(message), "color": color}

    return {
        "stars.json": endpoint("stars", stars_msg, "blue"),
        "views-week.json": endpoint("views", views_msg, views_color),
        "health.json": endpoint("health", f"{score}/100", health_color),
    }


def render_report(snapshot: dict, history: dict[str, dict], branch: str = "vitals") -> str:
    """REPORT.md — the daily human-readable summary (§6).

    Surfaces a failing traffic PAT loudly (§7.6b): the warning includes the
    last day for which traffic data exists in history.
    """
    derived = compute_derived(snapshot, history)
    end = dt.date.fromisoformat(snapshot["date"])
    traffic_failing = any(e["section"] == "traffic" for e in snapshot.get("errors", []))
    traffic_days = sorted(day for day, rec in history.items() if "views" in rec)

    views_daily = daily_series(history, "views", end, SPARK_DAYS)
    clones_daily = daily_series(history, "clones", end, SPARK_DAYS)

    repo = snapshot["repo"]
    return _env.get_template("report.md.j2").render(
        snapshot=snapshot,
        derived=derived,
        health=derived["health"],
        forecast=derived["star_forecast"],
        windows=derived["windows"],
        funnel=derived["funnel_30d"],
        traffic_failing=traffic_failing,
        last_traffic_day=traffic_days[-1] if traffic_days else None,
        views_spark=sparkline(views_daily),
        clones_spark=sparkline(clones_daily),
        views_30d_total=derived["views_last_30d"],
        clones_30d_total=derived["clones_last_30d"],
        spark_days=SPARK_DAYS,
        badges=[
            ("stars", badge_url(repo, branch, "stars.json")),
            ("views/week", badge_url(repo, branch, "views-week.json")),
            ("health", badge_url(repo, branch, "health.json")),
        ],
    )


def render_dashboard() -> str:
    """index.html — a static, self-contained dashboard (§3.4). All data comes
    from relative fetches of VITALS.json/history.ndjson at view time, so the
    file itself carries no repo-specific state and is copied verbatim."""
    return (
        importlib.resources.files("repo_vitals")
        .joinpath("templates/index.html")
        .read_text(encoding="utf-8")
    )


def write_outputs(out_dir: str | Path, snapshot: dict, history: dict[str, dict],
                  branch: str = "vitals") -> list[Path]:
    """Write snapshots/<date>.json, history.ndjson, VITALS.json, REPORT.md,
    index.html, and badge/*.json under out_dir."""
    out = Path(out_dir)
    (out / "snapshots").mkdir(parents=True, exist_ok=True)
    (out / "badge").mkdir(parents=True, exist_ok=True)

    paths = []

    def write_json(relpath, payload):
        path = out / relpath
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
        paths.append(path)

    write_json(f"snapshots/{snapshot['date']}.json", snapshot)

    history_path = out / "history.ndjson"
    history_path.write_text(dump_history(history), encoding="utf-8")
    paths.append(history_path)

    write_json("VITALS.json", build_vitals(snapshot, history))

    report_path = out / "REPORT.md"
    report_path.write_text(render_report(snapshot, history, branch=branch),
                           encoding="utf-8")
    paths.append(report_path)

    dashboard_path = out / "index.html"
    dashboard_path.write_text(render_dashboard(), encoding="utf-8")
    paths.append(dashboard_path)

    for name, payload in build_badges(snapshot, compute_derived(snapshot, history)).items():
        write_json(f"badge/{name}", payload)

    return paths
