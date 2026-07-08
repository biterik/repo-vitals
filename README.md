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

## Two separate things — read this first

This confuses people, so it gets its own section before anything else:

1. **The engine — this repo, `repo-vitals`.** You do **not** copy, clone, or
   fork it to use it on your own project (there's exactly one exception,
   [Part 2](#part-2-track-many-of-your-own-repos-at-once), and even that just
   *borrows a script* from it — it still doesn't add its code to your repo).
   You add one small file to a repo you own, that file points at
   `biterik/repo-vitals@v1`, and GitHub runs it for you every day. Nothing
   else to install.

2. **A "hub" — a separate repository that you create.** If you want *one*
   dashboard covering many repos — yours, a team's, a whole consortium's —
   you make your own small hub repository from a public template. It has
   its own name, you own it, and it is a **completely different repository
   from `repo-vitals`**. You never need a copy of `repo-vitals`'s code to
   create or run a hub. It just reads what other repos have already
   published. See [Part 4](#part-4-the-hub-one-view-across-many-repos).

If you only care about your own repo(s): go to
[Part 1](#part-1-track-one-repo-2-minutes). If you're the person who has to
report on repos *other people* own: skim Part 1 so you know what you're
asking them to do, then jump to
[Part 4](#part-4-the-hub-one-view-across-many-repos) — but every repo you
want in the report still needs Part 1 (or [Part 2](#part-2-track-many-of-your-own-repos-at-once))
done first, by whoever owns it.

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
consortium, and the **hub** (Part 4) aggregates a whole fleet into one
dashboard and one grant-ready report.

## Part 1: track one repo (2 minutes)

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

**Step 3 — you must do this once, nothing happens on its own yet.** Adding
the file above does not create any data by itself: it only tells GitHub
*when* to eventually run (daily, at 03:17 UTC). To get your first report
right now instead of waiting up to 24 hours, trigger it manually:
*Actions → repo-vitals → Run workflow* (or `gh workflow run repo-vitals`).
That first run creates the `vitals` branch and backfills your full star
history since the repo was created. After that, it's automatic, every day,
forever.

Once it's run at least once, see [Part 3](#part-3-view-your-repos-vitals)
to look at the result.

## Part 2: track many of your own repos at once

This is still just Part 1, done many times automatically — nothing to do
with the hub in Part 4.

`deploy/rollout.sh` is a script *inside the repo-vitals tool itself*
(`github.com/biterik/repo-vitals`) — the one and only time you'll need a
copy of that repo's code, and only for this script, not for anything it adds
to your projects. Clone it, then run the script from inside that clone:

```sh
git clone https://github.com/biterik/repo-vitals
cd repo-vitals
deploy/rollout.sh --dry-run                  # show the plan for all your repos
deploy/rollout.sh --repos projA,projB        # only these repos
deploy/rollout.sh --exclude big-mono-repo    # everything except
deploy/rollout.sh --merge                    # auto-merge PRs where allowed
```

`projA`, `projB` above are **GitHub repository names** (e.g. `mc-driver`),
*not* local folders — the script only talks to the GitHub API and never
needs your other projects checked out anywhere on disk.

It opens one PR per repo — reviewable, never a direct push, safe to re-run
(already-instrumented repos are skipped) — and sets the `REPO_VITALS_TOKEN`
secret on each. The PAT is taken from `--token`, `$REPO_VITALS_TOKEN`, or —
if defined — a `repo-vitals-token` shell function (e.g. a macOS keychain
lookup). With `--no-secret` the rollout proceeds without traffic collection.

**Merging the PR.** Nothing runs until the PR is merged into that repo's
default branch (GitHub only fires scheduled workflows from the default
branch) — an open, unmerged PR does nothing by itself. Either:

- command line: `gh pr merge add-repo-vitals --repo <owner>/<repo> --squash`
- browser: open `https://github.com/<owner>/<repo>/pulls`, open the PR
  titled "Add repo-vitals daily stats", click the green **Merge pull
  request** button, confirm.

(`--merge` above does this step automatically, for every repo where nothing
— like a required review — blocks it.)

Merging still doesn't create any data by itself — same as
[Part 1, Step 3](#part-1-track-one-repo-2-minutes): trigger the workflow
once (*Actions → repo-vitals → Run workflow*, or
`gh workflow run repo-vitals --repo <owner>/<repo>`), or wait for the daily
03:17 UTC cron.

`rollout.sh` needs bash and the [GitHub CLI](https://cli.github.com)
(`gh`, authenticated via `gh auth login`) — it checks for both and fails
with a clear message if either is missing. Tested on macOS and Linux; on
Windows there's no native cmd.exe/PowerShell support, so run it under
**WSL** (identical to the Linux case) or **Git Bash**.

## Part 3: view your repo's vitals

**Daily report** — open the stable URL (bookmarkable, downloadable, no auth
for public repos):

```
https://raw.githubusercontent.com/<owner>/<repo>/vitals/REPORT.md
```

or browse the `vitals` branch on GitHub, where `REPORT.md` renders nicely.
A dated, standalone copy also lives at
`.../vitals/reports/<owner>-<repo>-<date>.md` — safe to download without
colliding with another repo's or another day's report (see
[Reference](#reference-every-file-and-url-this-produces)).

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
- *Automatically*, with no setup at all, if someone tracks your repo in
  their [hub](#part-4-the-hub-one-view-across-many-repos) — the hub mirrors
  a live dashboard for every repo it tracks, whether or not that repo has
  its own GitHub Pages.

**Badges in your README** — live numbers served from the vitals branch:

```markdown
![stars](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2F<owner>%2F<repo>%2Fvitals%2Fbadge%2Fstars.json)
![views](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2F<owner>%2F<repo>%2Fvitals%2Fbadge%2Fviews-week.json)
![health](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2F<owner>%2F<repo>%2Fvitals%2Fbadge%2Fhealth.json)
```

**Scripts / pipelines** — consume `VITALS.json` (latest snapshot + derived
metrics; schema in [`schema/vitals.schema.json`](schema/vitals.schema.json))
or `history.ndjson` (one JSON object per day).

**Does `git clone` download this data?** Yes and no — the distinction
matters. A plain `git clone https://github.com/<owner>/<repo>` fetches the
*entire* repository, including every commit on the orphan `vitals` branch;
that data is genuinely on your disk afterward and readable fully offline
(`git show origin/vitals:REPORT.md` works with zero network access, once
cloned). What it does **not** do is put those files in your working
directory: `git clone` only checks out the *default* branch's tree, so
`REPORT.md` won't appear alongside your other files unless you explicitly
check out `vitals` — `git clone --branch vitals ... vitals-data` (used
above), `git worktree add`, or `git checkout vitals` in a scratch clone.
That flag is what surfaces the files, not what fetches them — they were
already fetched.

## Part 4: the hub — one view across many repos

For consortia, PIs, and project managers: a small repository — *yours*,
completely separate from `repo-vitals` — that pulls together everyone
else's already-published vitals data into one dashboard and one report.
**No part of this needs a copy of `repo-vitals`'s code.** Live example:
<https://biterik.github.io/repo-vitals-hub/>.

### Step 0 — create your own hub (one click, one time)

Open [github.com/biterik/repo-vitals-hub](https://github.com/biterik/repo-vitals-hub) —
notice it's marked **"Public template"**. Click the green **Use this
template** button → **Create a new repository** → give it a name (e.g.
`your-name/repo-vitals-hub`) → **Create repository**. You now own a brand
new, independent repository containing exactly three things:
`hub-config.yml`, `.github/workflows/hub.yml`, and a README. (If you'd
rather build it from source instead of using the button, the same three
files live in this repo's [`hub-template/`](hub-template/) — copy them into
a new repository yourself. Same result.)

Then, once, in your new repo: *Settings → Pages → Source: "GitHub Actions"*.

### Step 1 — find out what to track

Every repo owner installs repo-vitals on their own repos first — that's
[Part 1](#part-1-track-one-repo-2-minutes) or
[Part 2](#part-2-track-many-of-your-own-repos-at-once), done by *them*, not
by you. They then tell you their GitHub username and which repo names to
include — by email, chat, however your team communicates. There's no way
to discover this automatically: repo-vitals tracks by owner + repo name,
never by email address, and doesn't scan anyone's account on its own.

### Step 2 — tell your hub which repos to track

Open `hub-config.yml` in your hub repo and add a line per repo under
`repos:`. Two ways to do this — pick whichever you're comfortable with,
both have the exact same effect:

- **In the browser, no git needed:** click `hub-config.yml` → the pencil
  (✏️) "edit" icon → add a line → scroll down → **Commit changes** (directly
  to `main`).
- **On the command line:**
  ```sh
  git clone https://github.com/<you>/<hub-repo>
  cd <hub-repo>
  # edit hub-config.yml in any text editor, then:
  git add hub-config.yml
  git commit -m "add a repo to track"
  git push
  ```

Either way, `hub-config.yml` ends up looking like this:

```yaml
title: "My repo fleet"
repos:
  - biterik/openbis-mcp-server
  - biterik/LAMMPS-compile-n-bench
  - nfdi-matwerk/some-repo        # any repo with a vitals branch, even ones you don't own
```

The only requirement: each listed repo must **already** have repo-vitals
installed **and have completed at least one run** — a `vitals` branch must
exist (Part 1/2, done by its owner). The hub only ever *reads*; it never
installs anything anywhere, on any repo. A repo without a `vitals` branch
shows up flagged **"missing"** in your hub — it isn't silently dropped.

### Step 3 — that's it, no extra step to "run" anything

The instant you commit a change to `hub-config.yml` — browser or command
line, doesn't matter — it **automatically rebuilds the site**, no manual
button needed. (It also rebuilds every day on its own at 04:43 UTC, so it
never goes stale even if you forget about it.) Give it a minute or two,
then check the results below. If you're impatient or want to force a
rebuild without changing the config, you *can* trigger it by hand: your hub
repo → **Actions** tab → **hub** → **Run workflow** — but for the normal
case of adding or removing a repo, you never need to.

### Where you see the results

Once a build finishes (GitHub Pages redeploys automatically, usually within
a minute):

| What | Where |
|---|---|
| Aggregate dashboard (whole portfolio) | `https://<you>.github.io/<hub-repo>/` |
| Combined report (the funder/grant document) | `https://<you>.github.io/<hub-repo>/REPORT.md` |
| Dated archive of that report | `https://<you>.github.io/<hub-repo>/reports/` |
| Each repo's own interactive dashboard, mirrored | `https://<you>.github.io/<hub-repo>/repos/<owner>-<repo>/` |
| Each repo's own daily report | `https://raw.githubusercontent.com/<owner>/<repo>/vitals/REPORT.md` |
| Raw data behind the dashboard | `https://<you>.github.io/<hub-repo>/hub-data.json` |

A **watchdog** flags, in all of the above, any tracked repo whose data has
gone stale (expired token, disabled cron) or that was never instrumented —
so silent failures get noticed instead of quietly going missing. Private
repos aren't included by default (the hub reads public URLs only) — see
[`hub-template/README.md`](hub-template/README.md) for the token-based
option.

## Reference: every file and URL this produces

Once a repository is instrumented (Part 1/2), an orphan branch called
`vitals` is updated every day with:

| File | What it is | Stable URL |
|---|---|---|
| `REPORT.md` | Human-readable daily report: summary tables, trends, health score | `https://raw.githubusercontent.com/<owner>/<repo>/vitals/REPORT.md` |
| `VITALS.json` | The same data, machine-readable (JSON, schema-versioned) | `https://raw.githubusercontent.com/<owner>/<repo>/vitals/VITALS.json` |
| `index.html` | Interactive dashboard (charts, release-impact overlay) | serve via GitHub Pages, see [Part 3](#part-3-view-your-repos-vitals) |
| `history.ndjson` | Complete per-day history since instrumentation | `…/vitals/history.ndjson` |
| `badge/*.json` | Live shields.io badge endpoints (stars, views/week, health) | `…/vitals/badge/stars.json` |
| `snapshots/` | Immutable daily raw snapshots (audit trail) | `…/vitals/snapshots/2026-07-06.json` |
| `reports/` | Dated, repo-qualified copy of that day's `REPORT.md` — safe to download standalone | `…/vitals/reports/<owner>-<repo>-2026-07-06.md` |

`REPORT.md` is a **stable URL that always holds today's report** (for
badges/scripting); `reports/<owner>-<repo>-<date>.md` is the same content
under a name that survives being pulled out of context — download several
repos' reports into one folder (e.g. for a grant renewal) and none of them
collide or get confused for another day's. Your default branch is never
touched — daily commits go only to `vitals`.

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
- Release history: [CHANGELOG.md](CHANGELOG.md). Current release: **v1.3.0**.

## Local development

```sh
pip install -e ".[dev]"
pytest                # tests incl. the traffic-window merge suite
ruff check .
python tests/make_dashboard_fixture.py /tmp/demo   # synthetic dashboard data
```

## Citation

If you use repo-vitals in your work, please cite it — GitHub's
*"Cite this repository"* button uses [`CITATION.cff`](CITATION.cff):

> Bitzek, E. (2026). *repo-vitals* (Version 1.3.0) [Computer software].
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
