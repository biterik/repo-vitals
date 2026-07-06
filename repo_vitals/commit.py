"""Commit stage: publish the run's outputs to the orphan vitals branch.

Concurrency strategy (ARCHITECTURE.md §7.2): each publish attempt starts
from a fresh shallow clone of the branch, re-merges the snapshot into
whatever history is on the remote, and pushes. If the push is rejected
(someone else pushed in between), the whole attempt is retried with a
jittered backoff — re-cloning is the rebase. Merging is idempotent, so
replaying the same snapshot onto newer remote state is always safe.

The first run auto-creates the branch as an orphan (§7.8) and can backfill
full star history via the injected `backfill_star_history` callable.
"""

from __future__ import annotations

import random
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from repo_vitals.merge import load_history, merge_snapshot, merge_star_backfill
from repo_vitals.render import write_outputs

GIT_USER = "github-actions[bot]"
GIT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"


class PublishError(Exception):
    """Publishing to the vitals branch failed (after retries)."""


def _git(args, cwd):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    )


def prepare_workdir(remote_url, branch, base_dir=None):
    """Fresh clone of the vitals branch; init an orphan if it doesn't exist yet.

    Returns (workdir, created) where created=True means first run.
    """
    workdir = Path(tempfile.mkdtemp(prefix="repo-vitals-", dir=base_dir))
    clone = subprocess.run(
        ["git", "clone", "--quiet", "--depth", "1", "--branch", branch,
         "--single-branch", remote_url, str(workdir)],
        capture_output=True, text=True,
    )
    if clone.returncode != 0:
        if "not found" not in clone.stderr.lower():
            shutil.rmtree(workdir, ignore_errors=True)
            raise PublishError(f"git clone failed: {clone.stderr.strip()[:300]}")
        # branch (or any commit) doesn't exist yet -> first run, orphan branch
        _git(["init", "--quiet", "-b", branch], cwd=workdir)
        _git(["remote", "add", "origin", remote_url], cwd=workdir)
        created = True
    else:
        created = False
    _git(["config", "user.name", GIT_USER], cwd=workdir)
    _git(["config", "user.email", GIT_EMAIL], cwd=workdir)
    return workdir, created


def publish_snapshot(
    snapshot,
    remote_url,
    branch="vitals",
    max_attempts=3,
    sleep=time.sleep,
    base_dir=None,
    backfill_star_history=None,
):
    """Merge `snapshot` into the remote vitals branch and push. Returns a status str."""
    last_error = "unknown"
    for attempt in range(1, max_attempts + 1):
        workdir, created = prepare_workdir(remote_url, branch, base_dir=base_dir)
        try:
            history = load_history(workdir / "history.ndjson")
            if not history and backfill_star_history is not None:
                try:
                    merge_star_backfill(history, backfill_star_history())
                except Exception as exc:  # noqa: BLE001 - backfill is a bonus, never fatal
                    snapshot["errors"].append({
                        "section": "star_backfill",
                        "error": f"{type(exc).__name__}: {exc}",
                    })
            merge_snapshot(history, snapshot)
            write_outputs(workdir, snapshot, history)

            _git(["add", "-A"], cwd=workdir)
            status = _git(["status", "--porcelain"], cwd=workdir)
            if not status.stdout.strip():
                return "no changes"
            _git(["commit", "--quiet", "-m", f"vitals: {snapshot['date']}"], cwd=workdir)
            try:
                _git(["push", "--quiet", "origin", branch], cwd=workdir)
                return "created branch" if created else "pushed"
            except subprocess.CalledProcessError as exc:
                last_error = (exc.stderr or str(exc)).strip()[:300]
                if attempt < max_attempts:
                    sleep(2**attempt + random.random())
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
    raise PublishError(
        f"push to {branch!r} failed after {max_attempts} attempts: {last_error}"
    )
