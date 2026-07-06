# repo-vitals hub

An aggregate view over many [repo-vitals](https://github.com/biterik/repo-vitals)-instrumented
repositories: one dashboard, one combined report, and a watchdog that flags
repos whose data has gone stale.

Everything is **read-only**: the hub fetches each tracked repo's published
`VITALS.json`/`history.ndjson` from public raw URLs. No permissions, no
tokens, no coordination with the repo owners.

## Set up your own hub (5 minutes)

1. Copy the three files of this template into a new repository
   (e.g. `your-name/repo-vitals-hub`):
   `hub-config.yml`, `.github/workflows/hub.yml`, this `README.md`.
2. Edit `hub-config.yml`: set a title and list the repositories to track.
   Any repo with a `vitals` branch works — see the
   [2-minute install](https://github.com/biterik/repo-vitals#install-instrument-a-repository-2-minutes)
   for repos that don't have one yet.
3. Enable Pages: *Settings → Pages → Source: "GitHub Actions"*.
4. Run it once: *Actions → hub → Run workflow*.

Your fleet is then live at:

- `https://<your-name>.github.io/<hub-repo>/` — aggregate dashboard
- `https://<your-name>.github.io/<hub-repo>/REPORT.md` — combined report
  (the document to attach to a funder or project report)
- `https://<your-name>.github.io/<hub-repo>/hub-data.json` — machine-readable

The site rebuilds daily (04:43 UTC), on every change to `hub-config.yml`,
and on demand via *Run workflow*.

## The watchdog

Repos whose data is older than `stale_after_days` (default 3) — or that have
no `vitals` branch at all — are flagged prominently on the dashboard and at
the top of the report. The two usual causes: GitHub disabled the repo's cron
after 60 days without activity (re-run it manually once), or the traffic PAT
expired (create a new one and update the `REPO_VITALS_TOKEN` secret).

## Private repositories

The hub reads public raw URLs, so private repos are not aggregated out of
the box. Track them by running the hub build with a token-authenticated
fetch — documented, not required (see the repo-vitals README).
