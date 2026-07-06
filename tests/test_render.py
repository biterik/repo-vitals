# Author: Erik Bitzek <e.bitzek@mpi-susmat.de>
# Department of Materials Science, WW8-Materials Simulation,
# Friedrich-Alexander-Universität Erlangen-Nürnberg,
# Dr.-Mack-Straße 77, 90762 Fürth, Germany
"""REPORT.md rendering, badges, and render-from-data-alone (§7.9)."""

import json

from conftest import make_snapshot, window

from repo_vitals.cli import main
from repo_vitals.derived import compute_derived
from repo_vitals.merge import merge_snapshot
from repo_vitals.render import build_badges, render_report, slugify, sparkline, write_outputs


def rich_snapshot(date="2026-07-06"):
    return make_snapshot(
        date,
        views=window(date),
        clones=window(date, base=1),
        stars=53,
        referrers=[{"referrer": "reddit.com", "count": 31, "uniques": 22}],
        paths=[{"path": "/biterik/example", "count": 50, "uniques": 31}],
        releases=[{"tag": "v1.3", "published_at": "2026-06-20T10:00:00Z",
                   "assets": [{"name": "a.zip", "downloads": 182}]}],
        activity={"commits_30d": 14, "prs_opened_30d": 3, "prs_merged_30d": 2,
                  "issues_opened_30d": 5, "issues_closed_30d": 4,
                  "contributors_total": 7},
    )


def test_report_shows_key_numbers():
    snap = rich_snapshot()
    history = merge_snapshot({}, snap)
    report = render_report(snap, history)

    assert "biterik/example" in report
    assert "| Metric | 30 d | 90 d | 365 d |" in report
    assert "Stars: **53**" in report
    assert "reddit.com" in report
    assert "`/biterik/example`" in report
    assert "v1.3" in report and "182" in report
    assert "14 commits" in report
    assert "Health:" in report and "/100" in report
    assert "Conversion funnel (30 d):" in report
    assert "img.shields.io/endpoint" in report
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
    snap["activity"] = None
    report = render_report(snap, merge_snapshot({}, snap))
    assert "No releases." in report
    assert "–" in report  # unknown values render as dashes, never crash


def test_sparkline_maps_range_and_gaps():
    assert sparkline([0, 7, 3, None, 7]) == "▁█▄·█"
    assert sparkline([5, 5, 5]) == "▁▁▁"
    assert sparkline([None, None]) == ""


def test_badges_are_valid_shields_endpoints():
    snap = rich_snapshot()
    history = merge_snapshot({}, snap)
    badges = build_badges(snap, compute_derived(snap, history))

    assert set(badges) == {"stars.json", "views-week.json", "health.json"}
    for payload in badges.values():
        assert payload["schemaVersion"] == 1
        assert payload["label"] and payload["message"] and payload["color"]
    assert badges["stars.json"]["message"].startswith("53")
    assert badges["health.json"]["message"].endswith("/100")


def test_badge_views_trend_colors():
    snap = rich_snapshot()
    history = merge_snapshot({}, snap)
    derived = compute_derived(snap, history)

    derived["views_last_7d"], derived["views_prev_7d"] = 20, 10
    assert build_badges(snap, derived)["views-week.json"]["color"] == "brightgreen"
    derived["views_last_7d"], derived["views_prev_7d"] = 5, 10
    assert build_badges(snap, derived)["views-week.json"]["color"] == "orange"
    derived["views_last_7d"] = None
    assert build_badges(snap, derived)["views-week.json"]["message"] == "no data"


def test_write_outputs_includes_badges(tmp_path):
    snap = rich_snapshot()
    history = merge_snapshot({}, snap)
    write_outputs(tmp_path, snap, history)
    for name in ("stars.json", "views-week.json", "health.json"):
        payload = json.loads((tmp_path / "badge" / name).read_text())
        assert payload["schemaVersion"] == 1


def test_slugify_makes_filename_safe_identifiers():
    assert slugify("biterik/repo-vitals") == "biterik-repo-vitals"
    assert slugify("My Repo Fleet!!") == "my-repo-fleet"
    assert slugify("") == "report"


def test_write_outputs_archives_a_dated_repo_qualified_report(tmp_path):
    """Alongside the stable REPORT.md, a copy named with the repo and the
    date should always exist — safe to download standalone without
    colliding with another repo's or another day's report."""
    snap = rich_snapshot(date="2026-07-06")
    history = merge_snapshot({}, snap)
    paths = write_outputs(tmp_path, snap, history)

    archive_path = tmp_path / "reports" / "biterik-example-2026-07-06.md"
    assert archive_path in paths
    assert archive_path.read_text() == (tmp_path / "REPORT.md").read_text()


def test_render_subcommand_rebuilds_from_data_alone(tmp_path):
    """§7.9 determinism: the vitals branch is self-sufficient."""
    snap = rich_snapshot()
    history = merge_snapshot({}, snap)
    write_outputs(tmp_path, snap, history)
    report_before = (tmp_path / "REPORT.md").read_text()
    vitals_before = (tmp_path / "VITALS.json").read_text()

    (tmp_path / "REPORT.md").unlink()
    (tmp_path / "VITALS.json").unlink()
    assert main(["render", "--data-dir", str(tmp_path)]) == 0

    assert (tmp_path / "REPORT.md").read_text() == report_before
    assert (tmp_path / "VITALS.json").read_text() == vitals_before


def test_render_subcommand_errors_without_snapshots(tmp_path):
    assert main(["render", "--data-dir", str(tmp_path)]) == 2


def test_dashboard_is_self_contained(tmp_path):
    """§3.4: single file, one pinned CDN dependency, data via relative fetch."""
    snap = rich_snapshot()
    history = merge_snapshot({}, snap)
    write_outputs(tmp_path, snap, history)
    html = (tmp_path / "index.html").read_text()

    # exactly one external resource: the pinned ECharts build
    assert html.count("<script src=") == 1
    assert "echarts@5.5.1" in html
    assert "<link" not in html  # CSS is inline
    # data comes from relative fetches, so the file carries no repo state
    assert 'fetch("VITALS.json")' in html
    assert 'fetch("history.ndjson")' in html
    # release-impact overlay, dark mode, mobile viewport
    assert "markLine" in html
    assert "prefers-color-scheme" in html
    assert 'name="viewport"' in html
