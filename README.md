# repo-vitals

![stars](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fbiterik%2Frepo-vitals%2Fvitals%2Fbadge%2Fstars.json)
![views](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fbiterik%2Frepo-vitals%2Fvitals%2Fbadge%2Fviews-week.json)
![health](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fbiterik%2Frepo-vitals%2Fvitals%2Fbadge%2Fhealth.json)
(live badges — served from this repo's own `vitals` branch)

**Your repository has a story. GitHub only remembers the last 14 days of it.**

repo-vitals is a tiny GitHub Action that turns any repository into its own
permanent analytics archive. Every day it records traffic, stars, releases,
and activity to a `vitals` branch in the repo itself — and publishes a daily
report, machine-readable data, live badges, and an interactive dashboard at
stable URLs. **No server. No database. No external service. Your data stays
in your repo, forever.**

## Why?

**If you maintain open-source software**, GitHub's built-in insights can't
answer the questions you actually have: *Is my project growing? Did that
release bring anyone in? What caused Tuesday's spike? Where do visitors come
from — and do they stick around?* GitHub deletes traffic data (views, clones,
referrers) after 14 days, so by the time you wonder, the evidence is gone.
repo-vitals keeps every day since instrumentation and turns it into trends,
release-impact overlays, a conversion funnel (visitors → clones → stars →
downloads), star-milestone forecasts, and a health score — plus README badges
that show your project is alive.

**If you manage a portfolio of repositories** — a research consortium, an
institute, a company's open-source projects — you have to *report* on them:
to funders, in grant renewals, in annual reviews. repo-vitals gives every
repo a daily, stable-URL `REPORT.md` and `VITALS.json` that anyone can
download or script against, with zero coordination: no accounts, no
dashboards behind logins, no asking maintainers for numbers. It was built
for exactly this case in the [NFDI-MatWerk](https://nfdi-matwerk.de)
consortium, and the upcoming **hub** (see below) aggregates a whole fleet
into one dashboard and one grant-ready report.

Adoption is one ~15-line workflow file per repo — or one command for your
entire account (see [fleet rollout](#instrument-many-repositories-at-once)).
Your default branch is never touched, and if you ever stop using it, the
archive remains: plain JSON and markdown in a git branch you own.

## What you get

Once a repository is instrumented, an orphan branch called `vitals` is
updated every day with:

| File | What it is | Stable URL |
|---|---|---|
| `REPORT.md` | Human-readable daily report: summary tables, trends, health score | `https://raw.githubusercontent.com/<owner>/<repo>/vitals/REPORT.md` |
| `VITALS.json` | The same data, machine-readable (JSON, schema-versioned) | `https://raw.githubusercontent.com/<owner>/<repo>/vitals/VITALS.json` |
| `index.html` | Interactive dashboard (charts, release-impact overlay) | serve via GitHub Pages, see below |
| `history.ndjson` | Complete per-day history since instrumentation | `…/vitals/history.ndjson` |
| `badge/*.json` | Live shields.io badge endpoints (stars, views/week, health) | `…/vitals/badge/stars.json` |
| `snapshots/` | Immutable daily raw snapshots (audit trail) | `…/vitals/snapshots/2026-07-06.json` |
| `reports/` | Dated, repo-qualified copy of that day's `REPORT.md` — safe to download standalone | `…/vitals/reports/<owner>-<repo>-2026-07-06.md` |

`REPORT.md` is a **stable URL that always holds today's report** (for
badges/scripting); `reports/<owner>-<repo>-<date>.md` is the same content
under a name that survives being pulled out of context — download several
repos' reports into one folder (e.g. for a grant renewal) and none of them
collide or get confused for another day's.

Your default branch is never touched — daily commits go only to `vitals`.

## Install: instrument a repository (2 minutes)

**Step 1** — add one workflow file to your repo as
`.github/workflows/repo-vitals.yml`:

```yaml
name: repo-vitals
on:
  schedule:
    - cron: "17 3 * * *"   # daily
  workflow_dispatch:        # allows manual runs
permissions:
  contents: write   # push to the vitals branch
  actions: write    # let the action re-enable this workflow if GitHub pauses it
concurrency:
  group: repo-vitals
jobs:
  vitals:
    runs-on: ubuntu-latest
    steps:
      - uses: biterik/repo-vitals@v1
        with:
          traffic-token: ${{ secrets.REPO_VITALS_TOKEN }}  # optional, see step 2
```

That's it — the action works immediately with the default `GITHUB_TOKEN`.

**Step 2 (recommended)** — enable traffic collection. GitHub's traffic API
(views/clones/referrers) rejects the default token and needs a personal
access token (PAT):

1. Create a fine-grained PAT at github.com → *Settings → Developer settings →
   Fine-grained tokens*: repository access "All repositories" (or selected),
   with the single permission **Administration: read-only**.
   (A classic token with `repo` scope also works.)
2. Store it in the repo: *Settings → Secrets and variables → Actions* →
   new secret `REPO_VITALS_TOKEN`. Or from a terminal:
   ```sh
   gh secret set REPO_VITALS_TOKEN --repo <owner>/<repo>
   ```

Without the PAT everything still works — the traffic section is skipped and
the report says so. Fine-grained PATs expire (max 1 year); when that happens
the report shows a loud warning rather than failing silently.

**Step 3** — don't wait for 03:17 UTC: run it once now via
*Actions → repo-vitals → Run workflow* (or `gh workflow run repo-vitals`).
The first run creates the `vitals` branch and backfills your full star
history since the repo was created.

### Instrument many repositories at once

`deploy/rollout.sh` (from a clone of this repo) opens a PR against every one
of your repos — reviewable, never a direct push, safe to re-run (instrumented
repos are skipped):

```sh
deploy/rollout.sh --dry-run                  # show the plan for all your repos
deploy/rollout.sh --repos projA,projB        # only these repos
deploy/rollout.sh --exclude big-mono-repo    # everything except
deploy/rollout.sh --merge                    # auto-merge PRs where allowed
```

It also sets the `REPO_VITALS_TOKEN` secret on each repo. The PAT is taken
from `--token`, `$REPO_VITALS_TOKEN`, or — if defined — a `repo-vitals-token`
shell function (e.g. a macOS keychain lookup). With `--no-secret` the rollout
proceeds without traffic collection.

`rollout.sh` needs bash and the [GitHub CLI](https://cli.github.com)
(`gh`, authenticated via `gh auth login`) — it checks for both and fails
with a clear message if either is missing. Tested on macOS and Linux; on
Windows there's no native cmd.exe/PowerShell support, so run it under
**WSL** (identical to the Linux case) or **Git Bash**.

## Look at the status of a repository

**Daily report** — open the stable URL (bookmarkable, downloadable, no auth
for public repos):

```
https://raw.githubusercontent.com/<owner>/<repo>/vitals/REPORT.md
```

or browse the `vitals` branch on GitHub, where `REPORT.md` renders nicely.

**Interactive dashboard** — the `vitals` branch carries a self-contained
`index.html` (charts for traffic with release markers, stars/forks, release
downloads, activity). To view it:

- *GitHub Pages* (if free on that repo): Settings → Pages → deploy from the
  `vitals` branch. Example: this repo's own dashboard is live at
  **<https://biterik.github.io/repo-vitals/>**.
- *Locally*, from any machine:
  ```sh
  git clone --branch vitals https://github.com/<owner>/<repo> vitals-data
  python3 -m http.server -d vitals-data     # → http://localhost:8000
  ```

**Badges in your README** — live numbers served from the vitals branch:

```markdown
![stars](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2F<owner>%2F<repo>%2Fvitals%2Fbadge%2Fstars.json)
![views](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2F<owner>%2F<repo>%2Fvitals%2Fbadge%2Fviews-week.json)
![health](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2F<owner>%2F<repo>%2Fvitals%2Fbadge%2Fhealth.json)
```

**Scripts / pipelines** — consume `VITALS.json` (latest snapshot + derived
metrics; schema in [`schema/vitals.schema.json`](schema/vitals.schema.json))
or `history.ndjson` (one JSON object per day).

## Watch a whole fleet: the hub

For consortia and project managers, a companion **hub** repository — three
files, [set up in 5 minutes](hub-template/README.md) from
[`hub-template/`](hub-template/) or the
[repo-vitals-hub template repo](https://github.com/biterik/repo-vitals-hub) —
tracks any number of instrumented repos. **Live example:
<https://biterik.github.io/repo-vitals-hub/>.**

```yaml
# hub config: just a list — including repos you don't own
repos:
  - biterik/openbis-mcp-server
  - biterik/LAMMPS-compile-n-bench
  - nfdi-matwerk/some-repo
```

A daily cron fetches each repo's published `VITALS.json` (public raw URLs —
**read-only, no permissions, no coordination with the repo owners**) and
builds:

- an **aggregate dashboard** on GitHub Pages: the whole portfolio at a glance,
- a **live dashboard mirrored per repo**, at `repos/<owner>-<repo>/` on the
  hub's own site — clicking a repo from the fleet table or the report opens
  an interactive chart, not a raw markdown file, even if that repo never set
  up its own GitHub Pages,
- a **combined REPORT.md** — the document you attach to a funder report
  (`https://<you>.github.io/<hub>/REPORT.md`), plus a dated copy under
  `reports/` for filing away without collisions,
- a **watchdog** that flags repos whose data has gone stale (expired token,
  disabled cron) or that aren't instrumented yet, so silent failures get
  noticed.

That means anyone with a list of NFDI-MatWerk repositories can stand up
their own fleet report, self-service. The only prerequisite: each tracked
repo has repo-vitals installed (its `vitals` branch must exist) — which is
what the [2-minute install](#install-instrument-a-repository-2-minutes) and
[fleet rollout](#instrument-many-repositories-at-once) are for.

## Generate reports yourself (no Action needed)

Everything the Action does can be run locally with Python ≥ 3.11:

```sh
git clone https://github.com/biterik/repo-vitals
cd repo-vitals
pip install .
```

**Collect a snapshot for any repository** (writes to a local directory,
touches nothing on GitHub):

```sh
export GITHUB_TOKEN=$(gh auth token)      # any token; enables API access
export REPO_VITALS_TOKEN=<traffic PAT>    # optional; enables traffic data
python -m repo_vitals run --repo <owner>/<repo> --dry-run --output-dir ./out
open ./out/REPORT.md
```

Run it on consecutive days with the same `--output-dir` and the history
accumulates exactly as it would on the vitals branch.

**Rebuild reports from archived data alone** (no API calls, no tokens — the
vitals branch is self-sufficient):

```sh
git clone --branch vitals https://github.com/<owner>/<repo> vitals-data
python -m repo_vitals render --data-dir vitals-data
```

This regenerates `REPORT.md`, `VITALS.json`, badges, and the dashboard from
`history.ndjson` + `snapshots/` — useful after improvements to the report
format, or decades later.

## How it works, briefly

- A ~15-line workflow calls the composite action `biterik/repo-vitals@v1`,
  which runs a small Python package (dependencies: `requests`, `jinja2`).
- Each run stores an immutable snapshot and merges the rolling 14-day traffic
  window into the per-day history (newer data wins on overlap; gaps longer
  than 14 days remain visible gaps — never interpolated).
- Rendering is a pure function of the archived data (see `render` above).
- Robustness: partial API failures never abort a run; pushes retry on
  conflicts; the action re-enables its own workflow if GitHub's 60-day
  auto-disable hits; forks are a no-op by default.
- Full design: [ARCHITECTURE.md](ARCHITECTURE.md). Milestone status:
  M1–M6 done (collector/merge, action, reports/badges, dashboard, rollout,
  hub); M7 (Zenodo DOI citations/downloads for research software) upcoming.

## Local development

```sh
pip install -e ".[dev]"
pytest                # 50 tests incl. the traffic-window merge suite
ruff check .
python tests/make_dashboard_fixture.py /tmp/demo   # synthetic dashboard data
```

## Citation

If you use repo-vitals in your work, please cite it — GitHub's
*"Cite this repository"* button uses [`CITATION.cff`](CITATION.cff):

> Bitzek, E. (2026). *repo-vitals* (Version 1.0.0) [Computer software].
> https://github.com/biterik/repo-vitals

## Funding

Funded by the Deutsche Forschungsgemeinschaft (DFG, German Research
Foundation) under the National Research Data Infrastructure — NFDI 38/1 —
project number [460247524](https://gepris.dfg.de/gepris/projekt/460247524)
(NFDI-MatWerk consortium).

## Author

Erik Bitzek ([ORCID 0000-0001-7430-3694](https://orcid.org/0000-0001-7430-3694))
Department of Materials Science, WW8-Materials Simulation,
Friedrich-Alexander-Universität Erlangen-Nürnberg,
Dr.-Mack-Straße 77, 90762 Fürth, Germany
<e.bitzek@mpi-susmat.de>

## License

BSD-3-Clause. See [LICENSE](LICENSE).
