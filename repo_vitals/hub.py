# Author: Erik Bitzek <e.bitzek@mpi-susmat.de>
# Department of Materials Science, WW8-Materials Simulation,
# Friedrich-Alexander-Universität Erlangen-Nürnberg,
# Dr.-Mack-Straße 77, 90762 Fürth, Germany
"""Hub: aggregate many repos' published vitals into one site (§3.5).

The hub is strictly read-only: it fetches each tracked repo's VITALS.json
and history.ndjson from the public raw URLs — no permissions, no
coordination with the repo owners. It builds a static site directory:

  index.html       aggregate dashboard (fetches hub-data.json)
  hub-data.json    trimmed per-repo data for the dashboard
  REPORT.md        combined fleet report (the grant-report artifact)
  reports/         dated, repo/title-qualified copies of REPORT.md
  repos/<slug>/    a *mirrored copy* of each reporting repo's own interactive
                   dashboard (index.html + its VITALS.json/history.ndjson) —
                   ARCHITECTURE.md §3.4(b): "the hub renders every member
                   repo's dashboard — primary path, always works", because a
                   repo's own GitHub Pages slot is often already used by docs
                   and can't be relied on.

The watchdog lives here too: any repo whose VITALS.json is missing or older
than `stale_after_days` (default 3) is flagged loudly in every output —
that's how expired traffic PATs and GitHub's 60-day cron auto-disable get
noticed (§7.1, §7.6b).
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import requests

from repo_vitals.render import render_dashboard_asset, render_template, slugify

DEFAULT_STALE_DAYS = 3
SERIES_DAYS = 120  # per-repo history trimmed to this many trailing days


def parse_simple_yaml(text: str) -> dict:
    """Parse the deliberately tiny YAML subset used by hub-config.yml:
    top-level `key: value` scalars and `key:` followed by `- item` lists.
    Keeps the hub dependency-free (no pyyaml); anything fancier is an error.
    """
    data: dict = {}
    current_list = None
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        if stripped.startswith("- "):
            if current_list is None:
                raise ValueError(f"hub config line {lineno}: list item outside a list")
            data[current_list].append(stripped[2:].strip().strip("\"'"))
        elif not line[0].isspace() and ":" in line:
            key, _, value = line.partition(":")
            key, value = key.strip(), value.strip().strip("\"'")
            if value:
                data[key] = value
                current_list = None
            else:
                data[key] = []
                current_list = key
        else:
            raise ValueError(f"hub config line {lineno}: unsupported syntax: {raw!r}")
    return data


def load_hub_config(path: str | Path) -> dict:
    data = parse_simple_yaml(Path(path).read_text(encoding="utf-8"))
    repos = data.get("repos") or []
    if not repos:
        raise ValueError("hub config: 'repos:' list is required and must not be empty")
    return {
        "title": data.get("title", "repo-vitals hub"),
        "branch": data.get("branch", "vitals"),
        "stale_after_days": int(data.get("stale_after_days", DEFAULT_STALE_DAYS)),
        # Optional: this hub site's own public URL (e.g. its GitHub Pages
        # address), used to build fully-qualified per-repo dashboard links in
        # REPORT.md so they still work when that file is read raw or emailed
        # standalone. Without it, dashboard links are root-relative — correct
        # whenever the site is browsed as a whole (Pages, hub-data.json),
        # which is the common case.
        "site_url": str(data.get("site_url", "")).rstrip("/"),
        "repos": repos,
    }


def fetch_repo_status(session, repo, branch="vitals", stale_after_days=DEFAULT_STALE_DAYS,
                      now=None):
    """Fetch one repo's published vitals and classify it: ok / stale / missing / error."""
    now = now or dt.datetime.now(dt.UTC)
    base = f"https://raw.githubusercontent.com/{repo}/{branch}"
    entry = {
        "repo": repo,
        "status": "error",
        "detail": "",
        "days_since_update": None,
        "collected_at": None,
        "stars": None, "views_30d": None, "clones_30d": None,
        "downloads_total": None, "health_score": None,
        "report_url": f"{base}/REPORT.md",
        "dashboard_url": None,  # filled in once build_hub() mirrors this repo's dashboard
        "series": None,
        # Raw payloads, stashed only long enough for build_hub() to mirror
        # them into repos/<slug>/ — stripped before entries are ever
        # serialized (hub-data.json, REPORT.md).
        "_vitals_text": None,
        "_history_text": None,
    }
    try:
        resp = session.get(f"{base}/VITALS.json", timeout=30)
    except requests.RequestException as exc:
        entry["detail"] = f"fetch failed: {type(exc).__name__}"
        return entry
    if resp.status_code == 404:
        entry["status"] = "missing"
        entry["detail"] = "no vitals branch — repo-vitals not installed (or never ran)"
        return entry
    if resp.status_code != 200:
        entry["detail"] = f"VITALS.json -> HTTP {resp.status_code}"
        return entry
    try:
        vitals = resp.json()
    except ValueError:
        entry["detail"] = "VITALS.json is not valid JSON"
        return entry

    derived = vitals.get("derived") or {}
    collected_at = str(vitals.get("collected_at", ""))
    entry.update({
        "collected_at": collected_at or None,
        "stars": derived.get("stars_now"),
        "views_30d": derived.get("views_last_30d"),
        "clones_30d": derived.get("clones_last_30d"),
        "downloads_total": derived.get("downloads_total"),
        "health_score": (derived.get("health") or {}).get("score"),
    })
    try:
        age = (now.date() - dt.date.fromisoformat(collected_at[:10])).days
    except ValueError:
        entry["detail"] = f"unparseable collected_at: {collected_at!r}"
        return entry
    entry["days_since_update"] = age
    if age > stale_after_days:
        entry["status"] = "stale"
        entry["detail"] = (f"last update {age} days ago — check the repo's Actions "
                           "(disabled cron? expired traffic PAT?)")
    else:
        entry["status"] = "ok"

    entry["_vitals_text"] = resp.text
    entry["series"], entry["_history_text"] = _fetch_series(session, base, now)
    return entry


def _fetch_series(session, base, now):
    """Trimmed per-day series for the hub's own charts, plus the raw
    history.ndjson text (for mirroring the repo's own dashboard). Both are
    None on any failure — non-fatal, the fleet report/dashboard just show
    less."""
    try:
        resp = session.get(f"{base}/history.ndjson", timeout=30)
        if resp.status_code != 200:
            return None, None
        cutoff = (now.date() - dt.timedelta(days=SERIES_DAYS)).isoformat()
        views, stars = [], []
        for line in resp.text.splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            day = rec.get("date", "")
            if day < cutoff:
                continue
            if "views" in rec:
                views.append([day, rec["views"]["count"]])
            pop = rec.get("popularity")
            if pop and pop.get("stars") is not None:
                stars.append([day, pop["stars"]])
            elif rec.get("stars_cumulative") is not None:
                stars.append([day, rec["stars_cumulative"]])
        return {"views": views, "stars": stars}, resp.text
    except (requests.RequestException, ValueError):
        return None, None


def build_hub(config: dict, out_dir: str | Path, session=None, now=None) -> dict:
    """Fetch all tracked repos, write the hub site. Returns the summary dict."""
    session = session or requests.Session()
    now = now or dt.datetime.now(dt.UTC)
    site_url = config.get("site_url", "")

    entries = [
        fetch_repo_status(session, repo, branch=config["branch"],
                          stale_after_days=config["stale_after_days"], now=now)
        for repo in config["repos"]
    ]

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Mirror each reporting repo's own dashboard under repos/<slug>/ — see
    # the module docstring and ARCHITECTURE.md §3.4(b). This is the primary
    # way to *view a visualization* for a tracked repo: it doesn't depend on
    # that repo having GitHub Pages free for its own vitals branch.
    dashboard_asset = None
    for e in entries:
        vitals_text = e.pop("_vitals_text", None)
        history_text = e.pop("_history_text", None)
        if e["status"] in ("ok", "stale") and vitals_text and history_text is not None:
            slug = slugify(e["repo"])
            repo_dir = out / "repos" / slug
            repo_dir.mkdir(parents=True, exist_ok=True)
            (repo_dir / "VITALS.json").write_text(vitals_text, encoding="utf-8")
            (repo_dir / "history.ndjson").write_text(history_text, encoding="utf-8")
            if dashboard_asset is None:
                dashboard_asset = render_dashboard_asset("index.html")
            (repo_dir / "index.html").write_text(dashboard_asset, encoding="utf-8")
            relative_url = f"repos/{slug}/index.html"
            e["dashboard_url"] = f"{site_url}/{relative_url}" if site_url else relative_url

    flagged = [e for e in entries if e["status"] != "ok"]

    def total(key):
        values = [e[key] for e in entries if e[key] is not None]
        return sum(values) if values else None

    summary = {
        "title": config["title"],
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stale_after_days": config["stale_after_days"],
        "repos": entries,
        "flagged": [e["repo"] for e in flagged],
        "totals": {
            "repos": len(entries),
            "ok": len(entries) - len(flagged),
            "stars": total("stars"),
            "views_30d": total("views_30d"),
            "clones_30d": total("clones_30d"),
            "downloads_total": total("downloads_total"),
        },
    }

    (out / "hub-data.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report_text = render_template("hub-report.md.j2", **summary)
    (out / "REPORT.md").write_text(report_text, encoding="utf-8")

    # Dated, title-qualified archive copy — see render.write_outputs() for
    # the same convention on a single repo's REPORT.md.
    reports_dir = out / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    archive_name = f"{slugify(config['title'])}-{now:%Y-%m-%d}.md"
    (reports_dir / archive_name).write_text(report_text, encoding="utf-8")

    (out / "index.html").write_text(render_dashboard_asset("hub.html"), encoding="utf-8")
    return summary
