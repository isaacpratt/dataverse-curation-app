---
page_type: reference
tgdp_template: Reference     # Reference | Glossary
audience: all                # curator | developer | contributor | all
---
# Configuration reference

`config.example.json` is the shipped template; `config.json` is the active file. All DATAVERSE_* environment variables override the corresponding `config.json` value; none are required (the Borealis demo is the default target).

## Configuration file keys

Every key present in `config.example.json`:

| Key | Type | Example / default | Meaning |
| --- | --- | --- | --- |
| `version` | integer | `1` | Configuration schema version (`CONFIG_SCHEMA_VERSION` in `curation/config.py`) |
| `dataverse` | object | — | Dataverse connection settings |
| `base_url` | string | `https://demo.borealisdata.ca` | Instance URL. The `DATAVERSE_BASE_URL` env override must be `https://` with a host (plain HTTP is refused because the token travels as `X-Dataverse-key`) and has trailing slashes trimmed; a value read from `config.json` is used as given |
| `api_token` | string | `""` | API token; blank while the token lives in the credential store |
| `api_token_source` | string | `"keyring"` | Where the token is persisted: `keyring`, `config` or `env`. Absent in older configs, where it is treated as `config` |
| `collection` | string | `""` | Collection alias used as the discovery `subtree`. The older keys `collection_alias` and `subtree` are accepted as aliases |
| `app` | object | — | Application-local settings |
| `workspace` | path | `C:/Users/<you>/Documents/curation-workspace` | Folder holding staged downloads and caches |
| `engine` | object | — | Engine settings |
| `optional_tools` | object | — | Paths to optional external tools |
| `tesseract` | string | `""` | Tesseract executable path (OCR) |
| `exiftool` | string | `""` | ExifTool executable path |
| `_comment` | string | human-readable note | Documentation embedded in the template; not read as a setting |

`tesseract` and `exiftool` live under `engine.optional_tools` in the template; `Config.load` also accepts the legacy `app.tesseract` and `app.exiftool` locations. Token load precedence is `DATAVERSE_API_TOKEN` (env) > OS credential store (keyring, keyed by base URL) > `config.json` plaintext. Plaintext tokens found in older configs migrate into the store on the next save. When the credential store is unavailable, the fallback keeps the token in `config.json` with owner-only ACLs.

## Environment variables

| Variable | Type | Resolution | Notes |
| --- | --- | --- | --- |
| `DATAVERSE_BASE_URL` | URL | env > config.json (default `https://demo.borealisdata.ca`) | Must be `https://` with a host; plain HTTP is refused with a clear error (the token travels as `X-Dataverse-key`); trailing slashes trimmed. This validation applies to the environment override, not to `config.json` |
| `DATAVERSE_API_TOKEN` | string | env > OS credential store (keyring) > config.json plaintext | Leading/trailing spaces stripped; empty means "no token (public-only)" |
| `DATAVERSE_COLLECTION` | string | env > config.json | Collection alias used for discovery (`subtree`) |
| `DATAVERSE_WORKSPACE` | path | env > config.json `app.workspace` (default `~/Documents/curation-workspace`) | Where staged downloads and caches live |

`DOCENT_STARTUP_LOG` is an independent opt-in runtime variable: when set to a file path, startup phase timings are appended there (see [Project layout](project-layout.md#startup-timing)).

## On-disk artefacts

Every file the app writes, its resolution rule and who writes it. Runtime caches are gitignored; a fresh clone starts clean.

| Path | Resolution | Written by | Contents |
| --- | --- | --- | --- |
| `config.json` | CWD (dev) · `%APPDATA%\Dataverse Docent\` (installed) · exe folder, its parent or grandparent (portable/plain frozen); a new file lands in the exe's parent | Settings; `poe build` ships `config.example.json` only | base_url, collection, workspace, tesseract/exiftool paths, api_token_source ("keyring" by default; plaintext token only as fallback when the credential store is unavailable) |
| `table_layout.json` | CWD (dev/frozen); probes never write here | Table layout controller | per-table saved column widths/orders |
| `dataset_sizes.json` | CWD | Batch size prober | cached dataset byte sizes for queue hints |
| `dashboard_cache.json` | CWD | Dashboard | last-seen list state to avoid cold paint |
| `requirements_profiles.json` | Same policy as `config.json` | Review configuration | versioned review rulesets (field + text-search rules, per-rule response templates) |
| `curation-workspace/*.db` / `*.db`, `*.sqlite` | `~/Documents/curation-workspace` (default) or `app.workspace` | `curation/storage.py` / actions log | SQLite local state (WAL): dataset inventory cache, check results, curation actions |
| `downloads/` | `app.workspace` subfolder (default `~/Documents/curation-workspace/downloads`) | Download manager | staged originals; skip-if-staged detection; never tracked |
| `workspace/`, `.curation-workspace/` | CWD (if used) | reserved/caches | variant of the workspace concept used by older builds; gitignored |
| `metadatablocks_cache.json`, `curation_labels.json` | `app.workspace` | Metadatablock/labels caches | field catalog + allowed curation labels (best-effort, disposable) |
| `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`, `.pyi-cache/`, `__pycache__/` | CWD | tooling | local caches; all gitignored |

## See also

- [Dataverse API](dataverse-api.md)
- [Entry-correctness rules](entry-checks.md)
- [Command-line reference](cli.md)
- [Glossary](glossary.md)
