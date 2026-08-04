# Author: Erik Bitzek <e.bitzek@mpi-susmat.de>
# Department of Materials Science, WW8-Materials Simulation,
# Friedrich-Alexander-Universität Erlangen-Nürnberg,
# Dr.-Mack-Straße 77, 90762 Fürth, Germany
"""Derived metrics (§4): growth windows, funnel, forecasts, tracking span."""

import datetime as dt

from conftest import make_snapshot, window

from repo_vitals.derived import (
    compute_derived,
    linear_fit,
    rate,
    series_gained,
    star_forecast,
    star_series,
    tracking_span,
)
from repo_vitals.merge import merge_snapshot, merge_star_backfill

END = dt.date(2026, 7, 6)


def history_with_stars(pairs):
    """{date: stars} -> history with popularity observations."""
    return {
        day: {"date": day, "popularity": {"stars": stars, "forks": 0,
                                          "watchers": stars, "subscribers": 0}}
        for day, stars in pairs.items()
    }


def test_star_series_prefers_live_count_over_backfill():
    history = merge_star_backfill({}, ["2026-07-01", "2026-07-01"])
    history["2026-07-01"]["popularity"] = {"stars": 1}  # one un-star happened
    assert star_series(history) == [("2026-07-01", 1)]


def test_series_gained_windows():
    series = [("2026-05-01", 10), ("2026-06-06", 20), ("2026-07-06", 35)]
    assert series_gained(series, END, 30) == 15   # baseline = 06-06 (on window start)
    assert series_gained(series, END, 90) == 25   # baseline = 05-01
    # window reaching back before any data falls back to earliest observation
    assert series_gained([("2026-07-01", 5), ("2026-07-06", 8)], END, 365) == 3
    # ... unless the series is known to start at repo birth (backfilled stars)
    assert series_gained([("2026-07-01", 5), ("2026-07-06", 8)], END, 365,
                         assume_zero_before=True) == 8
    assert series_gained([], END, 30) is None


def test_linear_fit_recovers_slope():
    slope, intercept = linear_fit([(x, 3 * x + 7) for x in range(10)])
    assert abs(slope - 3) < 1e-9 and abs(intercept - 7) < 1e-9


def test_forecast_linear_eta():
    # 1 star/day for 10 days, at 10 stars on 07-06 -> milestone 25 in ~15 days
    pairs = {(END - dt.timedelta(days=9 - i)).isoformat(): i + 1 for i in range(10)}
    forecast = star_forecast(star_series(history_with_stars(pairs)), END)
    assert forecast["next_milestone"] == 25
    assert abs(forecast["stars_per_day"] - 1.0) < 1e-6
    eta = dt.date.fromisoformat(forecast["eta_linear"])
    assert abs((eta - END).days - 15) <= 1


def test_forecast_flat_series_has_no_eta():
    pairs = {(END - dt.timedelta(days=i)).isoformat(): 5 for i in range(10)}
    forecast = star_forecast(star_series(history_with_stars(pairs)), END)
    assert forecast["next_milestone"] == 10
    assert forecast["eta_linear"] is None
    assert forecast["eta_exponential"] is None


def test_forecast_exponential_beats_linear_for_growth():
    # doubling every ~3 days: exponential ETA should be sooner than linear's
    pairs = {}
    stars = 1
    for i in range(12):
        pairs[(END - dt.timedelta(days=11 - i)).isoformat()] = stars
        stars = round(stars * 1.3) + 1
    forecast = star_forecast(star_series(history_with_stars(pairs)), END)
    assert forecast["eta_linear"] and forecast["eta_exponential"]
    assert forecast["eta_exponential"] <= forecast["eta_linear"]


def test_tracking_span_ignores_backfilled_star_days():
    """The star backfill reaches back to repo birth; it is not tracking data."""
    history = merge_star_backfill({}, ["2025-10-09"])  # a star, long before install
    merge_snapshot(history, make_snapshot("2026-07-06", views=window("2026-07-06")))
    first, days = tracking_span(history, END)
    assert first == "2026-06-23"            # 14-day traffic window, not 2025-10-09
    assert days == 14
    assert len(history) == 15               # history_days would have said 15


def test_tracking_span_without_traffic_is_unknown():
    assert tracking_span({}, END) == (None, None)
    assert tracking_span(merge_star_backfill({}, ["2026-01-01"]), END) == (None, None)


def test_rate_is_a_per_30_day_average():
    assert rate(300, 30) == 300.0
    assert rate(300, 60) == 150.0
    assert rate(43, 43) == 30.0
    assert rate(None, 30) is None and rate(300, None) is None and rate(300, 0) is None


def test_totals_and_averages_cover_the_whole_archive():
    snap = make_snapshot("2026-07-06", views=window("2026-07-06", base=10),
                         clones=window("2026-07-06", base=1))
    history = merge_snapshot({}, snap)
    d = compute_derived(snap, history)

    expected_views = sum(window("2026-07-06", base=10).values())
    assert d["totals"]["views"] == expected_views
    assert d["tracking_days"] == 14
    assert d["per_30d"]["views"] == round(expected_views * 30 / 14, 1)
    # the 30d window and the all-time total agree while the archive is younger
    assert d["totals"]["views"] == d["views_last_30d"]


def test_compute_derived_end_to_end():
    snap = make_snapshot("2026-07-06", views=window("2026-07-06", base=10),
                         clones=window("2026-07-06", base=1), stars=50,
                         releases=[{"tag": "v1", "published_at": None,
                                    "assets": [{"name": "a", "downloads": 120}]}])
    history = merge_star_backfill({}, ["2026-01-01"] * 30 + ["2026-06-20"] * 15)
    merge_snapshot(history, snap)
    d = compute_derived(snap, history)

    assert d["views_last_7d"] == sum(v for day, v in window("2026-07-06", base=10).items()
                                     if day >= "2026-06-30")
    assert d["stars_now"] == 50  # live popularity beats backfill total (45)
    assert d["stars_gained_30d"] == 20  # 30 at window start -> 50 now
    assert d["downloads_total"] == 120
    # backfill covers repo birth, so the 365d window counts from 0 stars
    assert d["windows"]["365d"]["stars_gained"] == 50
    assert d["funnel_30d"]["unique_visitors"] == d["windows"]["30d"]["unique_visitors"]
    assert d["star_forecast"]["next_milestone"] == 100
    assert "health" not in d
    assert d["repo_created_at"] is None  # make_snapshot's meta carries no created_at
    assert d["tracking_since"] == "2026-06-23" and d["tracking_days"] == 14
