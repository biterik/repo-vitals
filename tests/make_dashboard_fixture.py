"""Generate a realistic offline fixture dataset for eyeballing the dashboard.

Usage:  python tests/make_dashboard_fixture.py <output-dir>
Then:   python -m http.server -d <output-dir>  ->  open http://localhost:8000

120 days of synthetic history for a fictional repo: weekly traffic rhythm,
two releases with visible traffic spikes (to check the release-impact
overlay), growing stars, download curves, a 5-day collection gap (to check
that gaps stay gaps), and one collection warning.
"""

import datetime as dt
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from repo_vitals.merge import dump_history, merge_star_backfill  # noqa: E402
from repo_vitals.render import write_outputs  # noqa: E402

END = dt.date(2026, 7, 6)
DAYS = 120
RELEASES = [("v1.2", END - dt.timedelta(days=80)), ("v1.3", END - dt.timedelta(days=25))]
GAP = {(END - dt.timedelta(days=n)).isoformat() for n in range(40, 45)}  # missed runs


def build(out_dir):
    rng = random.Random(42)
    history = {}
    stars = 3
    star_dates = []
    downloads = {"v1.2": 0, "v1.3": 0}

    for offset in range(DAYS - 1, -1, -1):
        date = END - dt.timedelta(days=offset)
        day = date.isoformat()
        if day in GAP:
            continue

        boost = sum(
            8 * math.exp(-(date - rel_date).days / 6)
            for _, rel_date in RELEASES if date >= rel_date
        )
        weekly = 1.0 + 0.5 * math.sin(2 * math.pi * date.weekday() / 7)
        views = max(0, round((6 + boost) * weekly + rng.uniform(-2, 2)))
        clones = max(0, round(views * 0.25 + rng.uniform(-1, 1)))

        new_stars = rng.choices([0, 1, 2, 5], weights=[55, 30, 10, 5])[0]
        if boost > 4:
            new_stars += rng.randint(0, 3)
        stars += new_stars
        star_dates += [day] * new_stars

        for tag, rel_date in RELEASES:
            if date >= rel_date:
                downloads[tag] += max(0, round(boost * 1.5 + rng.uniform(0, 2)))

        history[day] = {
            "date": day,
            "views": {"count": views, "uniques": max(1, views // 2)},
            "clones": {"count": clones, "uniques": max(0, clones * 2 // 3)},
            "traffic_updated_at": f"{day}T03:17:00Z",
            "observed_at": f"{day}T03:17:00Z",
            "popularity": {"stars": stars, "forks": 2 + stars // 8,
                           "watchers": stars, "subscribers": 3 + stars // 10},
            "releases": [{"tag": tag, "downloads": n} for tag, n in downloads.items() if n],
            "activity": {
                "commits_30d": 10 + rng.randint(-3, 6),
                "prs_opened_30d": rng.randint(1, 6), "prs_merged_30d": rng.randint(0, 4),
                "issues_opened_30d": rng.randint(0, 5), "issues_closed_30d": rng.randint(0, 5),
                "contributors_total": 4 + stars // 15,
            },
        }
    merge_star_backfill(history, star_dates[:3])  # a little pre-history

    last = history[END.isoformat()]
    snapshot = {
        "schema_version": 1,
        "date": END.isoformat(),
        "collected_at": f"{END.isoformat()}T03:17:00Z",
        "repo": "biterik/fixture-demo",
        "popularity": last["popularity"],
        "traffic": {
            "views": {d: history[d]["views"] for d in sorted(history)[-14:]
                      if "views" in history[d]},
            "clones": {d: history[d]["clones"] for d in sorted(history)[-14:]
                       if "clones" in history[d]},
            "referrers": [
                {"referrer": "reddit.com", "count": 42, "uniques": 30},
                {"referrer": "Google", "count": 25, "uniques": 21},
                {"referrer": "news.ycombinator.com", "count": 19, "uniques": 17},
            ],
            "paths": [
                {"path": "/biterik/fixture-demo", "count": 80, "uniques": 44},
                {"path": "/biterik/fixture-demo/releases", "count": 22, "uniques": 15},
            ],
        },
        "releases": [
            {"tag": tag, "name": tag, "published_at": f"{rel_date.isoformat()}T10:00:00Z",
             "prerelease": False,
             "assets": [{"name": f"demo-{tag}.zip", "downloads": downloads[tag]}]}
            for tag, rel_date in reversed(RELEASES)
        ],
        "activity": last["activity"],
        "meta": {"fork": False, "archived": False},
        "errors": [{"section": "traffic",
                    "error": "example warning to exercise the warnings section"}],
    }

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_outputs(out, snapshot, history)
    (out / "history.ndjson").write_text(dump_history(history), encoding="utf-8")
    print(f"fixture dataset written to {out}")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "dashboard-fixture")
