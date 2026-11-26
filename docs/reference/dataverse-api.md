---
page_type: reference
tgdp_template: Reference     # Reference | Glossary
audience: all                # curator | developer | contributor | all
---
# Dataverse API reference

The client uses the Native/Search API only — no PostgreSQL/Solr. All endpoints are relative to `config.dataverse.base_url`; authentication is the `X-Dataverse-key` header. In the tables below, `…/resource` abbreviates `/api/datasets/:persistentId/resource`, and `CrawlWorker` is the background worker that performs a dashboard discovery pass.

## Authentication

| Aspect | Behaviour |
| --- | --- |
| Header | `X-Dataverse-key: <token>` |
| Search visibility | A token returns drafts; without one, only published datasets are visible |
| Token at rest | OS credential store by default (Windows Credential Manager via keyring, keyed by base URL); `api_token_source` names the source and `api_token` stays blank. Fallback: `config.json` with owner-only ACLs (source `config`) |
| Sources | `DATAVERSE_API_TOKEN` (env, source `env`) > keyring > `config.json` plaintext; legacy plaintext tokens migrate into the store on the next save |
| Settings | Token set or changed in Settings (Ctrl+,) |
| Preset | Borealis Demo — `demo.borealisdata.ca` → `https://demo.borealisdata.ca` |
| 401 response | A selectable dialog points at Settings. The token is never stored in SQLite and never leaves in diagnostics copies |
| Base URL validation | Must be `https://` with a host; plain HTTP and trailing slashes are rejected/normalised in `curation/config.py` |

## Endpoints used

| Purpose | Endpoint | Notes |
| --- | --- | --- |
| Version check | `GET /api/info/version` | Settings' **Test connection** button displays the instance version; this request is made directly by the Settings pane, not through the client |
| Discovery | `GET /api/search?q=*&type=dataset&per_page=1000&start=<n>&subtree=<alias>` | `start` is an offset, not a page. Empty or `:root`/`root` = whole repo (no subtree). First response carries `total_count`, so paging is total-driven; dedup by persistent ID |
| In-review (strict) | `GET /api/datasets/:persistentId/locks` | `lockType`/`reason` containing "review" (`locks_indicate_review`); `list_datasets_in_review()` filters the draft superset |
| Metadata | `GET /api/datasets/:persistentId?persistentId=<doi>` | Citation blocks; `versionState` drives the header link |
| File inventory | `GET …/versions/:draft` (fallback `:latest`, `:latest-published`) | `normalize_files` keeps filename, directoryLabel, filesize, contentType, checksum, UNF, tabular/original-format fields |
| Bundle download | `GET /api/access/dataset/:persistentId?…&version=draft` | No `Accept: application/json` (406); streamed `iter_content(1 MB)` with progress; tries draft → latest → unversioned |
| Original format | `GET /api/access/datafile/:id?format=original` | Tabular originals (`.sav` etc.) |
| Variable metadata | `GET /api/access/datafile/:id/metadata/ddi` | Per-file DDI: variable names, labels and types for the coverage check and the dictionary draft (`metadata.var_coverage`). Ingest state is read from the `ingestStatus` field of the version payload, not from a live endpoint |
| Curation status | `GET …/curationStatus?persistentId=<doi>` (+ `includeHistory`) | Current label + `createTime` + assigner; `None` when unset (4xx tolerated) |
| Bulk curation report | `GET /api/datasets/listCurationStates` (superuser, `text/csv`) | Must send `Accept: text/csv` (406 on JSON). 401/403/404 → per-dataset fallback |
| Compare versions | `GET …/versions/:latest-published/compare/:draft` | Metadata/terms diffs + added/removed/replaced files; `None` when nothing comparable |
| Version list | `GET …/versions?persistentId=<doi>` | `versionState`/`createTime`/`releaseTime` for the timeline (`[]` on 4xx) |
| Timestamps | `GET …/timestamps` (numeric-id fallback) | `createTime`, `publicationTime`, `globalIdCreateTime`, draft `lastUpdateTime` (also fed to the depositor follow-up tracker) |
| Notifications | `GET /api/notifications/all?…&inAppNotificationFormat=true` | `SUBMITTEDDS` matched by PID (`datasetPersistentIdentifier`), collection straight from API — no text comparison |
| Allowed labels | `GET …/allowedCurationLabels?persistentId=<doi>` | Comma-separated, instance/collection-specific; empty when unconfigured |
| Set / delete label | `PUT` / `DELETE …/curationStatus?…&label=<label>` | Wired to the UI — dataset detail Assessment Action pushes the chosen label (timeline-logged) |

## Curation labels

| Aspect | Behaviour |
| --- | --- |
| Resolution | Every dashboard refresh resolves labels bulk-first (`CrawlWorker`) |
| Dropdown | The union is remembered per pull in `dashboard_cache.json`; instances without labels show "All labels" |
| Hard-coded labels | None; labels come from `allowedCurationLabels` / the bulk report |

## Review-state discovery

| Aspect | Behaviour |
| --- | --- |
| `search_item_state` | A published-plus-new-draft dataset can surface as RELEASED yet carry "Draft" in `publicationStatuses` |
| Draft/review markers | Markers anywhere win |
| Duplicate PIDs | The draft row is kept — otherwise in-progress versions vanish from draft filtering |
| Status combo filters | All / DRAFT / Published / In Review / Deaccessioned |
| Default dashboard view | All drafts |

## Discovery and inventory enrichment

| Phase | Behaviour |
| --- | --- |
| a — Search | `GET /api/search` at `per_page=1000`; first response's `total_count` gives the page count, so the loop is total-driven and progress shows "page 2 of 3". Dedup by PID. Each page logs `Search page N (start=…): M item(s), K new` |
| b — Inventory enrichment | Drafts first, capped (200), 5 workers: one version doc per row adds the real byte total, true depositor, authoritative state and the draft's `lastUpdateTime` (drives the depositor follow-up signal). Sums only — never whole file arrays |
| c — Lock confirmation | Optional strict mode: `dataset_in_review()` checks `…/locks` for "review" |

Termination conditions for the search loop: the collected count reaches `total_count`; a page comes back short or empty (the ground truth for a corpus that shifts under a long crawl); or the runaway guard trips. Whatever ends it, collected vs. total is reconciled and any gap is logged. `max_pages=100` is a runaway guard only (100 × 1000 = 100k). The search reconciliation also merges a dataset listed twice (its published doc and its draft doc) — the index counts documents, not datasets.

## Download flow (approval-gated)

| Phase | Operation | Behaviour |
| --- | --- | --- |
| 1 — Quote | `quote(pid)` | Count + bytes (original size for tabular). No bytes moved |
| 2 — Approve | `DownloadApprovalDialog` | Large-dataset warning. A dataset with `guestbookId` renders the guestbook fields here (prefilled from `GET /api/users/:me`); nothing downloads until approved |
| 3 — Answer guestbook | `POST /api/access/dataset/:persistentId` | Body `{"guestbookResponse": {name, email, institution, position, answers[]}}` → `data.signedUrl` |
| 4 — Stream | Stream to `_bundle.zip.part` | Atomic rename; plain datasets try draft → latest → unversioned (3× retry per version); guestbook datasets stream the signed URL once |
| 5 — Stage | Atomic unzip | `files.new/` → swap, zip-slip guard, originals fetched, `.tab` removed (originals-only) |
| 6 — Verify | `verify()` | `(ok, problems, warnings)`: originals by size, rest by checksum. Previous stage survives partial failure |

## Errors, retries and limits

| Case | Behavior |
| --- | --- |
| Transient network (ConnectionError/ChunkedEncodingError/Timeout/ConnectionResetError, WinError 10054) | 3× retry, 1.5·(attempt+1) s backoff; 429/503 honors `Retry-After` (≤30 s), then a plain-language ConnectionError (VPN/proxy hint) |
| Bad collection alias (400/404 on subtree) | "The Dataverse URL or collection looks wrong (404). Check the Base URL and collection alias in Settings (Ctrl+,)." Try an empty alias for the whole repository |
| Discovery cap | None in practice: paging is driven by the server's `total_count`, and a short/empty page ends the crawl. `max_pages=100` is a runaway guard only; a genuine mismatch between collected and total is logged loudly |
| Guestbook required (400) | The approval window renders the dataset's guestbook (from `GET /api/guestbooks/{id}`, account details prefilled) and POSTs the answers; Dataverse returns `data.signedUrl`, which streams the ZIP. A missing required field is caught before sending; a server rejection shows its reason. No version retries, no "Base URL" hint |
| Large download | Quote warning ~5 GB in the approval dialog; `Accept: */*` avoids 406 |
| Logging | Every call via `applog.log_response` (method, URL, status, ms, summary); an expected refusal adds its reason after the raw line |

## Expected refusals (not bugs)

Dataverse answers some requests with a 4xx by design. `curation/client/refusals.py:_refusal()` classifies 400/401/403/404 responses by (path, status, body). A classified refusal is logged as EXPECTED — raw call and raw response kept verbatim, only the tone muted — while anything unclassified (500, a bad request, a wrong path) stays an ERROR.

| Refusal | Endpoint | Server condition | Code |
| --- | --- | --- | --- |
| 401 / 403 | `…/versions/:draft` | Dataverse grants draft access only inside a dataset's curation scope — an account outside it (even a collection admin) is not permitted | `draft_not_readable` |
| 404 | `…/versions/:draft` | The dataset has no draft version — the author is not working on an update | `no_draft_version` |
| 404 | `…/versions/:latest`, `:latest-published` | The dataset has no published version — deaccessioned versions are excluded unless `includeDeaccessioned=true` | `no_published_version` |
| 403 | `…/curationStatus` | Curation state exists only for datasets under curation, and only for accounts in their curation scope | `not_under_curation` |
| 404 | `…/versions/:latest-published/compare/:draft` | There is no published/draft pair to compare | `no_versions_to_compare` |

Reads that cannot exist are not sent. The Native API's dataset read answers with the version the account may see: the draft for a dataset under curation, the published version for a published one, and no version at all for a deaccessioned one. The dashboard reads each dataset once, with no version probe; only a row the Search payload marks as under curation is additionally probed at `:draft`. The queue row travels with the open request, so the detail view skips the curation status, the label history and the version comparison for a dataset with no draft. A refusal on one dataset marks that row (access: state, reason code, server message) and the batch continues.

## Version comparison

`MetadataWorker` calls `compare_versions(pid)` alongside the metadata fetch; `parse_version_compare` normalizes the `DatasetVersionDifference` shape. The "Changes since publication" card renders a Field | Previous (vX) | New (Draft) table plus a color-coded file list (added green, removed red, replaced amber, metadata blue) with a `vX → Draft · N change(s)` summary. First versions show "no published version to compare against"; identical drafts show "no changes".

## Curation record export (local)

`curation.curation_record.export_record()` composes the review's local outputs into one dated `curation-record/<YYYYMMDD-HHMMSS>/` folder beside the dataset's workspace folder: checks report (JSON + Markdown), depositor response, the curation timeline from `state.db`, per-finding dispositions, the sensitivity questionnaire, the recorded decision + curation label, and a `sha256sums.txt` manifest of the staged files — bound by `index.json` that hashes every artifact. The GUI exposes it as the header's Export record button; headless runs take `--export-record`. No server calls are involved: the record is a local audit bundle.

## See also

- [Configuration reference](configuration.md)
- [Checks reference](checks.md)
- [Glossary](glossary.md)
