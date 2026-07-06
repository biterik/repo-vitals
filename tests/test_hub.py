# Author: Erik Bitzek <e.bitzek@mpi-susmat.de>
# Department of Materials Science, WW8-Materials Simulation,
# Friedrich-Alexander-Universität Erlangen-Nürnberg,
# Dr.-Mack-Straße 77, 90762 Fürth, Germany
"""Hub (§3.5): config parsing, staleness watchdog, aggregate outputs."""

import datetime as dt
import json

import pytest

from repo_vitals.hub import (
    build_hub,
    fetch_repo_status,
    load_hub_config,
    parse_simple_yaml,
)

NOW = dt.datetime(2026, 7, 6, 12, 0, 0, tzinfo=dt.UTC)


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.text = text if text else (json.dumps(json_data) if json_data is not None else "")

    def json(self):
        if self._json is None:
            raise ValueError("not json")
        return self._json


class FakeSession:
    def __init__(self, routes):
        self.routes = routes

    def get(self, url, timeout=None):
        return self.routes.get(url, FakeResponse(404))


def vitals_payload(repo, collected_at, stars=10, views=100):
    return {
        "repo": repo,
        "collected_at": collected_at,
        "derived": {
            "stars_now": stars,
            "views_last_30d": views,
            "clones_last_30d": 5,
            "downloads_total": 42,
            "health": {"score": 61},
        },
    }


def routes_for(repo, payload, history_lines=""):
    base = f"https://raw.githubusercontent.com/{repo}/vitals"
    return {
        f"{base}/VITALS.json": FakeResponse(200, payload),
        f"{base}/history.ndjson": FakeResponse(200, text=history_lines),
    }


# ---------------------------------------------------------------- config

def test_parse_simple_yaml_subset():
    cfg = parse_simple_yaml(
        "# comment\n"
        'title: "My fleet"\n'
        "stale_after_days: 5\n"
        "repos:\n"
        "  - biterik/a   # inline comment\n"
        "  - biterik/b\n"
    )
    assert cfg == {"title": "My fleet", "stale_after_days": "5",
                   "repos": ["biterik/a", "biterik/b"]}


def test_parse_simple_yaml_rejects_fancy_syntax():
    with pytest.raises(ValueError, match="unsupported syntax"):
        parse_simple_yaml("repos:\n  nested:\n    - x\n")


def test_load_hub_config_defaults_and_required(tmp_path):
    path = tmp_path / "hub-config.yml"
    path.write_text("repos:\n  - biterik/a\n")
    cfg = load_hub_config(path)
    assert cfg["title"] == "repo-vitals hub"
    assert cfg["stale_after_days"] == 3
    assert cfg["branch"] == "vitals"

    path.write_text("title: x\n")
    with pytest.raises(ValueError, match="repos"):
        load_hub_config(path)


# ---------------------------------------------------------------- watchdog

def test_fresh_repo_is_ok():
    repo = "biterik/fresh"
    session = FakeSession(routes_for(repo, vitals_payload(repo, "2026-07-06T03:17:00Z")))
    entry = fetch_repo_status(session, repo, now=NOW)
    assert entry["status"] == "ok"
    assert entry["days_since_update"] == 0
    assert entry["stars"] == 10 and entry["health_score"] == 61


def test_stale_repo_is_flagged():
    repo = "biterik/sleepy"
    session = FakeSession(routes_for(repo, vitals_payload(repo, "2026-07-01T03:17:00Z")))
    entry = fetch_repo_status(session, repo, now=NOW)
    assert entry["status"] == "stale"
    assert entry["days_since_update"] == 5
    assert "expired traffic PAT" in entry["detail"]


def test_exactly_at_threshold_is_still_ok():
    repo = "biterik/borderline"
    session = FakeSession(routes_for(repo, vitals_payload(repo, "2026-07-03T03:17:00Z")))
    assert fetch_repo_status(session, repo, now=NOW, stale_after_days=3)["status"] == "ok"


def test_uninstrumented_repo_is_missing():
    entry = fetch_repo_status(FakeSession({}), "biterik/bare", now=NOW)
    assert entry["status"] == "missing"
    assert "not installed" in entry["detail"]


def test_series_trimmed_from_history():
    repo = "biterik/fresh"
    history = "\n".join([
        json.dumps({"date": "2025-01-01", "views": {"count": 9, "uniques": 1}}),  # old, cut
        json.dumps({"date": "2026-07-01", "views": {"count": 3, "uniques": 1},
                    "popularity": {"stars": 8}}),
        json.dumps({"date": "2026-07-05", "stars_cumulative": 9}),
    ])
    session = FakeSession(routes_for(repo, vitals_payload(repo, "2026-07-06T03:17:00Z"),
                                     history_lines=history))
    series = fetch_repo_status(session, repo, now=NOW)["series"]
    assert series["views"] == [["2026-07-01", 3]]
    assert series["stars"] == [["2026-07-01", 8], ["2026-07-05", 9]]


# ---------------------------------------------------------------- build

def hub_config(repos):
    return {"title": "Test fleet", "branch": "vitals", "stale_after_days": 3,
            "repos": repos}


def test_build_hub_outputs_and_watchdog(tmp_path):
    fresh, stale = "biterik/fresh", "biterik/sleepy"
    routes = {}
    routes.update(routes_for(fresh, vitals_payload(fresh, "2026-07-06T03:17:00Z", stars=7)))
    routes.update(routes_for(stale, vitals_payload(stale, "2026-06-20T03:17:00Z", stars=3)))
    session = FakeSession(routes)

    summary = build_hub(hub_config([fresh, stale, "biterik/bare"]), tmp_path,
                        session=session, now=NOW)

    assert summary["flagged"] == [stale, "biterik/bare"]
    assert summary["totals"] == {"repos": 3, "ok": 1, "stars": 10, "views_30d": 200,
                                 "clones_30d": 10, "downloads_total": 84}

    data = json.loads((tmp_path / "hub-data.json").read_text())
    assert [e["status"] for e in data["repos"]] == ["ok", "stale", "missing"]

    report = (tmp_path / "REPORT.md").read_text()
    assert "Watchdog: 2 repositories need attention" in report
    assert "biterik/sleepy" in report and "`stale`" in report
    assert "biterik/bare" in report and "`missing`" in report
    assert "| **Total** | | **10** |" in report

    html = (tmp_path / "index.html").read_text()
    assert 'fetch("hub-data.json")' in html
    assert html.count("<script src=") == 1 and "echarts@5.5.1" in html


def test_build_hub_all_missing_still_writes_site(tmp_path):
    summary = build_hub(hub_config(["biterik/a", "biterik/b"]), tmp_path,
                        session=FakeSession({}), now=NOW)
    assert summary["totals"]["ok"] == 0
    assert (tmp_path / "REPORT.md").exists()
