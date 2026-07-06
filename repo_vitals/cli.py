"""Command-line entry point: python -m repo_vitals run [--dry-run] ..."""

from __future__ import annotations

import argparse
import os
import sys

from repo_vitals.collect import all_sections_failed, collect_snapshot
from repo_vitals.merge import load_history, merge_snapshot
from repo_vitals.render import write_outputs
from repo_vitals.schemas import assert_valid_snapshot


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="repo_vitals",
        description="Collect long-term GitHub repository statistics.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="collect + merge + render (the daily pipeline)")
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

    args = parser.parse_args(argv)
    return _run(args)


def _run(args) -> int:
    if not args.repo:
        print("error: --repo is required (or set $GITHUB_REPOSITORY)", file=sys.stderr)
        return 2
    if not args.dry_run:
        print(
            "error: the commit stage is not implemented yet (milestone M2); "
            "use --dry-run to write to a local directory",
            file=sys.stderr,
        )
        return 2

    print(f"collecting snapshot for {args.repo} ...", file=sys.stderr)
    snapshot = collect_snapshot(
        args.repo, token=args.token, traffic_token=args.traffic_token
    )
    assert_valid_snapshot(snapshot)

    for err in snapshot["errors"]:
        print(f"warning: section {err['section']!r}: {err['error']}", file=sys.stderr)

    history = load_history(os.path.join(args.output_dir, "history.ndjson"))
    merge_snapshot(history, snapshot)
    paths = write_outputs(args.output_dir, snapshot, history)

    for path in paths:
        print(f"wrote {path}")

    if all_sections_failed(snapshot):
        print("error: every section failed to collect", file=sys.stderr)
        return 1
    return 0
