# Dataverse integration

The app talks to Dataverse exclusively through the Native/Search API (no PostgreSQL/Solr access, unlike the review dashboard). All endpoints are relative to `config.dataverse.base_url`; token auth is via `X-Dataverse-key`.

## Authentication

- Header `X-Dataverse-key: <api_token>` on every request that needs auth (search with a token returns drafts; without, only published).
- Token is configured in `config.json` / **File → Settings…** — `PRESETS` includes `Borealis Demo — demo.borealisdata.ca → https://demo.borealisdata.ca`. On `401`, a selectable dialog directs the user to Settings; the token is never stored in SQLite.
- `GET /api/search` without a token still works for published datasets; drafts require the token.

## Endpoints used

| Purpose | Endpoint | Notes |
| --- | --- | --- |
| Version/capability check | `GET /api/info/version` | Verifies instance and adapts to API differences |
| Datasets discovery (fallback) | `GET /api/search?q=*&type=dataset&per_page=100&start=<n>&subtree=<alias>` | `start` is an offset (not `page`). Empty or `:root`/`root` = whole repository (no `subtree` param). Paginated `max_pages=10` (=1000 datasets) with dedup by `persistent_id` |
| Datasets in review (strict) | `GET /api/datasets/:persistentId/locks` or `GET /api/datasets/{id}/locks` | `lockType`/`reason` containing “review” (`locks_indicate_review`). Used by `list_datasets_in_review()` to filter the draft superset |
| Dataset metadata | `GET /api/datasets/:persistentId?persistentId=<doi>` | Citation/descriptive metadata for the detail view; `versionState` drives the header link |
| File inventory | `GET /api/datasets/:persistentId/versions/:draft` (fallback `:latest`, `:latest-published`) | Response `data.files` (or `data.datasetVersion.files`); `normalize_files` extracts `filename`, `directoryLabel`, `filesize`, `contentType`, `checksum{type,value}`. Draft→latest fallback handles published-only datasets |
| Bundle download | `GET /api/access/dataset/:persistentId?persistentId=<doi>&version=draft` (fallback `latest`) | Zipped bundle; **no** `Accept: application/json` (causes 406). Streamed `iter_content(1MB)` with progress |
| Single file download | `GET /api/access/datafile/:id` | Optional per-file fetching during triage |
| Lock listing | `GET /api/datasets/:persistentId/locks` | Confirms `IN_REVIEW` |
| Curation status | `GET /api/datasets/:persistentId/curationStatus?persistentId=<doi>` (`&includeHistory=true` for history) | Current label + `createTime` + `assigner` for a draft; `None` when unset/unavailable (4xx tolerated). Fallback when the bulk report is forbidden |
| Bulk curation report | `GET /api/datasets/listCurationStates` (superuser-only, `text/csv`) | One row per draft dataset; parsed by `parse_curation_states_csv` (PID from hyperlink, none-ish → unset). 401/403/404 → `None` → per-dataset fallback. Must send `Accept: text/csv` — the endpoint 406s on `application/json` |
| Compare versions | `GET /api/datasets/:persistentId/versions/:latest-published/compare/:draft?persistentId=<doi>` | Changed metadata/terms fields + added/removed/replaced files (`DatasetVersionDifference` shape); `None` when nothing comparable (4xx tolerated) |
| Version list | `GET /api/datasets/:persistentId/versions?persistentId=<doi>` | Per-version `versionState`/`createTime`/`releaseTime` for the timeline (`[]` on 4xx) |
| Lifecycle timestamps | `GET /api/datasets/:persistentId/timestamps` (numeric-id fallback) | `createTime`, `publicationTime`, `globalIdCreateTime`, draft `lastUpdateTime`, etc.; `{}` when unavailable |
| Notifications | `GET /api/notifications/all?limit=&offset=&inAppNotificationFormat=true` | Token-owner inbox with `sentTimestamp`; in-app items carry structured `datasetPersistentIdentifier`/`ownerDisplayName`, so `SUBMITTEDDS` notes are matched by PID with the collection name taken straight from the API — no text comparison |
| Allowed labels | `GET /api/datasets/:persistentId/allowedCurationLabels?persistentId=<doi>` | Comma-separated, **instance/collection-specific** set; empty when labels not configured |
| Set / delete label | `PUT` / `DELETE /api/datasets/:persistentId/curationStatus?...&label=<label>` | Available in `DataverseClient.set_curation_label/delete_curation_label` (not yet wired to UI buttons) |

## Curation labels (per-instance)
Allowed curation labels (`AllowedCurationLabels` setting) differ per Dataverse instance and even per collection, so the app never hard-codes them. Labels are pulled in bulk-first order on every dashboard refresh (`CrawlWorker`):

1. **Bulk report (one call):** `GET /api/datasets/listCurationStates` returns a superuser-only CSV with one row per draft dataset — title-as-hyperlink (carrying the persistent ID), draft creation/modification dates, assigned label (`""` never set; none-ish when set-then-removed), setter, and set time. `parse_curation_states_csv` matches rows to pulled datasets by persistent ID (title fallback) and unions the observed labels.
2. **Per-dataset fallback (drafts only):** non-superuser tokens get 403 on the report (the worker skips the call entirely once `/api/users/:me` says non-superuser), so the worker falls back to `curationStatus` per **draft/in-review dataset only** — published/deaccessioned rows have no readable status and are never attempted.
3. **Allowed set (one probe per first-level collection):** the set is shared across a first-level collection and everything under it, so `fetch_allowed_labels_shared` pulls `allowedCurationLabels` exactly once — preferring a draft/in-review dataset, because the endpoint requires `PublishDataset` permission (verified in `Datasets.java#getAllowedCurationLabels`) and curator tokens typically hold it only on datasets under curation. The `403 "You are not permitted…"` seen on published rows is that permission check, not a draft-vs-published rule. A retry only goes out while probes come back empty (bounded, 3 attempts). The **pure probe result** is stamped to `<workspace>/curation_labels.json` (via the worker's `allowedProbed` signal) the first time an alias is used and served from cache afterwards; a cache hit never re-stamps, so a cached entry can never freeze an unverified union in place. Only rounds with at least one HTTP 200 stamp — transport/server-error rounds (e.g. maintenance pages) retry next session instead of freezing an error `[]`. Labels no draft currently carries are unioned in (legacy report values kept), so the dropdown always shows the full allowed list, not just labels in use — but the union itself is never written to the probe slot.
4. The dashboard remembers the unioned set **with the pull**: `DashboardView._curation_labels` drives the "Curation label" filter combo and the Curation Label column, persisted in the per-pull `dashboard_cache.json` entry (probe-pure set in `curation_labels.json`, legacy bare-instance entries adopted once then re-probed) so switching collections restores the right set; a new top-level with no cache resets the combo until its single shared call completes.
5. Instances without labels configured (or 403 without curator rights) simply yield an empty set — the combo stays on "All labels" and the column is blank; nothing fails.

## Review-state discovery

The dashboard derives review state from Solr/PostgreSQL; the desktop app cannot. Discovery has two layers, and search docs need draft-aware interpretation (`search_item_state`):

- A dataset with a published version plus a new draft can surface as a RELEASED doc that still carries "Draft" in `publicationStatuses`. Draft/review markers anywhere in the doc win over the headline `versionState`, and when the same PID appears twice (published doc shadowing the draft doc) `list_draft_datasets` keeps the draft row — otherwise in-progress versions vanish from draft filtering.

### 1. Bulk discovery

**a) dvmeta crawler (when available).** [dataverse-metadata-crawler](https://github.com/scholarsportal/dataverse-metadata-crawler) (MIT, Python 3.10+, `dvmeta` package) crawls a collection subtree and returns dataset + datafile metadata for **draft** versions (`-v draft`). The installed package uses non-relative imports internally, so the app drives its stable CLI (`dvmeta/main.py` resolved via `importlib.util.find_spec("dvmeta.main").origin`) as a subprocess with `BASE_URL`/`API_KEY` env vars in a temp `cwd`, parsing `exported_files/json_files/ds_metadata_*.json` via `parse_ds_metadata_payload`. Available only in dev installs — `_dvmeta_available()` returns `False` when `sys.frozen` (PyInstaller).

**b) Paginated Search API fallback (always available).** `DataverseClient._search_fallback(subtree, per_page=100, start)` calls `GET /api/search` with `q=*&type=dataset` and the correct `start` offset; `list_draft_datasets(..., max_pages=10)` iterates `start=0,100,…,900`, deduping by `persistent_id` and logging `Search page N (start=…): M item(s), K new`. Verified on `https://demo.borealisdata.ca` (`v6.8.4-SP`, alias `dv`/`mcmaster`): 13 datasets fetched across 2 pages; empty alias = whole repository.

An informational banner in the UI now describes the source (“Search API (paginated)” vs “dvmeta draft crawl”) — see the progress label.

### 2. Per-dataset in-review confirmation (optional strict mode)

Drafts are a superset of in-review. `list_datasets_in_review()` is kept for API compatibility; the dashboard flow filters drafts by `dataset_in_review()` — `GET /api/datasets/:persistentId/locks` and `locks_indicate_review` (`"review" in lockType|reason`). The dashboard by default shows all drafts (`list_draft_datasets`) with `versionState` (`DRAFT`/`RELEASED`); the curator can filter by the **Status** combo (`All`/`DRAFT`/`Published`/`In Review`/`Deaccessioned`).

This removes dependence on `state=REVIEW` Search filter semantics, which vary by instance version.

## Download flow (approval-gated)

1. `DownloadManager.quote(pid)` — `get_file_inventory()` (draft→latest) → file count + total bytes; no download.
2. Approval dialog (`DownloadApprovalDialog`) shows the quote with a warning over the threshold; the curator explicitly approves.
3. `DataverseClient.download_dataset_zip(dest, version="draft", progress=)` streams the bundle to `workspace/downloads/<sanitized-pid>/_bundle.zip.part`, then atomically renames to `_bundle.zip` (a killed run never leaves a truncated bundle behind), trying `version=draft` then `latest`, then no version param. Each version attempt retries 3× on network/timeout/throttle errors.
4. Atomic unzip into `workspace/downloads/<sanitized-pid>/files/` (extract to `files.new/`, verify, swap — a corrupt bundle preserves the previous stage) with zip-slip guard (containment via `is_relative_to`, symlinks refused); `verify()` rehashes each staged file via `DownloadManager._hash_file` and compares against the inventory checksum (`md5`/`sha1` normalized to lower); mismatches are surfaced. Inventory paths are containment-checked too, so `..`/absolute entries can never redirect reads/writes outside the workspace.
5. Staged files become the input to `engine/runner.py:run_report` (`CheckWorker`); pre-download inventory already populates the file table via `DatasetDetailView._populate_from_inventory()`.

The detail header link is version-aware after metadata loads: `dataset.xhtml?persistentId=…&version=DRAFT` for drafts, plain otherwise (DOIs not enabled for drafts).

## Error handling, retry and limits

- `_get_json`/`_get_text` retry 3× on `ConnectionError`/`ChunkedEncodingError`/`Timeout`/`ConnectionResetError` (WinError 10054 “remote host forcibly closed”) with `1.5*(attempt+1)` s backoff, plus 429/503 honoring `Retry-After` (capped 30 s), then raise a user-friendly `ConnectionError` suggesting VPN/proxy/reachability checks. All calls are logged via `applog.log_response` (method, URL, status, ms, summary — e.g. `12 item(s)` for search).
- Search errors `400`/`404` for `subtree` surface as “Collection ‘…’ not found … try an empty alias for the whole repository”.
- `list_draft_datasets` caps at `max_pages=10` (1000 datasets) and logs an explicit TRUNCATED error when every page comes back full — narrow the collection and refresh.
- Download uses `Accept: */*` not `application/json`; 406 avoided. Large-dataset quote warning at ~5 GB in the approval dialog.
- Partial failures (checksum mismatch, interrupted download) leave the previous stage intact: atomic swap on extract, `.part` bundle naming. All warnings/errors use selectable dialogs (`ui/dialogs.py`) so tracebacks can be copied.

## Verification (live)

- `https://demo.borealisdata.ca` `GET /api/info/version` → Borealis; `GET /api/search?q=*&type=dataset&per_page=100&start=0&subtree=mcmaster` → 10 + 3 = 13 datasets (paginated).
- `GET /api/datasets/:persistentId?persistentId=doi:10.5072/FK2/UM87WJ` → citation title OK; `GET /api/datasets/:persistentId/versions/:draftId` → 23 files in publish state (empty for drafts without token); `GET /api/access/dataset/:persistentId?version=draft` → 358477 bytes streamed, unzip OK.
- Empty collection alias and `:root` correctly return the whole repository via Search fallback.

## Collection alias note

Borealis demo root alias is `dv` (not `borealis`); the app treats empty alias as “whole repository” (no `subtree` param) and special-cases `root`/` :root` the same way, matching the Native API behavior observed in live tests.

## Version comparison (draft under review vs published)

When a dataset under review has a previously published version, the detail view shows what changed (`ui/dataset_detail.py` “Changes since publication” card, top of the right column):

1. `MetadataWorker` calls `DataverseClient.compare_versions(pid)` → `GET /api/datasets/:persistentId/versions/:latest-published/compare/:draft` alongside the metadata/inventory/curation fetch.
2. `parse_version_compare` normalizes the `DatasetVersionDifference` shape: `oldVersion`/`newVersion` headers, `metadataChanges` per block (`blockName` + `fieldName`/`oldValue`/`newValue`), `TermsOfAccess`, and `filesAdded`/`filesRemoved`/`filesReplaced`/`fileChanges`.
3. The card renders a Field | Previous (vX) | New (Draft) table (values truncated with full-text tooltips) plus a color-coded file list (added green, removed red, replaced amber, file-metadata changes blue), with a `vX → Draft · N change(s)` summary. First versions (compare 4xx) show “no published version to compare against”; identical drafts show “no changes”.
