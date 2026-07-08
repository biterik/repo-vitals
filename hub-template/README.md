# repo-vitals hub

An aggregate view over many [repo-vitals](https://github.com/biterik/repo-vitals)-instrumented
repositories: one dashboard, one combined report, and a watchdog that flags
repos whose data has gone stale.

Everything is **read-only**: the hub fetches each tracked repo's published
`VITALS.json`/`history.ndjson` from public raw URLs. No permissions, no
tokens, no coordination with the repo owners.

## Set up your own hub (5 minutes)

This repository is a **GitHub template** — click **Use this template** on
its GitHub page to get your own independent copy (`your-name/repo-vitals-hub`
or any name you like). It is completely separate from `repo-vitals` itself;
you never need a copy of that repo's code to run a hub.

1. **Use this template** → **Create a new repository**.
2. Enable Pages, once: in your new repo, *Settings → Pages → Source:
   "GitHub Actions"*.
3. Edit `hub-config.yml`: set a title and list the repositories to track.
   Any repo with a `vitals` branch works — see the
   [2-minute install](https://github.com/biterik/repo-vitals#part-1-track-one-repo-2-minutes)
   for repos that don't have one yet. You can do this entirely in the
   browser: open the file, click the pencil (✏️) icon, edit, **Commit
   changes**.

That's it — committing a change to `hub-config.yml` **automatically**
rebuilds the site (the workflow triggers on any push that touches that
file). No separate "run it" step needed. It also rebuilds on its own every
day at 04:43 UTC, so it never goes stale even untouched. If you want the
site updated immediately without changing the config, you can still trigger
a rebuild by hand: *Actions → hub → Run workflow* — but that's an optional
shortcut, never a required step.

Your fleet is then live at:

- `https://<your-name>.github.io/<hub-repo>/` — aggregate dashboard
- `https://<your-name>.github.io/<hub-repo>/REPORT.md` — combined report
  (the document to attach to a funder or project report)
- `https://<your-name>.github.io/<hub-repo>/hub-data.json` — machine-readable
- `https://<your-name>.github.io/<hub-repo>/repos/<owner>-<repo>/` — a live
  **interactive dashboard for each tracked repo**, mirrored by the hub
  itself. Clicking a repo from the fleet table or the combined report opens
  charts, not a raw markdown file — this works even for repos that never
  set up their own GitHub Pages. Set `site_url` in `hub-config.yml` to your
  hub's own address above so these links are fully-qualified inside
  `REPORT.md` too (optional; relative links already work when the site is
  browsed as a whole).
- `https://<your-name>.github.io/<hub-repo>/reports/` — every day's combined
  report, kept under a name that always carries the fleet title and the
  date (e.g. `my-repo-fleet-2026-07-06.md`) — safe to download and file
  away without colliding with anyone else's `REPORT.md`.

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
