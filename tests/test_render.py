"""REPORT.md rendering (minimal M2 report)."""

from conftest import make_snapshot, window

from repo_vitals.merge import merge_snapshot
from repo_vitals.render import render_report


def test_report_shows_key_numbers():
    snap = make_snapshot(
        "2026-07-06",
        views=window("2026-07-06"),
        stars=53,
        releases=[{"tag": "v1.3", "published_at": "2026-06-20T10:00:00Z",
                   "assets": [{"name": "a.zip", "downloads": 182}]}],
        activity={"commits_30d": 14, "prs_opened_30d": 3, "prs_merged_30d": 2,
                  "issues_opened_30d": 5, "issues_closed_30d": 4,
                  "contributors_total": 7},
    )
    history = merge_snapshot({}, snap)
    report = render_report(snap, history)

    assert "biterik/example" in report
    assert "| Stars | 53 |" in report
    assert "v1.3" in report and "182" in report
    assert "14 commits" in report
    assert "Traffic collection is failing" not in report


def test_report_surfaces_failing_traffic_pat():
    """§7.6b: an expired traffic PAT is the most likely silent failure."""
    old = make_snapshot("2026-07-01", views={"2026-06-30": 9})
    history = merge_snapshot({}, old)

    snap = make_snapshot("2026-07-06", traffic_present=False)
    snap["errors"] = [{"section": "traffic", "error": "HTTP 403"}]
    merge_snapshot(history, snap)
    report = render_report(snap, history)

    assert "Traffic collection is failing" in report
    assert "2026-06-30" in report  # last day with traffic data


def test_report_handles_empty_new_repo():
    snap = make_snapshot("2026-07-06", traffic_present=False, releases=[])
    report = render_report(snap, merge_snapshot({}, snap))
    assert "No releases." in report
