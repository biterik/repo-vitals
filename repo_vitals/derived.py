# Author: Erik Bitzek <e.bitzek@mpi-susmat.de>
# Department of Materials Science, WW8-Materials Simulation,
# Friedrich-Alexander-Universität Erlangen-Nürnberg,
# Dr.-Mack-Straße 77, 90762 Fürth, Germany
"""Derived metrics — computed at render time, never stored in history (§4).

Everything here is a pure function of the merged per-day history plus the
latest snapshot. The health score and the star-milestone forecasts are
clearly-labeled heuristics: simple, explainable formulas, not analytics.
Weights become configurable when the config file lands (v1.1).
"""

from __future__ import annotations

import datetime as dt
import math

HEALTH_WEIGHTS = {
    "traffic_trend": 0.4,
    "activity": 0.3,
    "community": 0.2,
    "release_adoption": 0.1,
}

STAR_MILESTONES = [10, 25, 50, 100, 250, 500, 1000, 2500, 5000,
                   10000, 25000, 50000, 100000]

FORECAST_WINDOW_DAYS = 90
FORECAST_HORIZON_DAYS = 3650  # ETAs beyond ~10 years are noise, report None


def compute_derived(snapshot: dict, history: dict[str, dict]) -> dict:
    end = dt.date.fromisoformat(snapshot["date"])
    views_7d = window_sum(history, "views", end, 7)
    views_prev_7d = range_sum(history, "views",
                              end - dt.timedelta(days=13), end - dt.timedelta(days=7))
    stars = star_series(history)
    downloads = downloads_series(history)
    # a backfilled star history starts at repo birth, so before it stars were 0
    stars_from_birth = any("stars_cumulative" in rec for rec in history.values())
    stars_gained_30d = series_gained(stars, end, 30, assume_zero_before=stars_from_birth)
    downloads_gained_30d = series_gained(downloads, end, 30)

    windows = {}
    for days in (30, 90, 365):
        windows[f"{days}d"] = {
            "views": window_sum(history, "views", end, days),
            "unique_visitors": window_sum(history, "views", end, days, field="uniques"),
            "clones": window_sum(history, "clones", end, days),
            "stars_gained": series_gained(stars, end, days,
                                          assume_zero_before=stars_from_birth),
            "downloads_gained": series_gained(downloads, end, days),
        }

    return {
        "views_last_7d": views_7d,
        "views_prev_7d": views_prev_7d,
        "views_last_30d": window_sum(history, "views", end, 30),
        "clones_last_7d": window_sum(history, "clones", end, 7),
        "clones_last_30d": window_sum(history, "clones", end, 30),
        "stars_now": stars[-1][1] if stars else _snapshot_stars(snapshot),
        "stars_gained_7d": series_gained(stars, end, 7, assume_zero_before=stars_from_birth),
        "stars_gained_30d": stars_gained_30d,
        "downloads_total": downloads[-1][1] if downloads else None,
        "downloads_gained_30d": downloads_gained_30d,
        "windows": windows,
        "funnel_30d": {
            "unique_visitors": windows["30d"]["unique_visitors"],
            "unique_cloners": window_sum(history, "clones", end, 30, field="uniques"),
            "stars_gained": stars_gained_30d,
            "downloads_gained": downloads_gained_30d,
        },
        "star_forecast": star_forecast(stars, end),
        "health": compute_health(snapshot, views_7d, views_prev_7d,
                                 stars_gained_30d, downloads_gained_30d),
        "history_days": len(history),
    }


def _snapshot_stars(snapshot):
    return (snapshot.get("popularity") or {}).get("stars")


# ---------------------------------------------------------------- series

def window_sum(history, kind, end, days, field="count"):
    """Sum of a daily traffic field over the trailing window; None if no data."""
    return range_sum(history, kind, end - dt.timedelta(days=days - 1), end, field=field)


def range_sum(history, kind, start, end, field="count"):
    values = [
        rec[kind][field]
        for day, rec in history.items()
        if start.isoformat() <= day <= end.isoformat() and kind in rec
    ]
    return sum(values) if values else None


def star_series(history):
    """Sorted (date, stars) observations. The live API count (popularity.stars)
    wins over the first-run backfill (stars_cumulative) — it reflects un-stars."""
    out = []
    for day in sorted(history):
        rec = history[day]
        pop = rec.get("popularity")
        if pop and pop.get("stars") is not None:
            out.append((day, pop["stars"]))
        elif "stars_cumulative" in rec:
            out.append((day, rec["stars_cumulative"]))
    return out


def downloads_series(history):
    """Sorted (date, total release downloads) from the per-day release records."""
    return [
        (day, sum(r.get("downloads", 0) for r in history[day]["releases"]))
        for day in sorted(history)
        if "releases" in history[day]
    ]


def series_gained(series, end, days, assume_zero_before=False):
    """Value now minus value at/just before the window start; None if empty.

    When the window reaches back before the first observation, the baseline is
    the earliest observation (conservative — pre-instrumentation counts are
    unknown), unless assume_zero_before is set: correct for series known to
    start at repo birth, i.e. a backfilled star history, where the value
    before the first star event really was 0."""
    if not series:
        return None
    start = (end - dt.timedelta(days=days)).isoformat()
    base = None
    for day, value in series:
        if day <= start:
            base = value
        else:
            break
    if base is None:
        base = 0 if assume_zero_before else series[0][1]
    return series[-1][1] - base


# ---------------------------------------------------------------- forecast

def linear_fit(points):
    """Least-squares (slope, intercept) for [(x, y)]; slope 0 for degenerate x."""
    n = len(points)
    sx = sum(x for x, _ in points)
    sy = sum(y for _, y in points)
    sxx = sum(x * x for x, _ in points)
    sxy = sum(x * y for x, y in points)
    denom = n * sxx - sx * sx
    if denom == 0:
        return 0.0, sy / n
    slope = (n * sxy - sx * sy) / denom
    return slope, (sy - slope * sx) / n


def star_forecast(series, end):
    """ETA to the next star milestone from naive linear and exponential fits
    over the last 90 days. Explicitly a toy extrapolation, labeled as such."""
    result = {"next_milestone": None, "eta_linear": None,
              "eta_exponential": None, "stars_per_day": None}
    if not series:
        return result
    stars_now = series[-1][1]
    milestone = next((m for m in STAR_MILESTONES if m > stars_now), None)
    result["next_milestone"] = milestone

    cutoff = (end - dt.timedelta(days=FORECAST_WINDOW_DAYS)).isoformat()
    points = [(dt.date.fromisoformat(d).toordinal(), s) for d, s in series if d >= cutoff]
    if milestone is None or len(points) < 2:
        return result

    slope, _ = linear_fit(points)
    result["stars_per_day"] = round(slope, 4)
    if slope > 1e-9:
        days = (milestone - stars_now) / slope
        if days <= FORECAST_HORIZON_DAYS:
            result["eta_linear"] = (end + dt.timedelta(days=days)).isoformat()

    if all(y > 0 for _, y in points):
        b, a = linear_fit([(x, math.log(y)) for x, y in points])
        if b > 1e-9:
            days = (math.log(milestone) - a) / b - points[-1][0]
            if 0 <= days <= FORECAST_HORIZON_DAYS:
                result["eta_exponential"] = (end + dt.timedelta(days=days)).isoformat()
    return result


# ---------------------------------------------------------------- health

def compute_health(snapshot, views_last_7d, views_prev_7d,
                   stars_gained_30d, downloads_gained_30d):
    """Composite 0–100 health score (§4) — a labeled heuristic, not a truth.

    Component formulas (each clamped to 0–100):
      traffic_trend     50 * (views last 7d / previous 7d); 0 if dead, 100 if new
      activity          4*commits + 8*PRs merged + 3*PRs opened
                        + 3*issues closed + 2*issues opened (all 30d)
      community         8*contributors + 2*forks + 3*subscribers + 4*stars gained 30d
      release_adoption  10 + downloads gained 30d (0 without releases)
    """
    activity = snapshot.get("activity") or {}
    popularity = snapshot.get("popularity") or {}

    if not views_last_7d:
        traffic_trend = 0
    elif not views_prev_7d:
        traffic_trend = 100
    else:
        traffic_trend = max(0, min(100, round(50 * views_last_7d / views_prev_7d)))

    activity_score = min(100, (
        4 * activity.get("commits_30d", 0)
        + 8 * activity.get("prs_merged_30d", 0)
        + 3 * activity.get("prs_opened_30d", 0)
        + 3 * activity.get("issues_closed_30d", 0)
        + 2 * activity.get("issues_opened_30d", 0)
    ))

    community = min(100, (
        8 * activity.get("contributors_total", 0)
        + 2 * (popularity.get("forks") or 0)
        + 3 * (popularity.get("subscribers") or 0)
        + 4 * (stars_gained_30d or 0)
    ))

    if not snapshot.get("releases"):
        release_adoption = 0
    else:
        release_adoption = min(100, 10 + (downloads_gained_30d or 0))

    components = {
        "traffic_trend": traffic_trend,
        "activity": activity_score,
        "community": community,
        "release_adoption": release_adoption,
    }
    score = round(sum(HEALTH_WEIGHTS[k] * v for k, v in components.items()))
    return {
        "score": score,
        "components": components,
        "weights": HEALTH_WEIGHTS,
        "note": "heuristic composite — weights fixed in v1, configurable later",
    }
