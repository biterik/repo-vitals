# repo-vitals

**Long-term GitHub repository statistics with zero infrastructure.**
A daily GitHub Action archives your repo's traffic, stars, releases, and
activity to a `vitals` branch — with a daily report, machine-readable data,
live badges, and an interactive dashboard, all at stable URLs.

GitHub deletes traffic data (views, clones, referrers) after **14 days**.
repo-vitals keeps it forever, inside your own repository: no server, no
database, no external service.

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
  M1–M5 done (collector/merge, action, reports/badges, dashboard, rollout);
  M6 (multi-repo hub) and M7 (Zenodo/citation metrics) upcoming.

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
