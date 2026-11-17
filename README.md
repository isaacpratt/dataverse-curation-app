# Dataverse Docent

Desktop curation assistant for Alliance Dataverse instances. It pulls datasets submitted for review, lets the curator approve a download, runs automated format-specific checks on the files, checks metadata completeness, and presents per-file and dataset-level findings in a desktop GUI with an exportable curation report.

## Download & install (Windows)

Get the latest from the [GitHub releases](https://github.com/isaacpratt/dataverse-curation-app/releases):

- **`DataverseDocent-win-Setup.exe`** — one click, installs per-user (no admin prompt); Start menu and desktop shortcuts, uninstall via Apps & Features.
- **`DataverseDocent-win-Portable.zip`** — unzip and run, nothing to install.
- **`SHA256SUMS.txt`** — verify the download with `Get-FileHash -Algorithm SHA256` (PowerShell) or `certutil -hashfile <file> SHA256`.

The build is unsigned, so Windows SmartScreen will warn on first run: **More info → Run anyway**. Install and updates are also delta-sized (usually a few MB after the first install).

Source & developers: see [docs/html/development.html](docs/html/development.html) (setup, tests, packaging) and [docs/html/user-guide.html](docs/html/user-guide.html) (using the app).

## Roadmap

The remaining plan lives in **beads** (`bd ready` for next work, `bd list` for the full queue, `bd show <id>` for detail). The docs in `docs/html/` mirror it; beads win on disagreement.

## Context

The app is built on two existing projects:

| Project | Role in this app |
| --- | --- |
| [CUR_Res_CurationTools](../CUR_Res_CurationTools) | R inspection scripts and functions ported into the Python check engine |
| [rdm-review-dashboard](../rdm-review-dashboard) | Reference for Dataverse interaction, review workflow state, and reviewer/admin access patterns |
