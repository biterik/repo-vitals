#!/usr/bin/env bash
# Fleet deployment of repo-vitals (ARCHITECTURE.md §9).
#
# For every target repo (default: all of the owner's non-fork, non-archived
# repos), this script:
#   1. skips it if .github/workflows/repo-vitals.yml already exists,
#   2. sets the REPO_VITALS_TOKEN secret (traffic PAT),
#   3. creates branch add-repo-vitals with the workflow file (API only, no clone),
#   4. opens a PR titled "Add repo-vitals daily stats".
#
# PRs, not direct pushes: reviewable, skippable, works with branch protection.
# Consumers pin @v1, so future upgrades need no redeployment — this is
# one-time per repo. Runs on a Mac with `gh` authenticated; never touches HPC.
#
# Token resolution order: --token flag > $REPO_VITALS_TOKEN > macOS keychain
# via the `repo-vitals-token` zsh function (absent on e.g. the travel laptop —
# then pass the token explicitly or use --no-secret).
#
# Requires: bash + the GitHub CLI (`gh`, authenticated via `gh auth login`).
# Tested on macOS and Linux; on Windows there is no native cmd.exe/PowerShell
# support — run it under WSL (recommended, identical to the Linux case) or
# Git Bash.
#
# Usage:
#   deploy/rollout.sh [--owner biterik] [--repos a,b,c] [--exclude x,y]
#                     [--merge] [--dry-run] [--token PAT] [--no-secret]

set -euo pipefail

OWNER="biterik"
REPOS=""
EXCLUDE=""
MERGE=0
DRY_RUN=0
NO_SECRET=0
TOKEN="${REPO_VITALS_TOKEN:-}"
BRANCH="add-repo-vitals"
WORKFLOW_PATH=".github/workflows/repo-vitals.yml"
TEMPLATE="$(dirname "$0")/workflow-template.yml"

usage() { sed -n '2,26p' "$0"; exit "${1:-0}"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --owner)     OWNER="$2"; shift 2 ;;
    --repos)     REPOS="$2"; shift 2 ;;
    --exclude)   EXCLUDE="$2"; shift 2 ;;
    --merge)     MERGE=1; shift ;;
    --dry-run)   DRY_RUN=1; shift ;;
    --token)     TOKEN="$2"; shift 2 ;;
    --no-secret) NO_SECRET=1; shift ;;
    -h|--help)   usage ;;
    *) echo "unknown flag: $1" >&2; usage 1 ;;
  esac
done

[[ -f "$TEMPLATE" ]] || { echo "error: $TEMPLATE not found" >&2; exit 1; }

# --- preflight ---------------------------------------------------------------
command -v gh >/dev/null 2>&1 || {
  cat >&2 <<'EOF'
error: the GitHub CLI ('gh') is required but was not found on $PATH.
  macOS:   brew install gh
  Linux:   https://github.com/cli/cli#installation
  Windows: no native support — run this script under WSL (recommended) or
           Git Bash, then install gh there.
EOF
  exit 1
}
gh auth status >/dev/null 2>&1 || {
  echo "error: 'gh' is installed but not authenticated — run 'gh auth login' first." >&2
  exit 1
}

# --- traffic PAT (keychain fallback) ---------------------------------------
if [[ $NO_SECRET -eq 0 && $DRY_RUN -eq 0 && -z "$TOKEN" ]]; then
  echo "no token via --token/\$REPO_VITALS_TOKEN — trying macOS keychain (repo-vitals-token) ..."
  TOKEN="$(zsh -ic 'repo-vitals-token' 2>/dev/null | tail -1 || true)"
  if [[ -z "$TOKEN" ]]; then
    cat >&2 <<'EOF'
error: could not obtain the traffic PAT.
  Provide it via --token / $REPO_VITALS_TOKEN, or define the zsh function
  repo-vitals-token() (keychain lookup). To roll out without setting the
  secret (traffic collection will be skipped gracefully), use --no-secret.
EOF
    exit 1
  fi
  echo "  ... got token from keychain (length ${#TOKEN})"
fi

# --- target list -------------------------------------------------------------
if [[ -n "$REPOS" ]]; then
  TARGETS=$(tr ',' '\n' <<<"$REPOS" | sed "s|^|$OWNER/|; s|^$OWNER/$OWNER/|$OWNER/|")
else
  TARGETS=$(gh repo list "$OWNER" --no-archived --source --limit 300 \
              --json nameWithOwner -q '.[].nameWithOwner')
fi

is_excluded() {
  local name="${1#*/}"
  [[ ",$EXCLUDE," == *",$name,"* || ",$EXCLUDE," == *",$1,"* ]]
}

pr_body() {
  local repo="$1"
  cat <<EOF
This PR adds [repo-vitals](https://github.com/biterik/repo-vitals): a daily
GitHub Action that archives this repo's traffic, stars, releases, and
activity to an orphan \`vitals\` branch — GitHub deletes traffic data after
14 days, this keeps it forever.

After merging, data appears daily (or run the workflow manually via
*Actions → repo-vitals → Run workflow*):

- \`https://raw.githubusercontent.com/$repo/vitals/REPORT.md\` — daily report
- \`https://raw.githubusercontent.com/$repo/vitals/VITALS.json\` — machine-readable
- \`index.html\` on the \`vitals\` branch — interactive dashboard

The \`REPO_VITALS_TOKEN\` secret (traffic PAT) has already been set on this
repository. No other setup is needed; the action is pinned to \`@v1\` and
receives fixes automatically.
EOF
}

deploy_one() {
  local repo="$1" default_branch base_sha
  if [[ $NO_SECRET -eq 0 ]]; then
    gh secret set REPO_VITALS_TOKEN --repo "$repo" --body "$TOKEN" || return 1
  fi
  default_branch=$(gh api "repos/$repo" -q .default_branch) || return 1
  base_sha=$(gh api "repos/$repo/git/ref/heads/$default_branch" -q .object.sha) || return 1
  gh api -X POST "repos/$repo/git/refs" \
    -f ref="refs/heads/$BRANCH" -f sha="$base_sha" --silent || return 1
  gh api -X PUT "repos/$repo/contents/$WORKFLOW_PATH" \
    -f message="Add repo-vitals daily stats" \
    -f content="$(base64 <"$TEMPLATE" | tr -d '\n')" \
    -f branch="$BRANCH" --silent || return 1
  gh pr create --repo "$repo" --head "$BRANCH" --base "$default_branch" \
    --title "Add repo-vitals daily stats" \
    --body "$(pr_body "$repo")" || return 1
}

# --- rollout -----------------------------------------------------------------
CREATED=0 SKIPPED=0 FAILED=0
for repo in $TARGETS; do
  if [[ "$repo" == "$OWNER/repo-vitals" ]]; then
    echo "skip  $repo (self — uses self-vitals.yml)"; ((SKIPPED+=1)); continue
  fi
  if is_excluded "$repo"; then
    echo "skip  $repo (excluded)"; ((SKIPPED+=1)); continue
  fi
  if gh api "repos/$repo/contents/$WORKFLOW_PATH" --silent 2>/dev/null; then
    echo "skip  $repo (workflow already present)"; ((SKIPPED+=1)); continue
  fi
  if gh api "repos/$repo/branches/$BRANCH" --silent 2>/dev/null; then
    echo "skip  $repo (branch $BRANCH already exists — PR pending?)"; ((SKIPPED+=1)); continue
  fi
  if [[ $DRY_RUN -eq 1 ]]; then
    echo "plan  $repo: set secret, create $BRANCH, open PR"; continue
  fi

  echo "-> $repo"
  if ! deploy_one "$repo"; then
    echo "FAIL  $repo" >&2; ((FAILED+=1)); continue
  fi
  if [[ $MERGE -eq 1 ]]; then
    gh pr merge --repo "$repo" "$BRANCH" --squash --auto ||
      echo "note: auto-merge not possible on $repo — merge the PR manually" >&2
  fi
  ((CREATED+=1))
done

echo
echo "done: $CREATED PR(s) created, $SKIPPED skipped, $FAILED failed"
[[ $FAILED -eq 0 ]]
