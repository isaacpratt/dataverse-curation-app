# ADR 0009 — Documentation is built from Markdown by Zensical and published on GitHub Pages

- **Status:** Accepted; information architecture superseded by `dv-uq6` (2026-11-23)
- **Date:** 2026-11-20

> **Update (2026-11-23, `dv-uq6`):** the docs were rewritten using Diátaxis
> and The Good Docs Project templates. The ten flat pages became a quadrant-
> grouped `docs/` tree (home, tutorials, how-to, reference, explanation), and
> the frozen `docs/html/` tree was retired. References below to `docs/html/`
> and to the original page names describe the state at the time of this
> decision; the current layout is recorded in `docs/reports/diataxis-audit.md`.

## Context

The documentation was 10 hand-authored, self-contained HTML files plus two
proposal snapshots in `docs/html/` and `docs/reports/`: inline CSS and SVG in
every file, no build step, no search, and a hard-coded nav duplicated across
pages. Any style or navigation change meant editing up to 12 files. The
Material for MkDocs team now builds Zensical, its supported successor
(Material for MkDocs reaches end of life 2027-05-05), so migrating now aligns
the docs stack with the maintained toolchain.

The user decided (2026-11-18) to host on GitHub Pages and ratified the
implementer choices on 2026-11-20 (bead `dv-l1f`).

## Decision

- **`zensical.toml` at the repo root uses Zensical's native config format**
  (not `mkdocs.yml` compatibility mode). `site_url` carries the Pages base
  path `https://isaacpratt.github.io/dataverse-curation-app/`.
- **The build source is a Markdown tree in `docs/`.** Ten live pages mirror
  the retired page names (index, architecture, checks-reference,
  entry-correctness, dataverse-integration, report-contract, engine-port,
  user-guide, development, proposals) with an explicit `nav`. The structure
  need not match the old HTML one for one — the docs set is scheduled for a
  Diátaxis rewrite (`dv-uq6`) — so this migration preserves *content*, not
  information architecture.
- **The two frozen proposal snapshots live in `docs/proposals/`**, are built
  and searchable, carry a "Historical snapshot" admonition, and are
  deliberately **out of the nav** via `not_in_nav`.
- **Diagrams and styling are Zensical-native.** The hand-written inline SVGs
  became Mermaid fenced blocks (native runtime via `pymdownx.superfences`
  custom fence); the app's palette feeds `extra.css` through theme variables.
- **`zensical` is a dev dependency** with `poe docs` (strict build) and
  `poe docs-serve` (live preview) tasks.
- **CI builds the docs on every PR** (`zensical build --strict`) and deploys
  to Pages on pushes to `master` only, via `actions/configure-pages`,
  `upload-pages-artifact` and `deploy-pages`. The deploy job is gated on the
  event and ref so forks and PRs can never publish.
- **The old `docs/html/` tree was kept as a frozen reference** until the
  Diátaxis rewrite. It was not the build source and not the published site.
  Retiring it immediately would have left no live reference while the repo
  was still private and the Pages deployment could not be verified end to end.
  `dv-uq6` retired it on 2026-11-23.

## Consequences

- A fresh clone can `uv sync` and build the whole site with one documented
  command; search, instant navigation, light/dark palettes and Mermaid come
  from Zensical rather than per-page hand-written markup.
- Strict builds validate internal links and anchors, so a broken cross
  reference fails CI before publishing.
- There was a transition period with two copies of the prose (Markdown build
  source, frozen HTML reference). `dv-uq6` rewrote the Markdown and retired
  `docs/html/` in one step; edits now go to Markdown only.
- README, AGENTS.md, SECURITY.md and the package metadata point at the Pages
  URL. Source comments that named `docs/html/*.html` were repointed at the
  new Markdown pages when the frozen tree was retired.

## Links

- Beads: `dv-l1f` (migration), `dv-uq6` (the later Diátaxis rewrite that superseded this page's information architecture).
- `zensical.toml` — native config, explicit nav, `not_in_nav`, Mermaid fence.
- `docs/*.md`, `docs/proposals/*.md`, `docs/assets/extra.css` — the site source.
- `.github/workflows/docs.yml` — PR build and master-only Pages deploy.
