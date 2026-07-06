# Author: Erik Bitzek <e.bitzek@mpi-susmat.de>
# Department of Materials Science, WW8-Materials Simulation,
# Friedrich-Alexander-Universität Erlangen-Nürnberg,
# Dr.-Mack-Straße 77, 90762 Fürth, Germany
"""Commit stage against a local bare repository (no network, real git)."""

import json
import subprocess

import pytest
from conftest import make_snapshot, window

from repo_vitals.commit import PublishError, publish_snapshot

BRANCH = "vitals"


def git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout


@pytest.fixture
def origin(tmp_path):
    bare = tmp_path / "origin.git"
    bare.mkdir()
    git(["init", "--quiet", "--bare"], cwd=bare)
    return bare


def clone_vitals(origin, tmp_path, name="check"):
    dest = tmp_path / name
    git(["clone", "--quiet", "--branch", BRANCH, str(origin), str(dest)],
        cwd=origin.parent)
    return dest


def read_history(clone_dir):
    lines = (clone_dir / "history.ndjson").read_text().strip().splitlines()
    return {rec["date"]: rec for rec in map(json.loads, lines)}


def test_first_run_creates_orphan_branch_with_all_files(origin, tmp_path):
    snap = make_snapshot("2026-07-06", views={"2026-07-05": 5})
    result = publish_snapshot(snap, str(origin), branch=BRANCH, base_dir=tmp_path)
    assert result == "created branch"

    checkout = clone_vitals(origin, tmp_path)
    for name in ("VITALS.json", "REPORT.md", "history.ndjson",
                 "snapshots/2026-07-06.json"):
        assert (checkout / name).exists(), name
    # orphan: exactly one commit, no parents
    log = git(["log", "--format=%H %P", BRANCH], cwd=checkout).strip().splitlines()
    assert len(log) == 1 and log[0].split()[1:] == []
    # only the vitals branch exists on the remote
    branches = git(["branch", "-r"], cwd=checkout)
    assert "origin/main" not in branches


def test_second_run_merges_with_remote_history(origin, tmp_path):
    publish_snapshot(make_snapshot("2026-07-06", views={"2026-07-05": 5}),
                     str(origin), branch=BRANCH, base_dir=tmp_path)
    publish_snapshot(make_snapshot("2026-07-07", views={"2026-07-05": 8,
                                                        "2026-07-06": 3}),
                     str(origin), branch=BRANCH, base_dir=tmp_path)

    history = read_history(clone_vitals(origin, tmp_path))
    # newer run retro-adjusted 07-05; both snapshot files kept as audit trail
    assert history["2026-07-05"]["views"]["count"] == 8
    assert history["2026-07-06"]["views"]["count"] == 3
    checkout = clone_vitals(origin, tmp_path, "check2")
    assert (checkout / "snapshots/2026-07-06.json").exists()
    assert (checkout / "snapshots/2026-07-07.json").exists()


def test_identical_rerun_pushes_nothing(origin, tmp_path):
    snap = make_snapshot("2026-07-06", views={"2026-07-05": 5})
    publish_snapshot(snap, str(origin), branch=BRANCH, base_dir=tmp_path)
    assert publish_snapshot(snap, str(origin), branch=BRANCH,
                            base_dir=tmp_path) == "no changes"

    checkout = clone_vitals(origin, tmp_path)
    assert len(git(["log", "--format=%H", BRANCH], cwd=checkout).split()) == 1


def test_rejected_push_retries_from_fresh_clone(origin, tmp_path):
    """§7.2: simulate a concurrent push landing between our clone and our push."""
    hook = origin / "hooks" / "pre-receive"
    hook.write_text(
        "#!/bin/sh\n"
        'if [ -f "$GIT_DIR/reject-once" ]; then\n'
        '  rm "$GIT_DIR/reject-once"\n'
        '  echo "simulated concurrent push" >&2\n'
        "  exit 1\n"
        "fi\n"
        "exit 0\n"
    )
    hook.chmod(0o755)
    (origin / "reject-once").touch()

    sleeps = []
    result = publish_snapshot(
        make_snapshot("2026-07-06", views={"2026-07-05": 5}),
        str(origin), branch=BRANCH, base_dir=tmp_path, sleep=sleeps.append,
    )
    assert result == "created branch"
    assert len(sleeps) == 1  # one rejection, one backoff, then success


def test_push_gives_up_after_max_attempts(origin, tmp_path):
    hook = origin / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho always-reject >&2\nexit 1\n")
    hook.chmod(0o755)

    with pytest.raises(PublishError, match="after 2 attempts"):
        publish_snapshot(
            make_snapshot("2026-07-06", views={"2026-07-05": 5}),
            str(origin), branch=BRANCH, base_dir=tmp_path,
            max_attempts=2, sleep=lambda s: None,
        )


def test_first_run_backfills_star_history(origin, tmp_path):
    publish_snapshot(
        make_snapshot("2026-07-06", views=window("2026-07-06")),
        str(origin), branch=BRANCH, base_dir=tmp_path,
        backfill_star_history=lambda: ["2026-01-05", "2026-01-05", "2026-02-01"],
    )
    history = read_history(clone_vitals(origin, tmp_path))
    assert history["2026-01-05"]["stars_cumulative"] == 2
    assert history["2026-02-01"]["stars_cumulative"] == 3


def test_backfill_runs_only_on_first_run(origin, tmp_path):
    calls = []

    def backfill():
        calls.append(1)
        return ["2026-01-05"]

    publish_snapshot(make_snapshot("2026-07-06", views={"2026-07-05": 5}),
                     str(origin), branch=BRANCH, base_dir=tmp_path,
                     backfill_star_history=backfill)
    publish_snapshot(make_snapshot("2026-07-07", views={"2026-07-06": 2}),
                     str(origin), branch=BRANCH, base_dir=tmp_path,
                     backfill_star_history=backfill)
    assert len(calls) == 1


def test_backfill_failure_is_not_fatal(origin, tmp_path):
    def broken():
        raise RuntimeError("GraphQL down")

    snap = make_snapshot("2026-07-06", views={"2026-07-05": 5})
    result = publish_snapshot(snap, str(origin), branch=BRANCH, base_dir=tmp_path,
                              backfill_star_history=broken)
    assert result == "created branch"
    assert any(e["section"] == "star_backfill" for e in snap["errors"])
