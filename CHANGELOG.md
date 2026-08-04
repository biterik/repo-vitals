# Changelog

All notable changes to repo-vitals are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/); versioning is
[SemVer](https://semver.org/) plus a floating `v1` major tag (so repos
pinned to `biterik/repo-vitals@v1` receive fixes automatically — see
[`release.yml`](.github/workflows/release.yml)).

## [1.4.0] - 2026-08-04

### Added

- **Provenance on every artifact.** `REPORT.md`, the dashboard, the hub table
  and `hub-data.json` now state two dates that were previously invisible: the
  repository's GitHub creation date (already collected as `meta.created_at`,
  but never rendered) and `derived.tracking_since` — the first day this
  archive actually covers, with `derived.tracking_days` alongside it. Without
  both, a total is unreadable: "1,282 clones" means nothing until you know it
  was over 43 days, and that the repo itself is nine months older than that.
- `tracking_since` deliberately counts only days carrying traffic data. The
  first-run star backfill writes sparse days reaching back to repo birth, so
  the old `derived.history_days` (`len(history)`) could claim 42 days of
  history for an archive whose real record was 41 days plus one star event
  from the previous October. `history_days` is retained, unchanged, for
  compatibility; nothing renders it any more.
- **All-time totals and 30-day averages.** New `derived.totals` (views,
  unique visitors, clones, unique cloners, stars gained, release downloads
  gained — everything since `tracking_since`) and `derived.per_30d`, each
  total divided by days tracked, times 30. Shown as a "Since tracking began"
  table in `REPORT.md`, as two new stat cards on the dashboard, and as a
  second table plus new columns in the hub. Averages are a rate, not a
  projection.
- Hub: the fleet table gained created / tracked-since / days / totals /
  averages columns and now scrolls horizontally rather than squeezing.

### Removed

- **The composite health score**, everywhere: `derived.health`,
  `compute_health()`, the `badge/health.json` shields endpoint, the
  `REPORT.md` line, the dashboard stat card, the hub column and
  `hub-data.json`'s `health_score`. A single 0–100 number is read as a
  verdict no matter how prominently it is labeled a heuristic, and it
  scored quiet, finished, perfectly useful repositories badly. The
  components it was built from remain visible as themselves.

  This changes the published shape of `VITALS.json` and removes a badge
  endpoint. It ships as a minor release because the floating `v1` tag moves
  with it, so all tracked repos pick it up on their next scheduled run —
  deliberate: the alternative was nine repos stuck on a metric that was
  removed for being misleading. **If you embedded the health badge in a
  README, remove that line** — the endpoint stops being written and the
  badge will show as unavailable once the vitals branch next updates.

### Fixed

- `write_outputs()` now deletes badge endpoints it no longer generates.
  Publishing commits the whole tree, so a file the renderer simply stops
  writing would sit on the `vitals` branch indefinitely, serving its last
  value as though it were live — `badge/health.json` would have done exactly
  that after this release.

### Changed

- Release downloads are now labeled in `REPORT.md` and the hub as GitHub's
  lifetime per-release counter, which starts at each release's publication
  and can therefore predate the tracking start date.

## [1.3.0] - 2026-07-08

First formally documented release — no code changes since 1.2.3, this
consolidates the hub work below with corrected, concrete documentation and
aligned version metadata.

### Docs

- README rewritten from scratch around a "Two separate things" mental model:
  `repo-vitals` (the engine — added to a repo you own, never cloned) versus
  the hub (a separate repository you create once from a public template —
  also never requires a `repo-vitals` clone). Corrects an earlier,
  overstated claim that pushing `hub-config.yml` doesn't rebuild the hub
  site; it does, automatically, via `hub.yml`'s
  `push: paths: [hub-config.yml]` trigger — manual "Run workflow" is now
  documented as an optional immediate-rebuild shortcut, not a required step.
  Reorganized into four numbered parts (track one repo, track many of your
  own, view your vitals, the hub) plus a reference table of every file/URL
  produced, replacing the earlier "Quickstart: which of these is you?"
  section.
- Fixed a long-standing broken anchor link (`#quickstart-target-ux`, which
  never corresponded to any README heading) in the traffic-collection
  warning banner of every generated `REPORT.md`; updated three other
  cross-file anchor references (`report.md.j2`, `hub-report.md.j2`,
  `hub-template/README.md`) to match the renamed headings.
- `hub-template/README.md` reordered (enable Pages before editing config)
  and rewritten to match the corrected auto-rebuild-on-push behavior.
- Clarified precisely what `git clone` does and doesn't bring down from the
  orphan `vitals` branch (fetched into `.git`, not checked out into the
  working tree without `--branch vitals`).

### Changed

- Version metadata (`pyproject.toml`, `repo_vitals/__init__.py`,
  `CITATION.cff`) now tracks the actual release instead of a stale
  `0.1.0`/`1.0.0`.

## [1.2.3] - 2026-07-08

### Added

- Hub dashboard: clones and release downloads charted as **trends over
  time** (not just current totals), reusing per-day data already recorded
  in each repo's `history.ndjson` — no new data collection was needed.

## [1.2.2] - 2026-07-08

### Fixed

- Hub: the per-repo dashboard mirror (`repos/<owner>-<repo>/`) now also
  mirrors that repo's `REPORT.md`, so the dashboard template's own relative
  `REPORT.md` link no longer 404s inside the mirror. Best-effort — mirroring
  still proceeds if this one fetch fails.

## [1.2.1] - 2026-07-08

### Added

- Hub dashboard: clones (30 d) and release downloads charted **per
  repository**, alongside the existing stars/views bars.
- `deploy/rollout.sh`: preflight check for the GitHub CLI (`gh`) — installed
  and authenticated — with a clear, OS-aware error instead of a raw
  command-not-found failure partway through.

### Docs

- Documented the Windows requirement (WSL or Git Bash) for `rollout.sh`, in
  the script's own header, the README, and ARCHITECTURE.md §9.

## [1.2.0] - 2026-07-06

### Added

- Hub: mirrors each reporting repo's own interactive dashboard under
  `repos/<owner>-<repo>/` (`index.html` + `VITALS.json` + `history.ndjson`)
  — implements ARCHITECTURE.md §3.4(b), "the hub renders every member
  repo's dashboard — primary path, always works." The fleet table and
  combined report link to real charts instead of a raw `REPORT.md`, with no
  dependency on a tracked repo's own GitHub Pages. Optional `site_url` in
  `hub-config.yml` fully-qualifies those links; otherwise they're
  root-relative.
- Both a repo's own `REPORT.md` and the hub's combined `REPORT.md` now also
  write a dated, name-qualified archive copy under `reports/` (e.g.
  `reports/biterik-relevantr-2026-07-06.md`) — safe to download standalone
  without colliding with another repo's or another day's report. The
  existing `REPORT.md` stable URL is unchanged.
- Consistent attribution footer ("repo-vitals by Erik Bitzek", linked) on
  every generated `REPORT.md` and `index.html`, per-repo and hub-level.

## [1.1.0] - 2026-07-06

### Added

- **Hub** (M6): a companion repository — `hub-template/`, or the
  [`repo-vitals-hub`](https://github.com/biterik/repo-vitals-hub) template —
  that aggregates any number of already-instrumented repos (read-only,
  public raw URLs, zero coordination with repo owners) into one aggregate
  dashboard, one combined `REPORT.md` (the grant-report artifact), and a
  watchdog that flags repos whose data has gone stale or aren't
  instrumented yet.

## [1.0.0] - 2026-07-06

Initial tagged release — milestones M1–M5:

- **M1** — collector, traffic-window merge (rolling 14-day window, newer
  run wins on overlap, gaps never interpolated), JSON schema, test suite, CI.
- **M2** — commit stage (push to an orphan `vitals` branch, retry on
  conflicts), the composite GitHub Action, self-dogfooding workflow.
- **M3** — `REPORT.md`, shields.io badge endpoints, derived metrics (health
  score, conversion funnel, star-milestone forecast), the `render`
  subcommand (rebuild everything from archived data alone).
- **M4** — self-contained interactive dashboard (`index.html`) with the
  release-impact overlay on the traffic chart.
- **M5** — `deploy/rollout.sh` for fleet-wide deployment (one PR per repo,
  never a direct push) and `release.yml` (pushing a SemVer tag moves the
  floating `v1` major tag).

[1.4.0]: https://github.com/biterik/repo-vitals/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/biterik/repo-vitals/compare/v1.2.3...v1.3.0
[1.2.3]: https://github.com/biterik/repo-vitals/compare/v1.2.2...v1.2.3
[1.2.2]: https://github.com/biterik/repo-vitals/compare/v1.2.1...v1.2.2
[1.2.1]: https://github.com/biterik/repo-vitals/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/biterik/repo-vitals/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/biterik/repo-vitals/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/biterik/repo-vitals/releases/tag/v1.0.0
