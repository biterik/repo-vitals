"""Traffic-window merge — THE critical correctness tests (ARCHITECTURE.md §5).

The traffic API returns a rolling 14-day window; consecutive runs overlap
~13 days and GitHub retro-adjusts recent days. Newer run wins per day; a
missed run <= 13 days loses nothing; a gap > 14 days leaves an explicit hole.
"""

import copy
import datetime as dt
import json

from conftest import make_snapshot, window

from repo_vitals.merge import (
    dump_history,
    load_history,
    merge_snapshot,
    rebuild_history,
    summarize_releases,
)


def days_with(history, kind):
    return sorted(day for day, rec in history.items() if kind in rec)


def test_consecutive_runs_overlap_newer_wins():
    """Day 2's window overlaps 13 days with day 1's; newer values win."""
    w1 = window("2026-07-01")
    w2 = window("2026-07-02")
    # GitHub retro-adjusted 2026-06-30 upward between the two runs
    w2["2026-06-30"] = 999

    history = {}
    merge_snapshot(history, make_snapshot("2026-07-01", views=w1))
    merge_snapshot(history, make_snapshot("2026-07-02", views=w2))

    assert history["2026-06-30"]["views"]["count"] == 999
    # oldest day of window 1 fell out of window 2 but is preserved
    assert history["2026-06-18"]["views"]["count"] == w1["2026-06-18"]
    # union covers both windows: 06-18 .. 07-02 with no holes
    assert days_with(history, "views") == [
        (dt.date(2026, 6, 18) + dt.timedelta(days=i)).isoformat() for i in range(15)
    ]


def test_missed_runs_within_window_lose_nothing():
    """13 days between runs: the two 14-day windows still tile without a hole."""
    history = {}
    merge_snapshot(history, make_snapshot("2026-07-01", views=window("2026-07-01")))
    merge_snapshot(history, make_snapshot("2026-07-14", views=window("2026-07-14")))

    expected = [
        (dt.date(2026, 6, 18) + dt.timedelta(days=i)).isoformat() for i in range(27)
    ]
    assert days_with(history, "views") == expected


def test_gap_beyond_window_leaves_explicit_hole():
    """> 14 days without a run: missing days stay missing (never interpolate)."""
    history = {}
    merge_snapshot(history, make_snapshot("2026-06-01", views=window("2026-06-01")))
    merge_snapshot(history, make_snapshot("2026-07-01", views=window("2026-07-01")))

    have = days_with(history, "views")
    assert "2026-06-01" in have and "2026-07-01" in have
    # the hole: nothing between the end of window 1 and the start of window 2
    hole = [d for d in have if "2026-06-02" <= d <= "2026-06-17"]
    assert hole == []


def test_same_day_rerun_is_idempotent_and_overwrites():
    """A second run on the same UTC day replaces the first (one snapshot per day)."""
    history = {}
    s1 = make_snapshot("2026-07-06", collected_at="2026-07-06T03:17:00Z",
                       views={"2026-07-05": 5}, stars=50)
    s2 = make_snapshot("2026-07-06", collected_at="2026-07-06T15:00:00Z",
                       views={"2026-07-05": 7}, stars=51)
    merge_snapshot(history, s1)
    merge_snapshot(history, s2)

    assert history["2026-07-05"]["views"]["count"] == 7
    assert history["2026-07-06"]["popularity"]["stars"] == 51

    # merging the same snapshot again changes nothing
    before = copy.deepcopy(history)
    merge_snapshot(history, s2)
    assert history == before


def test_out_of_order_merge_never_clobbers_newer_data():
    """Backfilling an older raw snapshot after a newer one must not regress values."""
    older = make_snapshot("2026-07-01", views=window("2026-07-01"))
    newer = make_snapshot("2026-07-02", views=window("2026-07-02"))

    in_order = rebuild_history([older, newer])
    reversed_merge = {}
    merge_snapshot(reversed_merge, newer)
    merge_snapshot(reversed_merge, older)

    assert reversed_merge == in_order


def test_rebuild_from_raw_snapshots_matches_incremental():
    """history.ndjson must be fully regenerable from the snapshot audit trail."""
    snaps = [
        make_snapshot("2026-07-01", views=window("2026-07-01")),
        make_snapshot("2026-07-02", views=window("2026-07-02")),
        make_snapshot("2026-07-05", views=window("2026-07-05"), stars=60),
    ]
    incremental = {}
    for s in snaps:
        merge_snapshot(incremental, s)
    assert rebuild_history(list(reversed(snaps))) == incremental


def test_snapshot_without_traffic_still_records_point_in_time():
    """No traffic token: popularity/releases/activity still land in history."""
    history = {}
    snap = make_snapshot(
        "2026-07-06",
        traffic_present=False,
        stars=42,
        releases=[{"tag": "v1.0", "published_at": "2026-01-01T00:00:00Z",
                   "assets": [{"name": "a.zip", "downloads": 100},
                              {"name": "b.zip", "downloads": 20}]}],
    )
    merge_snapshot(history, snap)

    rec = history["2026-07-06"]
    assert rec["popularity"]["stars"] == 42
    assert rec["releases"] == [{"tag": "v1.0", "downloads": 120}]
    assert "views" not in rec


def test_clones_and_views_merge_independently_per_day():
    history = {}
    merge_snapshot(history, make_snapshot("2026-07-01",
                                          views={"2026-06-30": 10},
                                          clones={"2026-06-29": 3}))
    assert history["2026-06-30"]["views"]["count"] == 10
    assert "clones" not in history["2026-06-30"]
    assert history["2026-06-29"]["clones"]["count"] == 3


def test_summarize_releases_totals_assets():
    releases = [
        {"tag": "v2", "assets": [{"name": "x", "downloads": 5}]},
        {"tag": "v1", "assets": []},
    ]
    assert summarize_releases(releases) == [
        {"tag": "v2", "downloads": 5},
        {"tag": "v1", "downloads": 0},
    ]


def test_history_roundtrip_ndjson(tmp_path):
    history = {}
    merge_snapshot(history, make_snapshot("2026-07-01", views=window("2026-07-01")))
    merge_snapshot(history, make_snapshot("2026-07-02", views=window("2026-07-02")))

    path = tmp_path / "history.ndjson"
    path.write_text(dump_history(history), encoding="utf-8")
    assert load_history(path) == history

    # one line per day, sorted by date
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == len(history)
    dates = [json.loads(line)["date"] for line in lines]
    assert dates == sorted(dates)


def test_load_history_missing_file_is_empty(tmp_path):
    assert load_history(tmp_path / "nope.ndjson") == {}
