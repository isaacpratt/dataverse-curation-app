---
page_type: governance
tgdp_template: Release notes
audience: all
---

# Release notes

The authoritative list of releases, with every published asset and checksum, is [GitHub Releases](https://github.com/isaacpratt/dataverse-curation-app/releases). This page summarises the channels and the most recent changes; it does not replace the release pages.

## Channels

| Channel | Tags | What you get |
| --- | --- | --- |
| Stable (`win`) | `vX.Y.Z` | Published release and the in-app updater's stable feed. |
| Prerelease (`win-beta`) | `vX.Y.Z-rc.N` or `vX.Y.Z-beta.N` | Marked pre-release, with separately named assets and feed so prereleases never reach the stable updater. |

Every release includes a Windows Setup executable, a portable zip, and `SHA256SUMS.txt`. A delta package is built against the previous release of the same channel when one exists; otherwise a full package is published. Current builds are unsigned — verify the checksum before running the installer. Signing through a managed service is planned, not yet shipped.

## Unreleased and 0.2.0

The entries below are condensed from `CHANGELOG.md`; see that file for the full list.

### Unreleased

- **Dataset header rebuilt** in three bands from the approved mockups, with a compact status widget and rail actions that only navigate.
- **Checks declare their scope** — all 24 checks now state whether their findings are dataset-level or file-level, and the dispatcher routes on that declaration.
- **The application core moved to `curation/`**, and the dataset detail page was split into sections under `ui/dataset/`.
- **All application code is type-checked under full `--strict`** (ADR 0008); only the four test packages relax the "annotate everything" rules.
- **Documentation is built from Markdown by Zensical** (ADR 0009), with CI configured to publish the site to GitHub Pages on master pushes and a strict build on every pull request.
- **Dark mode ships** — Settings → **Appearance** offers Light, Dark and Auto (follow system), with auto-switching driven by the operating system. The theme has separate light/dark role and contrast tables, the app mark and taskbar icon have dark variants, and the component gallery can show both themes side by side.
- **UI fixes** cover check-box appearance, unclassified Qt warnings failing the build, review-rule selection by click, two review rule cards, entry-check parameter layout, and the split into Dataset checks and File checks sections.

### 0.2.0 (2026-11-16)

- **uv is the package manager** and poe is the task runner; the committed lockfile is enforced in CI and pre-commit.
- **pre-commit is the local gate**, with codespell, a `config.json` guard, ruff, actionlint, and EOF/whitespace fixers.
- **Token storage moved to the OS credential store** (Windows Credential Manager via `keyring`); `config.json` keeps only `api_token_source`.
- **Configuration validation** reports the exact field on bad shapes and validates environment overrides.
- **The `client/` package replaced the single large client module**; the old `dataverse_client.py` compatibility shim was subsequently removed (the app is not a library).
- **CI** gained SHA-pinned actions, coverage gates, a headless smoke, UI probes, and an OSV dependency audit.
