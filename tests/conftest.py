# Author: Erik Bitzek <e.bitzek@mpi-susmat.de>
# Department of Materials Science, WW8-Materials Simulation,
# Friedrich-Alexander-Universität Erlangen-Nürnberg,
# Dr.-Mack-Straße 77, 90762 Fürth, Germany
import datetime as dt
import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_snapshot(
    date,
    collected_at=None,
    views=None,
    clones=None,
    stars=None,
    referrers=None,
    paths=None,
    releases=None,
    activity=None,
    traffic_present=True,
):
    """A minimal valid snapshot for merge tests.

    views/clones: {"YYYY-MM-DD": count} shorthand (uniques = count // 2).
    """

    def per_day(shorthand):
        return {
            day: {"count": count, "uniques": count // 2}
            for day, count in (shorthand or {}).items()
        }

    traffic = None
    if traffic_present:
        traffic = {
            "views": per_day(views),
            "clones": per_day(clones),
            "referrers": referrers or [],
            "paths": paths or [],
        }
    return {
        "schema_version": 1,
        "date": date,
        "collected_at": collected_at or f"{date}T03:17:00Z",
        "repo": "biterik/example",
        "popularity": {
            "stars": stars if stars is not None else 10,
            "forks": 2,
            "watchers": 10,
            "subscribers": 3,
        },
        "traffic": traffic,
        "releases": releases if releases is not None else [],
        "activity": activity,
        "meta": {"fork": False, "archived": False},
        "errors": [],
    }


def window(end_date, days=14, base=10):
    """A rolling traffic window ending at end_date: {date: count} for `days` days."""
    end = dt.date.fromisoformat(end_date)
    return {
        (end - dt.timedelta(days=offset)).isoformat(): base + offset
        for offset in range(days)
    }
