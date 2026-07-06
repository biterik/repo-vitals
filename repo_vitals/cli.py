# Author: Erik Bitzek <e.bitzek@mpi-susmat.de>
# Department of Materials Science, WW8-Materials Simulation,
# Friedrich-Alexander-Universität Erlangen-Nürnberg,
# Dr.-Mack-Straße 77, 90762 Fürth, Germany
"""Command-line entry point: python -m repo_vitals run [--dry-run] ..."""

from __future__ import annotations

import argparse
import os
import sys

from repo_vitals.collect import (
    GitHubClient,
    all_sections_failed,
    collect_snapshot,
    collect_star_history,
    re_enable_workflow,
)
from repo_vitals.commit import publish_snapshot
from repo_vitals.merge import load_history, merge_snapshot
from repo_vitals.render import write_outputs
from repo_vitals.schemas import assert_valid_snapshot


def _env_flag(name):
    return os.environ.get(name, "").lower() in ("1", "true", "yes")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="repo_vitals",
        description="Collect long-term GitHub repository statistics.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="collect + merge + render + commit (the daily pipeline)")
    run.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY"),
        help="owner/name (default: $GITHUB_REPOSITORY)",
    )
    run.add_argument(
        "--dry-run",
        action="store_true",
        help="write outputs to --output-dir instead of committing to the vitals branch",
    )
    run.add_argument(
        "--output-dir",
        default="vitals-out",
        help="directory for --dry-run outputs (default: ./vitals-out)",
    )
    run.add_argument(
        "--token",
        default=os.environ.get("GITHUB_TOKEN"),
        help="API token for everything except traffic (default: $GITHUB_TOKEN)",
    )
    run.add_argument(
        "--traffic-token",
        default=os.environ.get("REPO_VITALS_TOKEN") or None,
        help="PAT for the traffic endpoints; omit to skip traffic gracefully "
             "(default: $REPO_VITALS_TOKEN)",
    )
    run.add_argument(
        "--branch",
        default=os.environ.get("REPO_VITALS_BRANCH") or "vitals",
        help="data branch to push to (default: $REPO_VITALS_BRANCH or 'vitals')",
    )
    run.add_argument(
        "--allow-fork",
        action="store_true",
        default=_env_flag("REPO_VITALS_ALLOW_FORK"),
        help="run even if the repository is a fork (default: forks are a no-op)",
    )

    render = sub.add_parser(
        "render",
        help="rebuild VITALS.json/REPORT.md/badges from existing data alone (no API calls)",
    )
    render.add_argument(
        "--data-dir",
        required=True,
        help="directory holding history.ndjson and snapshots/ (e.g. a vitals checkout)",
    )
    render.add_argument(
        "--branch",
        default=os.environ.get("REPO_VITALS_BRANCH") or "vitals",
        help="data branch name, used for badge URLs (default: 'vitals')",
    )

    args = parser.parse_args(argv)
    if args.command == "render":
        return _render(args)
    return _run(args)


def _render(args) -> int:
    """§7.9 determinism: rendering is a pure function of history + templates."""
    import glob
    import json

    snapshot_files = sorted(glob.glob(os.path.join(args.data_dir, "snapshots", "*.json")))
    if not snapshot_files:
        print(f"error: no snapshots/*.json under {args.data_dir}", file=sys.stderr)
        return 2
    with open(snapshot_files[-1], encoding="utf-8") as fh:
        snapshot = json.load(fh)
    assert_valid_snapshot(snapshot)
    history = load_history(os.path.join(args.data_dir, "history.ndjson"))
    for path in write_outputs(args.data_dir, snapshot, history, branch=args.branch):
        print(f"wrote {path}")
    return 0


def _run(args) -> int:
    if not args.repo:
        print("error: --repo is required (or set $GITHUB_REPOSITORY)", file=sys.stderr)
        return 2
    if not args.dry_run and not args.token:
        print("error: pushing to the vitals branch requires --token (or $GITHUB_TOKEN)",
              file=sys.stderr)
        return 2

    client = GitHubClient(token=args.token)
    print(f"collecting snapshot for {args.repo} ...", file=sys.stderr)
    snapshot = collect_snapshot(
        args.repo, traffic_token=args.traffic_token, client=client
    )
    assert_valid_snapshot(snapshot)

    for err in snapshot["errors"]:
        print(f"warning: section {err['section']!r}: {err['error']}", file=sys.stderr)

    if (snapshot.get("meta") or {}).get("fork") and not args.allow_fork:
        print(f"{args.repo} is a fork; skipping (pass --allow-fork to override)",
              file=sys.stderr)
        return 0

    if args.dry_run:
        history = load_history(os.path.join(args.output_dir, "history.ndjson"))
        merge_snapshot(history, snapshot)
        for path in write_outputs(args.output_dir, snapshot, history, branch=args.branch):
            print(f"wrote {path}")
    else:
        remote_url = f"https://x-access-token:{args.token}@github.com/{args.repo}.git"
        result = publish_snapshot(
            snapshot,
            remote_url,
            branch=args.branch,
            backfill_star_history=lambda: collect_star_history(client, args.repo),
        )
        print(f"publish to {args.branch!r}: {result}", file=sys.stderr)
        # keep our own cron alive (§7.1); needs `actions: write`, best-effort
        if re_enable_workflow(client, args.repo):
            print("workflow re-enabled", file=sys.stderr)

    if all_sections_failed(snapshot):
        print("error: every section failed to collect", file=sys.stderr)
        return 1
    return 0
