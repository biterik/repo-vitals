# repo-vitals

Long-term GitHub repository statistics: a daily GitHub Action that archives
traffic, stars, releases, and activity to an orphan `vitals` branch — with a
stable-URL `VITALS.json` / `REPORT.md` and a self-contained dashboard.

GitHub throws away traffic data after 14 days. repo-vitals keeps it forever,
in your own repo, with zero infrastructure.

**Status: under construction** — see [ARCHITECTURE.md](ARCHITECTURE.md) for
the full design. Milestone progress:

- [x] M1 — collector + traffic-window merge + tests
- [x] M2 — commit stage + composite action (dogfood)
- [x] M3 — REPORT.md, badges, derived metrics
- [ ] M4 — dashboard
- [ ] M5 — fleet rollout script
- [ ] M6 — hub template

## Quickstart (target UX)

Add one workflow file to your repo:

```yaml
# .github/workflows/repo-vitals.yml
name: repo-vitals
on:
  schedule:
    - cron: "17 3 * * *"
  workflow_dispatch:
permissions:
  contents: write
jobs:
  vitals:
    runs-on: ubuntu-latest
    steps:
      - uses: biterik/repo-vitals@v1
        with:
          traffic-token: ${{ secrets.REPO_VITALS_TOKEN }}  # optional PAT
```

Daily data appears on the `vitals` branch at stable raw URLs:

```
https://raw.githubusercontent.com/<owner>/<repo>/vitals/VITALS.json
https://raw.githubusercontent.com/<owner>/<repo>/vitals/REPORT.md
```

## Badges

Every instrumented repo gets shields.io endpoint files on the vitals branch
(`badge/stars.json`, `badge/views-week.json`, `badge/health.json`). Show them
in your README:

```markdown
![stars](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2F<owner>%2F<repo>%2Fvitals%2Fbadge%2Fstars.json)
```

## Rebuilding reports from data

Rendering is a pure function of the archived data (survivability guarantee):

```sh
git clone --branch vitals https://github.com/<owner>/<repo> vitals-data
python -m repo_vitals render --data-dir vitals-data
```

## Local development

```sh
pip install -e ".[dev]"
pytest
ruff check .

# collect a snapshot for any repo without touching anything:
GITHUB_TOKEN=$(gh auth token) python -m repo_vitals run \
    --repo owner/name --dry-run --output-dir ./vitals-out
```

`--dry-run` writes `snapshots/<date>.json`, `history.ndjson`, and
`VITALS.json` to the output directory instead of committing to a branch.

## License

BSD-3-Clause. See [LICENSE](LICENSE).
