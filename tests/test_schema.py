"""Snapshots (and VITALS.json) must validate against the published JSON Schema."""

import json
from pathlib import Path

import jsonschema
from conftest import make_snapshot, window

from repo_vitals.merge import merge_snapshot
from repo_vitals.render import build_vitals

SCHEMA = json.loads(
    (Path(__file__).parent.parent / "schema" / "vitals.schema.json").read_text()
)


def validate(instance):
    jsonschema.validate(instance=instance, schema=SCHEMA)


def test_full_snapshot_validates():
    snap = make_snapshot(
        "2026-07-06",
        views=window("2026-07-06"),
        clones=window("2026-07-06", base=1),
        referrers=[{"referrer": "reddit.com", "count": 31, "uniques": 22}],
        paths=[{"path": "/biterik/example", "count": 50, "uniques": 31}],
        releases=[{"tag": "v1.0", "name": "v1.0", "published_at": "2026-01-01T00:00:00Z",
                   "prerelease": False,
                   "assets": [{"name": "a.zip", "downloads": 100}]}],
        activity={"commits_30d": 14, "prs_opened_30d": 3, "prs_merged_30d": 2,
                  "issues_opened_30d": 5, "issues_closed_30d": 4,
                  "contributors_total": 7},
    )
    validate(snap)


def test_snapshot_with_failed_sections_validates():
    snap = make_snapshot("2026-07-06", traffic_present=False)
    snap["releases"] = None
    snap["errors"] = [{"section": "traffic", "error": "no token"},
                      {"section": "releases", "error": "HTTP 500"}]
    validate(snap)


def test_vitals_json_with_derived_validates():
    snap = make_snapshot("2026-07-06", views=window("2026-07-06"))
    history = merge_snapshot({}, snap)
    vitals = build_vitals(snap, history)
    assert vitals["derived"]["views_last_7d"] is not None
    validate(vitals)


def test_bad_snapshot_fails_validation():
    snap = make_snapshot("2026-07-06")
    snap["traffic"] = {"views": {"not-a-date": {"count": 1, "uniques": 1}},
                       "clones": {}, "referrers": [], "paths": []}
    try:
        validate(snap)
    except jsonschema.ValidationError:
        return
    raise AssertionError("schema accepted an invalid per-day date key")
