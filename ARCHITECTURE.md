# repo-vitals — Architecture Specification

**Status:** design finalized — handoff to Claude Code (implementation + repo creation)
**Owner:** Erik Bitzek (`biterik`)
**Date:** 2026-07-06
**Name check:** no existing GitHub project named `repo-vitals` (verified 2026-07-06; re-verify at repo creation).

---

## 1. Problem & goals

GitHub throws away traffic data after 14 days and offers no long-term view of a
project's life. Existing tools (github-repo-stats, Repository Traffic Action,
github-repo-traffic-stats) archive traffic but don't answer maintainer
questions: *Is the project growing? Which release worked? What caused that
spike? Is it healthy?*

Concrete driving requirement (NFDI-MatWerk): each repo must expose a **daily
updated, stable-URL report file** that consortium members can download directly
from the GitHub project — no server, no auth, no manual step.

Goals, in priority order:

1. **Zero-config adoption**: one ~15-line workflow file per repo, nothing else.
2. **Daily machine-readable snapshot** (`VITALS.json`) + human-readable
   `REPORT.md` at stable raw URLs.
3. **Long-term history** stored in git, future-proof, regenerable.
4. **Interactive dashboard** (static HTML, GitHub Pages) per repo.
5. **Hub**: one aggregate dashboard across all of a user's instrumented repos.
6. Generally useful to any open-source maintainer, not NFDI-specific.

Non-goals (v1): servers, databases, external hosting, analytics beyond the
GitHub/Zenodo APIs, write access to anything except the repo's own vitals data.

## 2. Topology

Per-repo action + optional central hub.

```
┌ each instrumented repo ─────────────────────────────┐
│ .github/workflows/repo-vitals.yml  (15 lines)       │
│        │ cron daily, uses: biterik/repo-vitals@v1   │
│        ▼                                            │
│ branch "vitals" (orphan):                           │
│   snapshots/2026-07-06.json   ← daily raw snapshot  │
│   history.ndjson              ← compacted history   │
│   VITALS.json                 ← latest, stable URL  │
│   REPORT.md                   ← human summary       │
│   index.html                  ← self-contained dash │
└─────────────────────────────────────────────────────┘
                    ▲ read-only (raw URLs)
┌ hub repo (repo-vitals-hub) ─────────────────────────┐
│ daily cron: fetch VITALS.json from N repos          │
│ → aggregate dashboard (GitHub Pages)                │
│ → cross-repo REPORT.md (grant-report ready)         │
└─────────────────────────────────────────────────────┘
```

Key decision — **orphan `vitals` branch, not `main`**: daily bot commits would
pollute `main`'s history and trigger CI/notifications. An orphan branch keeps
the default branch pristine while still giving stable raw URLs:

```
https://raw.githubusercontent.com/<owner>/<repo>/vitals/VITALS.json
https://raw.githubusercontent.com/<owner>/<repo>/vitals/REPORT.md
```

These are the URLs NFDI-MatWerk gets. Optional config flag
`mirror_to_default_branch: true` for repos that want `VITALS.json` visible on
`main` too.

## 3. Components

### 3.1 The action (`biterik/repo-vitals`, used as `@v1`)

**Composite action** wrapping a small Python package (`repo_vitals/`).
Rationale: Erik's ecosystem and likely contributors are Python; composite +
`actions/setup-python` + pinned deps is transparent and hackable. Tradeoff
noted: a bundled Node action would shave ~20 s setup; not worth the opacity.

Dependencies: `requests`, `jinja2` only. Pin exact versions. No pandas — keep
install < 10 s.

Pipeline (single entry point `python -m repo_vitals run`):

1. **collect** — call GitHub REST/GraphQL, produce today's snapshot dict.
2. **merge** — dedupe/merge with existing history (see §5 traffic-window merge).
3. **render** — write `VITALS.json`, `REPORT.md`, `index.html`.
4. **commit** — commit + push to `vitals` branch (with retry, see §7).

Each stage independently testable; `--dry-run` writes to a local dir.

### 3.2 Consumer workflow (what every repo adds)

```yaml
# .github/workflows/repo-vitals.yml
name: repo-vitals
on:
  schedule:
    - cron: "17 3 * * *"   # daily, off-peak minute to avoid cron congestion
  workflow_dispatch:        # manual runs / backfill
permissions:
  contents: write           # push to vitals branch; also grants traffic read
jobs:
  vitals:
    runs-on: ubuntu-latest
    steps:
      - uses: biterik/repo-vitals@v1
        with:
          traffic-token: ${{ secrets.REPO_VITALS_TOKEN }}  # PAT, see below
        # config-file: .github/repo-vitals.yml             # optional
```

**Token model (verified 2026-07-06):** the default `GITHUB_TOKEN` handles
everything *except* the traffic endpoints — those reject `GITHUB_TOKEN` and
require a PAT (fine-grained: **Administration: read**; classic: `repo` scope).
Design consequence:

- All non-traffic collection + the `vitals`-branch push use `GITHUB_TOKEN`
  (`contents: write`). Zero setup.
- Traffic collection uses the optional `traffic-token` input. **If absent, the
  traffic section is skipped gracefully** (logged, `errors[]` note) — the
  action still works, just without views/clones/referrers.
- Recommended setup: ONE fine-grained PAT scoped to "All repositories"
  (Administration: read only), stored per-repo as secret `REPO_VITALS_TOKEN`.
  The rollout script (§9) sets the secret automatically via
  `gh secret set REPO_VITALS_TOKEN --repo <r>`. Fine-grained PATs expire
  (≤ 1 year) — REPORT.md must surface "traffic collection failing since
  <date>" prominently so an expired token is noticed, and the hub watchdog
  flags it.

### 3.3 Optional per-repo config (`.github/repo-vitals.yml`)

```yaml
branch: vitals               # data branch name
mirror_to_default_branch: false
report:
  title: "MyProject"
  badges: true               # generate shields.io endpoint JSON
science:                     # v1.1
  zenodo_doi: 10.5281/zenodo.XXXXX
dashboard: true              # set false to skip index.html
```

Defaults must make an empty config file (or none) fully functional.

### 3.4 Dashboard (`index.html`)

Single self-contained file: inline CSS/JS, one CDN dependency (ECharts,
pinned version), reads `history.ndjson` +
`VITALS.json` via relative fetch. Dark mode, mobile friendly. Plots: stars/
forks over time, views/clones (daily + 7-day rolling), per-release download
curves, referrer table, popular paths, activity (commits/PRs/issues per week).
Release dates drawn as vertical annotations on the traffic plot — the
"release impact overlay".

Viewing options (per-repo Pages is often already occupied by docs, so don't
require it): (a) enable Pages on `vitals` branch if free, (b) **the hub
mirrors every member repo's dashboard under `repos/<owner>-<repo>/`**
(implemented — primary path, always works: the hub already fetches each
repo's `VITALS.json`/`history.ndjson` for its watchdog, so it writes those
plus a copy of `index.html` into that directory and links to it from both
the fleet table and the per-repo entry in `REPORT.md`; no dependency on that
repo's own Pages), (c) third-party raw-HTML preview services exist
(raw.githack.com, htmlpreview.github.io) but are best-effort; don't document
them as the official path.

### 3.5 Hub (`repo-vitals-hub`, template repo)

Separate repo, created from a template. Config lists repos to track:

```yaml
repos:
  - biterik/relevantr
  - biterik/science2go
  - nfdi-matwerk/some-repo     # any repo with a vitals branch — read-only
```

Daily cron fetches each repo's `VITALS.json` + `history.ndjson` (raw URLs, no
auth for public repos), builds an aggregate dashboard on GitHub Pages, a
per-repo dashboard mirror (`repos/<owner>-<repo>/`, see §3.4(b)) for every
reporting repo, and a combined `REPORT.md` plus a dated copy under
`reports/` (this is the grant-report artifact). Optional `site_url` in
`hub-config.yml` makes the per-repo dashboard links inside `REPORT.md`
fully-qualified; otherwise they're root-relative (fine when the site is
browsed as a whole). The hub also runs a **watchdog**: flags repos whose
`VITALS.json` is > 3 days stale (usually the disabled-cron problem, §7).

## 4. Metrics

### v1 (ship)

| Group | Metrics | Source |
|---|---|---|
| Popularity | stars, forks, watchers, subscribers | REST `/repos/:o/:r` |
| Traffic | views, unique visitors, clones, unique cloners (daily) | `/traffic/views`, `/traffic/clones` |
| Referrers | top referrers with counts (daily archive) | `/traffic/popular/referrers` |
| Paths | top visited paths (daily archive) | `/traffic/popular/paths` |
| Releases | per-release, per-asset download counts | `/releases` |
| Activity | commits, PRs opened/merged, issues opened/closed, contributors | GraphQL (one query) |
| Meta | repo size, open/closed issue counts, latest release age | REST |

### Derived (computed at render time, never stored)

Growth per week/month; 7/30-day rolling traffic; release-impact overlay;
conversion funnel (visitors → clones → stars → downloads); simple linear +
exponential fit with ETA to next star milestone; composite health score
(weights: 40 % traffic trend, 30 % activity, 20 % community, 10 % release
adoption — clearly labeled heuristic, weights configurable).

### v1.1 (design in, implement second)

Zenodo DOI citations/downloads (Zenodo REST + OpenCitations), dependents count
(dependency-graph API where available), external-contributor count, discussion
counts. Schema already reserves a `science` key so v1.1 adds without migration.

## 5. Data model & storage

```
vitals branch:
  snapshots/2026-07-06.json    # immutable daily raw snapshot
  history.ndjson               # one line per day, merged/deduped
  VITALS.json                  # latest snapshot + derived summary
  REPORT.md                    # stable URL, always *today's* report
  reports/<owner>-<repo>-2026-07-06.md   # dated, self-identifying copy
  index.html
  schema/vitals.schema.json    # JSON Schema, versioned
```

Hub site (generated by `repo_vitals hub`, not a git branch — deployed to
Pages):

```
index.html                     # aggregate dashboard
hub-data.json                  # trimmed per-repo data behind it
REPORT.md                      # combined fleet report, stable URL
reports/<hub-title>-2026-07-06.md   # dated copy of the combined report
repos/<owner>-<repo>/          # per-repo dashboard mirror (§3.4(b)):
  index.html                     same index.html, fetches the files below
  VITALS.json                    verbatim copy fetched from that repo
  history.ndjson                 verbatim copy fetched from that repo
```

Snapshot (abridged):

```json
{
  "schema_version": 1,
  "date": "2026-07-06",
  "collected_at": "2026-07-06T03:21:14Z",
  "repo": "biterik/relevantr",
  "popularity": {"stars": 53, "forks": 12, "watchers": 53, "subscribers": 9},
  "traffic": {
    "views": {"2026-06-23": {"count": 91, "uniques": 40}, "...": {}},
    "clones": {"...": {}},
    "referrers": [{"referrer": "reddit.com", "count": 31, "uniques": 22}],
    "paths": [{"path": "/biterik/relevantr", "count": 50}]
  },
  "releases": [{"tag": "v1.3", "published_at": "...", "assets":
    [{"name": "mac-arm.zip", "downloads": 182}]}],
  "activity": {"commits_30d": 14, "prs_opened_30d": 3, "prs_merged_30d": 2,
               "issues_opened_30d": 5, "issues_closed_30d": 4,
               "contributors_total": 7},
  "errors": []
}
```

**Traffic-window merge (the core correctness problem):** the traffic API
returns a rolling 14-day window. Consecutive runs overlap 13 days, and GitHub
retro-adjusts recent days. Rule: merge per-day keyed by date, **newer run wins
for overlapping days**. A missed run ≤ 13 days causes no data loss; a gap > 14
days leaves an explicit hole (never interpolate; dashboard shows gaps).
`history.ndjson` stores the merged per-day truth; raw snapshots are the audit
trail and allow full regeneration if merge logic ever improves.

**Growth control:** daily snapshots ≈ 5–20 KB → ~5 MB/year worst case; fine.
Optional `compact` mode (yearly: fold snapshots > 1 year old into
`snapshots/2026.tar.gz`) — v1.1, not needed initially.

`schema_version` bumps only on breaking changes; renderer must read all past
versions (migrate-on-read, never rewrite history).

## 6. Report file (NFDI deliverable)

`REPORT.md` — human-readable, regenerated daily, Jinja2 template:
header (repo, date, badges) → 30/90/365-day summary table → sparkline-style
unicode charts (works in raw markdown) → release table → top referrers/paths →
link to dashboard. `VITALS.json` — the same data machine-readable. Both at the
stable raw URLs in §2. Also emit `badge/*.json` shields.io endpoint files
(stars trend, views/week) so repos can show live badges in their README.
Alongside the stable `REPORT.md`, also write a dated, repo-qualified copy to
`reports/<owner>-<repo>-<date>.md` — same content, filename that survives
being downloaded or emailed standalone (the hub does the same for its
combined report, qualified by hub title instead of repo). Every generated
`REPORT.md`, `index.html`, and hub page carries a footer attribution:
"repo-vitals by Erik Bitzek" with a link back to this repo — light marketing,
consistent across every surface a viewer might land on.

## 7. Robustness (hard-won gotchas — implement all)

1. **Scheduled-workflow auto-disable:** GitHub disables cron workflows after
   60 days without repo activity, and bot commits to a non-default branch may
   not count. Mitigations: (a) the action re-enables its own workflow via
   `PATCH /repos/:o/:r/actions/workflows/:id/enable` on every run, (b) the hub
   watchdog flags stale repos, (c) `workflow_dispatch` always available.
2. **Concurrent-push conflicts:** fetch + rebase + retry (3×, jittered) before
   push; `concurrency: repo-vitals` group in the action to serialize runs.
3. **Partial API failures:** never abort the whole run. Each collector section
   is try/except; failures land in `errors[]`, section value `null`. A snapshot
   with holes beats no snapshot. Exit code still 0 unless *everything* failed.
4. **Rate limits:** GITHUB_TOKEN = 1 000 req/h/repo; a full run needs < 20
   requests. Respect `Retry-After`; exponential backoff on 403/429.
5. **Empty/new repos, no releases, no Pages, forks:** all sections optional;
   action must succeed on a repo created yesterday. On forks default to no-op
   unless explicitly enabled (prevents forks of instrumented repos spamming).
6. **Private repos:** works unchanged; hub needs a PAT with read access for
   private members — document, don't require.
6b. **PAT expiry:** the traffic PAT (§3.2) is the single most likely silent
   failure. Surface token-age/failure loudly in REPORT.md and hub watchdog.
7. **Timezone:** all dates UTC everywhere. One snapshot per UTC day; a second
   run the same day overwrites (idempotent).
8. **First run:** auto-creates orphan `vitals` branch; backfills traffic with
   the available 14-day window; stars/forks history begins at day 0 (optionally
   backfill star history via GraphQL `stargazers(orderBy: STARRED_AT)` — cheap,
   do it: gives full star history from repo birth on first run).
9. **Determinism:** rendering is a pure function of history + templates —
   `repo_vitals render` can rebuild REPORT/dashboard from data alone at any
   time (survivability: the vitals branch is self-sufficient).

## 8. Repo layout (`biterik/repo-vitals`)

```
action.yml                      # composite action definition
repo_vitals/                    # Python package
  collect.py merge.py render.py commit.py cli.py schemas.py
templates/  report.md.j2  index.html.j2
schema/vitals.schema.json
deploy/
  rollout.sh                    # §9
  workflow-template.yml
hub-template/                   # template for repo-vitals-hub
tests/                          # pytest; fixtures = recorded API JSON
  test_merge.py                 # traffic-window merge is THE critical test
docs/  (README with 60-second quickstart, config reference, NFDI note)
.github/workflows/
  ci.yml                        # pytest + ruff on PR
  self-vitals.yml               # dogfood: repo-vitals runs on itself
  release.yml                   # tag → move @v1 major tag
```

Versioning: SemVer tags; floating `v1` major tag (standard Actions practice) so
consumer repos auto-receive fixes without PRs.

## 9. Fleet deployment ("all my repos") — yes, doable

`deploy/rollout.sh` (uses `gh` CLI, runs on Erik's Mac — no cluster involved).
Portability: a bash script, needs `gh` on `$PATH` (both checked upfront with
a clear error). Tested on macOS and Linux; on Windows there's no native
cmd.exe/PowerShell support — WSL (identical to Linux) or Git Bash is
required. The macOS-keychain traffic-token fallback (`repo-vitals-token` zsh
function) is optional and degrades to `--token`/`--no-secret` elsewhere.

```
gh repo list biterik --no-archived --json name,defaultBranchRef
  → for each repo (with include/exclude list):
      skip if .github/workflows/repo-vitals.yml exists
      gh secret set REPO_VITALS_TOKEN --repo <r>   # traffic PAT (§3.2)
      create branch add-repo-vitals
      add workflow file (from deploy/workflow-template.yml)
      open PR titled "Add repo-vitals daily stats"
```

PRs, not direct pushes — reviewable, skippable, and works on repos with branch
protection. Flags: `--repos a,b,c`, `--exclude x`, `--merge` (auto-merge where
allowed), `--dry-run`. Because consumers pin `@v1`, **future upgrades need no
redeployment**; rollout is one-time per repo. For a true org (e.g.
`nfdi-matwerk`) the same script works with `gh repo list <org>`; org-level
required workflows are an alternative but need GitHub Enterprise — not assumed.

## 10. Implementation milestones (for Claude Code)

| # | Deliverable | Acceptance |
|---|---|---|
| M1 | Repo created; collector + merge + tests | `--dry-run` produces valid snapshot for a real repo; merge tests pass incl. overlap/gap cases |
| M2 | Commit stage + composite action; dogfood on repo-vitals itself | vitals branch appears with VITALS.json/REPORT.md after workflow run |
| M3 | REPORT.md + badges + derived metrics | stable raw URL serves correct daily report |
| M4 | Dashboard index.html | renders offline from fixture data; release overlay works |
| M5 | rollout.sh + deploy to first wave (`openbis-mcp-server`, `LAMMPS-compile-n-bench`) | PRs open on both repos; one merged end-to-end |
| M6 | Hub template + Erik's hub instance | aggregate Pages dashboard live; watchdog flags a stale repo |
| M7 (v1.1) | Science metrics, compaction | Zenodo section appears when DOI configured |

Order matters: M1's merge logic is the only genuinely tricky code — test it
against recorded API fixtures before anything else is built on top.

## 11. Decisions (confirmed by Erik, 2026-07-06)

1. **Owner:** personal account `biterik` → action reference is
   `biterik/repo-vitals@v1` everywhere.
2. **License:** BSD-3-Clause.
3. **First rollout wave (M5):** `biterik/openbis-mcp-server` and
   `biterik/LAMMPS-compile-n-bench`.
4. **Chart library:** ECharts (pin version, single CDN script tag).
