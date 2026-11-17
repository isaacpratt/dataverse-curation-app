# Dataverse Docent

Desktop curation assistant for Alliance Dataverse instances. It pulls datasets submitted for review, lets the curator approve a download, runs automated format-specific checks on the files, checks metadata completeness, and presents per-file and dataset-level findings in a desktop GUI with an exportable curation report.

Windows-first PySide6 app (single process, no web stack), API-token authenticated against the Dataverse Native/Search API, SQLite for local state, packaged with PyInstaller. Python 3.11+; environment and builds are pinned by `uv.lock`.

## Quick start

```bash
git clone https://github.com/isaacpratt/dataverse-curation-app.git
cd dataverse-curation-app
uv sync --group dev                  # .venv from uv.lock incl. dev tools
copy config.example.json config.json # PowerShell: Copy-Item config.example.json config.json
```

Set the token in `config.json` **or** use the environment instead (good for CI/headless): `DATAVERSE_BASE_URL`, `DATAVERSE_API_TOKEN`, `DATAVERSE_COLLECTION` — env wins over the file. At rest the token is stored in the OS credential store (Windows Credential Manager via keyring, keyed by base URL) and `config.json` keeps only a blank `api_token` with `api_token_source: "keyring"`; if the credential store is unavailable the save falls back to a plaintext token with owner-only ACLs on the file.

```bash
uv run poe run           # launch the desktop GUI
uv run pytest            # 550 tests (offscreen Qt)
uv run poe check         # lint + typecheck + tests
uv run poe build         # dist/curation-app-lite + dist/curation-app-full
uv run poe release-artefacts   # dist/licenses.md + NOTICE + both SBOMs
uv run python main.py --headless <staged_dir> --out report.json --format json --persistent-id doi:10.5072/FK2/EXAMPLE
```

The GUI defaults to the Borealis demo (demo.borealisdata.ca); pick or enter your instance in the top-nav Settings page. Headless exits 0 (clean), 1 (error-level findings), 2 (usage/IO failure) and rejects `--config/--dataverse` (GUI-only).

## Documentation

- `docs/html/index.html` — documentation index (source of truth): architecture, user guide, checks reference, dataverse integration, report contract, development setup
- `AGENTS.md` — agent-facing working agreement: repo layout, quality gates, beads workflow
- `DESIGN.md` — design system (tokens, components, motion)
- `SECURITY.md` — token handling, reporting a vulnerability, dependency/CVE policy

## Workflow

Work is tracked in [beads](https://github.com/gastownhall/beads) (`bd ready` for next work, `bd list` for the queue). CI (windows-latest) runs on every push/PR to master: pre-commit, ruff, mypy (engine + UI), pytest with coverage gates, headless smoke, UI probes, workflow lint, and an OSV vulnerability scan of the locked dependency set. Formatting is enforced by `ruff format`; dependency updates come through Dependabot.

## Roadmap

The remaining plan lives in **beads** (`bd ready` for next work, `bd list` for the full queue, `bd show <id>` for detail). The docs in `docs/html/` mirror it; beads win on disagreement.

## Context

The app is built on two existing projects:

| Project | Role in this app |
| --- | --- |
| [CUR_Res_CurationTools](../CUR_Res_CurationTools) | R inspection scripts and functions ported into the Python check engine |
| [rdm-review-dashboard](../rdm-review-dashboard) | Reference for Dataverse interaction, review workflow state, and reviewer/admin access patterns |

## License

MIT — see [LICENSE](LICENSE). Third-party components keep their own licenses: `uv run poe release-artefacts` writes the per-dependency inventory (`dist/licenses.md`), the attribution file (`dist/NOTICE`) and both SBOMs (`dist/sbom.cdx.json` CycloneDX, `dist/sbom.spdx.json` SPDX 2.3); the release workflow attaches all four. The check engine is ported from the MIT-licensed `CUR_Res_CurationTools` (© 2026 Curation Services Team, Digital Research Alliance of Canada).
