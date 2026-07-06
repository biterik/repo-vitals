"""Snapshot schema version and lightweight validation.

The authoritative, machine-readable schema lives in
schema/vitals.schema.json (JSON Schema, versioned; validated in the test
suite with the `jsonschema` package). The runtime check here is deliberately
dependency-free: it catches structural mistakes before anything is written,
without pulling a validator into the action's install footprint.

`schema_version` bumps only on breaking changes; readers must accept all
past versions (migrate-on-read, never rewrite history).
"""

from __future__ import annotations

import re

SCHEMA_VERSION = 1

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_REPO_RE = re.compile(r"^[^/\s]+/[^/\s]+$")

_SECTIONS = ("popularity", "traffic", "releases", "activity", "meta")


def validate_snapshot(snapshot: dict) -> list[str]:
    """Return a list of structural problems (empty list = valid)."""
    problems = []

    def check(cond, msg):
        if not cond:
            problems.append(msg)

    check(isinstance(snapshot, dict), "snapshot is not a dict")
    if not isinstance(snapshot, dict):
        return problems

    check(snapshot.get("schema_version") == SCHEMA_VERSION,
          f"schema_version != {SCHEMA_VERSION}")
    check(_DATE_RE.match(str(snapshot.get("date", ""))) is not None,
          "date is not YYYY-MM-DD")
    check(_DATETIME_RE.match(str(snapshot.get("collected_at", ""))) is not None,
          "collected_at is not an ISO-8601 UTC timestamp (…Z)")
    check(_REPO_RE.match(str(snapshot.get("repo", ""))) is not None,
          "repo is not owner/name")
    check(isinstance(snapshot.get("errors"), list), "errors is not a list")

    for name in _SECTIONS:
        check(name in snapshot, f"missing section key: {name}")

    traffic = snapshot.get("traffic")
    if traffic is not None:
        check(isinstance(traffic, dict), "traffic is not a dict or null")
        if isinstance(traffic, dict):
            for kind in ("views", "clones"):
                per_day = traffic.get(kind)
                check(isinstance(per_day, dict), f"traffic.{kind} is not a dict")
                if isinstance(per_day, dict):
                    for day, counts in per_day.items():
                        check(_DATE_RE.match(day) is not None,
                              f"traffic.{kind} key {day!r} is not YYYY-MM-DD")
                        check(
                            isinstance(counts, dict)
                            and "count" in counts and "uniques" in counts,
                            f"traffic.{kind}[{day!r}] lacks count/uniques",
                        )

    return problems


def assert_valid_snapshot(snapshot: dict) -> None:
    problems = validate_snapshot(snapshot)
    if problems:
        raise ValueError("invalid snapshot: " + "; ".join(problems))
