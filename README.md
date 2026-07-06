# repo-vitals

Long-term GitHub repository statistics: a daily GitHub Action that archives
traffic, stars, releases, and activity to an orphan `vitals` branch — with a
stable-URL `VITALS.json` / `REPORT.md` and a self-contained dashboard.

GitHub throws away traffic data after 14 days. repo-vitals keeps it forever,
in your own repo, with zero infrastructure.

**Status: under construction** — see [ARCHITECTURE.md](ARCHITECTURE.md) for
the full design. Milestone progress:

- [x] M1 — collector + traffic-window merge + tests
- [ ] M2 — commit stage + composite action (dogfood)
- [ ] M3 — REPORT.md, badges, derived metrics
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
