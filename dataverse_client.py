"""Dataverse Native API client with paginated Search-API discovery.

Discovery paginates the native Search API (draft-aware dedup) and enriches
rows with live inventory sums; in-review status is confirmed per dataset
via the locks endpoint. See docs/html/dataverse-integration.html for
endpoints and auth.

All requests/responses are recorded in an in-memory log (see applog.py)
which the UI can display.
"""

import hashlib
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests

from applog import get_app_log

_STREAM_CHUNK = 1 << 20

# Canonical state token for "locked for review". This is a *data* contract
# shared by the client, the engine and the dashboard cache — not interface
# copy, so it is deliberately not translated. The GUI renders it through its
# own display-state mapping (``dashboard.display_state.review``).
STATE_IN_REVIEW = "In Review"

# Network failures worth one retry cycle (timeouts included: a stalled
# bundle stream otherwise restarts from zero with no second chance).
_RETRYABLE_NETWORK = (
    requests.exceptions.ConnectionError,
    requests.exceptions.ChunkedEncodingError,
    requests.exceptions.Timeout,
    ConnectionResetError,
)

# HTTP statuses worth retrying (throttle / transient overload).
_RETRYABLE_STATUS = (429, 503)


class _RetryOriginal(Exception):
    """Internal: throttled original-format download should retry the loop."""


class DownloadCancelled(Exception):
    """Raised from a streaming loop when the curator cancels the download.

    Deliberately not an HTTP/network error: the retry loops must never
    catch or replay it — it propagates straight through DownloadManager
    to the worker, which turns it into the `cancelled` signal.
    """


class GuestbookRequired(Exception):
    """The Access API refused the bundle because a guestbook must be answered.

    Dataverse answers HTTP 400 ("You may not download this file without the
    required Guestbook response ..."), which must not be mistaken for a
    missing version: no retry or version fallback can succeed until the
    guestbook is answered. Deliberately not an HTTPError so the streaming
    retry loop does not swallow it as an unavailable version.
    """


def _error_message(response) -> str:
    """Best-effort Dataverse error message from a JSON error response."""
    try:
        payload = response.json()
    except Exception:
        payload = None
    if isinstance(payload, dict):
        message = payload.get("message")
        if message:
            return str(message).strip()
    try:
        return (response.text or "").strip()[:400]
    except Exception:
        return ""


def _throttle_delay(exc: requests.HTTPError) -> float | None:
    """Retry-After seconds for a retryable HTTP error, else None.

    Returns 0.0 when the status is retryable but carries no usable
    Retry-After header (caller falls back to linear backoff).
    """
    resp = getattr(exc, "response", None)
    if resp is None or resp.status_code not in _RETRYABLE_STATUS:
        return None
    try:
        return max(0.0, min(30.0, float(resp.headers.get("Retry-After", ""))))
    except (TypeError, ValueError):
        return 0.0


def _field_value(dataset_version: dict[str, Any], type_name: str) -> Any:
    fields = (
        dataset_version.get("metadataBlocks", {})
        .get("citation", {})
        .get("fields", [])
    )
    for field in fields:
        if field.get("typeName") == type_name:
            return field.get("value")
    return None


def extract_title(dataset_version: dict[str, Any]) -> str:
    value = _field_value(dataset_version, "title")
    return value if isinstance(value, str) else ""


def _extract_contact(dataset_version: dict[str, Any]) -> str:
    value = _field_value(dataset_version, "datasetContact")
    if isinstance(value, list) and value:
        first = value[0] or {}
        name = first.get("datasetContactName", {}).get("value", "") if isinstance(first.get("datasetContactName"), dict) else first.get("datasetContactName", "")
        email = first.get("datasetContactEmail", {}).get("value", "") if isinstance(first.get("datasetContactEmail"), dict) else first.get("datasetContactEmail", "")
        if name and email:
            return f"{name} <{email}>"
        return name or email or ""
    if isinstance(value, str):
        return value
    return ""


def normalize_files(dataset_version: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize a datasetVersion.files array into flat file records."""
    records: list[dict[str, Any]] = []
    for entry in dataset_version.get("files", []):
        data_file = entry.get("dataFile", {}) or {}
        checksum_type = ""
        checksum_value = ""
        checksum = data_file.get("checksum")
        if isinstance(checksum, dict):
            checksum_type = str(checksum.get("type", "")).lower()
            checksum_value = checksum.get("value", "")
        else:
            for candidate in ("sha1", "md5"):
                if data_file.get(candidate):
                    checksum_type = candidate
                    checksum_value = data_file[candidate]
                    break
        directory = entry.get("directoryLabel") or ""
        filename = entry.get("filename") or data_file.get("filename") or ""
        restrictions = extract_file_restrictions(entry, data_file)
        # Tabular ingest products (.tab): field names verified against
        # JsonPrinter (UNF is uppercase there). The UNF is the stable
        # fingerprint when the server regenerates .tab bytes.
        unf = (
            data_file.get("UNF") or data_file.get("unf")
            or entry.get("UNF") or entry.get("unf") or ""
        )
        # Tabular ingest status/errors surfaced from the API (when present).
        ingest_status = str(
            data_file.get("ingestStatus") or entry.get("ingestStatus") or ""
        )
        ingest_error = str(
            data_file.get("ingestErrorMessage")
            or data_file.get("ingestError")
            or entry.get("ingestErrorMessage")
            or entry.get("ingestError")
            or ""
        )
        # Access restrictions (restricted files, embargo, retention).
        restricted = bool(
            entry.get("restricted", data_file.get("restricted", False))
        )
        try:
            original_size = int(
                data_file.get("originalFileSize") or entry.get("originalFileSize") or 0
            )
        except (TypeError, ValueError):
            original_size = 0
        try:
            size_bytes = int(data_file.get("filesize") or 0)
        except (TypeError, ValueError):
            size_bytes = 0
        records.append(
            {
                "id": str(data_file.get("id", "")),
                "path": f"{directory}/{filename}" if directory else filename,
                "size_bytes": size_bytes,
                "mime_type": data_file.get("contentType") or "",
                "checksum_type": checksum_type.lower(),
                "checksum_value": checksum_value,
                "embargo_date": restrictions["embargo_date"],
                "retention": restrictions["retention"],
                "restricted": restricted,
                "tabular": bool(data_file.get("tabularData", entry.get("tabularData", False))),
                "unf": str(unf or ""),
                "ingest_status": ingest_status,
                "ingest_error": ingest_error,
                "original_format": str(
                    data_file.get("originalFileFormat") or entry.get("originalFileFormat") or ""
                ),
                "original_name": str(
                    data_file.get("originalFileName") or entry.get("originalFileName") or ""
                ),
                "original_size": original_size,
            }
        )
    return records


_DATE_RE = None  # lazy compiled in _scan_restriction_dates


def _scan_restriction_dates(obj: Any, depth: int = 0) -> dict[str, str]:
    """Collect {dotted.key.path: YYYY-MM-DD} for embargo/retention-ish keys."""
    import re

    global _DATE_RE
    if _DATE_RE is None:
        _DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
    found: dict[str, str] = {}
    if isinstance(obj, dict):
        items = obj.items()
    elif isinstance(obj, list) and depth < 2:
        for value in obj:
            found.update(_scan_restriction_dates(value, depth + 1))
        return found
    else:
        return found
    for key, value in items:
        key_lower = str(key).lower()
        interesting = (
            "embargo" in key_lower or "retention" in key_lower or "dateavailable" in key_lower
        )
        if isinstance(value, str):
            if interesting:
                match = _DATE_RE.search(value)
                if match:
                    found[key_lower] = match.group(0)
        elif isinstance(value, (dict, list)) and depth < 2:
            for sub_key, sub_val in _scan_restriction_dates(value, depth + 1).items():
                found[f"{key_lower}.{sub_key}"] = sub_val
    return found


def extract_file_restrictions(entry: dict[str, Any], data_file: dict[str, Any]) -> dict[str, str]:
    """Pull embargo/retention dates out of a file-version entry.

    Field names vary by Dataverse version, so both the entry-level and
    dataFile-level dicts are scanned (two levels deep) for embargo /
    retention / dateAvailable keys holding a YYYY-MM-DD date. Returns
    {"embargo_date": ..., "retention": ...} with "" when absent.
    """
    found: dict[str, str] = {}
    for source in (entry or {}, data_file or {}):
        if isinstance(source, dict):
            for path, date in _scan_restriction_dates(source).items():
                found.setdefault(path, date)
    embargo_date = ""
    for path, date in found.items():
        if "embargo" in path or path == "dateavailable":
            embargo_date = date
            break
    retention = ""
    for path, date in found.items():
        if "retention" in path:
            retention = date
            break
    return {"embargo_date": embargo_date, "retention": retention}


def parse_timestamps(payload: dict[str, Any]) -> dict[str, str]:
    """Normalize a /timestamps response data object to known date fields."""
    data = (payload or {}).get("data")
    if not isinstance(data, dict):
        return {}
    keys = (
        "createTime",
        "publicationTime",
        "lastMetadataExportTime",
        "lastMajorVersionReleaseTime",
        "lastUpdateTime",
        "lastIndexTime",
        "lastPermissionUpdateTime",
        "globalIdCreateTime",
    )
    return {key: str(data.get(key) or "") for key in keys}


# Notification types that mark a dataset submitted for review (exact enum
# values from UserNotification.Type — verified against source).
REVIEW_SUBMIT_TYPES = frozenset({"SUBMITTEDDS"})


def note_review_submission(pid: str, note: Any) -> dict[str, str] | None:
    """Structured review-submission match (in-app notification format).

    Matches when the note's type is a review-submission type AND its
    datasetPersistentIdentifier equals this dataset's persistent ID
    (case-insensitive). No text comparison anywhere: identity comes from
    the structured fields, and the collection name from ownerDisplayName
    as pulled from the API. Returns {time, dataverse, dataset, requestor}
    or None.
    """
    if not isinstance(note, dict):
        return None
    if str(note.get("type") or "").upper() not in REVIEW_SUBMIT_TYPES:
        return None
    note_pid = str(note.get("datasetPersistentIdentifier") or "").strip()
    wanted = (pid or "").strip()
    if not note_pid or not wanted or note_pid.casefold() != wanted.casefold():
        return None
    requestor = " ".join(
        part
        for part in (
            str(note.get("requestorFirstName") or "").strip(),
            str(note.get("requestorLastName") or "").strip(),
        )
        if part
    )
    return {
        "time": str(note.get("sentTimestamp") or ""),
        "dataverse": str(note.get("ownerDisplayName") or "").strip(),
        "dataset": str(note.get("datasetDisplayName") or "").strip(),
        "requestor": requestor,
    }


def locks_indicate_review(locks: list[dict[str, Any]]) -> bool:
    import re as _re

    # Match "review" (InReview, in_review, in-review, "In Review") but not
    # "Preview": the 'r' must not be preceded by 'p' (case-insensitive).
    _review_re = _re.compile(r"(?<!p)review", _re.IGNORECASE)
    for lock in locks:
        if not isinstance(lock, dict):
            continue
        # Prefer lockType; fall back to reason only when lockType is empty.
        kind = lock.get("lockType") or lock.get("reason", "")
        if kind and _review_re.search(str(kind)):
            return True
    return False


def search_item_state(item: dict[str, Any]) -> tuple:
    """Derive (state, has_draft) from a Search API dataset doc.

    A dataset with a published version plus a new draft version can surface
    as a RELEASED doc that still carries "Draft" in publicationStatuses —
    without this, the in-progress draft is invisible to draft filtering.
    Draft/review markers anywhere win over the headline versionState.
    """
    statuses = [str(s or "") for s in (item.get("publicationStatuses") or [])]
    lowered = [s.lower() for s in statuses]
    vs = str(item.get("versionState") or "")
    has_draft = vs.upper() == "DRAFT" or any(
        "draft" in s or "review" in s for s in lowered
    )
    if any("review" in s for s in lowered):
        return STATE_IN_REVIEW, True
    if has_draft:
        return "DRAFT", True
    if vs:
        return vs, False
    if statuses:
        return statuses[0], False
    return "", False


def parse_allowed_labels(data: Any) -> list[str]:
    """Parse the allowedCurationLabels `data` payload.

    Shapes seen in the wild: a comma-separated string, a JSON array of
    strings, or (Dataverse 6.8) an envelope object carrying either under
    "message". All shapes yield the same deduped list — previously the
    array shape was silently dropped to [], and the envelope shape with it
    (every probe against such servers returned [] while the log still said
    "received", so the allowed set NEVER populated and only in-use labels
    ever showed).
    """
    seen: list[str] = []
    if isinstance(data, dict):
        data = data.get("message", "")
    if isinstance(data, str):
        parts = data.split(",")
    elif isinstance(data, (list, tuple)):
        parts = list(data)
    else:
        return []
    for part in parts:
        label = str(part).strip() if isinstance(part, str) else str(part or "").strip()
        if label and label not in seen:
            seen.append(label)
    return seen


def top_level_collection(collection: str) -> str:
    """First path segment of a collection alias.

    Allowed curation labels are shared across a first-level collection and
    everything under it ("mcmaster/x" uses "mcmaster"'s list), so the
    allowed-set cache is keyed by this segment, not the full alias.
    "" means the whole repository.
    """
    try:
        seg = (collection or "").strip().strip("/")
    except Exception:
        return ""
    if not seg:
        return ""
    return seg.split("/")[0].strip()


def is_draft_dataset(ds: Any) -> bool:
    """Check whether a crawl row is under curation (draft or in review).

    Curation labels/status exist only for datasets under curation — the
    shared predicate for per-draft label reads and probe ordering, so
    published/deaccessioned rows are never probed.
    """
    try:
        if not isinstance(ds, dict):
            return False
        state = str(ds.get("state") or "").upper()
        return state == "DRAFT" or "REVIEW" in state or bool(ds.get("has_draft"))
    except Exception:
        return False


def _version_files_data(data: Any) -> dict[str, Any]:
    """Extract the files-carrying version dict from a version `data` payload.

    Dataverse versions API puts files at data.files (not
    data.datasetVersion.files); metadata reads put them under
    data.datasetVersion or data.latestVersion.
    """
    try:
        if not isinstance(data, dict):
            return {}
        # Prefer version docs that actually carry files; fall back through
        # the known shapes in order (mirrors get_file_inventory history).
        for key in ("datasetVersion", "latestVersion"):
            try:
                candidate = data.get(key)
            except Exception:
                candidate = None
            if isinstance(candidate, dict) and candidate.get("files"):
                return candidate
        try:
            dataset_version = data.get("datasetVersion")
        except Exception:
            dataset_version = None
        if isinstance(dataset_version, dict):
            return dataset_version
        try:
            data_files = data.get("files")
        except Exception:
            data_files = None
        if data_files:
            return {"files": data_files if isinstance(data_files, list) else []}
        try:
            latest = data.get("latestVersion")
        except Exception:
            latest = None
        if isinstance(latest, dict):
            return latest
        return {}
    except Exception:
        return {}


def _version_last_update(data: Any) -> str:
    """Best-effort version ``lastUpdateTime`` from a version payload (dv-5eg).

    Used to tell whether the depositor touched the draft since a
    revisions-requested decision; "" when the server did not say.
    """
    try:
        version_data = _version_files_data(data)
        if isinstance(version_data, dict):
            ts = str(version_data.get("lastUpdateTime") or "")
            if ts:
                return ts
        if isinstance(data, dict):
            return str(data.get("lastUpdateTime") or "")
    except Exception:
        pass
    return ""


def _summarize_version_data(data: Any) -> tuple[list[dict[str, Any]], str, str, bool]:
    """Best-effort (files, depositor, versionState, files_known) from a payload.

    Never raises. `files_known` is False when the payload carried no
    `files` key at all — that means "the server did not tell us", which
    is different from "this dataset has zero files" and must not be
    rendered as a size of 0.
    """
    try:
        version_data = _version_files_data(data)
        files = normalize_files(version_data)
    except Exception:
        files = []
    depositor = ""
    state = ""
    files_known = False
    try:
        if isinstance(version_data, dict):
            if "files" in version_data:
                files_known = True
            dep = _field_value(version_data, "depositor")
            if isinstance(dep, str):
                depositor = dep
            if not depositor and isinstance(data, dict):
                depositor = str(data.get("depositorName") or "")
            state = str(version_data.get("versionState") or "")
        if not state and isinstance(data, dict):
            # Flat version shape: versionState sits beside files.
            state = str(data.get("versionState") or "")
        if not files_known and isinstance(data, dict) and "files" in data:
            files_known = True
    except Exception:
        pass
    return files, depositor, state, files_known


# Authenticated-identity cache: (base_url, token fingerprint) -> /api/users/:me data.
# Keyed by a SHA-256 fingerprint, never the token itself. Successes only —
# a failure (bad token, network) returns None and retries next time.
# Collection roles share the lock with a (base_url, fingerprint, alias) key.
_ME_CACHE: dict[tuple, dict[str, Any]] = {}
_ROLE_CACHE: dict[tuple, list[str]] = {}
_ME_LOCK = threading.Lock()


def _me_cache_key(base_url: str, api_token: str) -> tuple:
    try:
        base = (base_url or "").rstrip("/").lower()
    except Exception:
        base = ""
    try:
        fp = hashlib.sha256((api_token or "").encode("utf-8")).hexdigest()[:16]
    except Exception:
        fp = ""
    return (base, fp)


# In-process allowed-labels cache: (base_url, top_level) -> labels.
# The endpoint needs PublishDataset permission and the list is identical
# for every dataset under a first-level collection, so one network call
# per top-level collection per process is enough; [] is a valid negative
# entry (none configured) — None means "unknown, may fetch".
_ALLOWED_LABELS_CACHE: dict[tuple, list[str]] = {}
_ALLOWED_LABELS_LOCK = threading.Lock()

_ALLOWED_LABELS_FILE = "curation_labels.json"


def allowed_labels_cache_key(base_url: str, collection: str) -> tuple:
    """Memory-cache key: normalized (instance, first-level collection)."""
    try:
        base = (base_url or "").rstrip("/").lower()
    except Exception:
        base = ""
    return (base, top_level_collection(collection or "").lower())


def get_cached_allowed_labels(base_url: str, collection: str) -> list[str] | None:
    """Return cached allowed labels, or None when unknown (caller may fetch once)."""
    try:
        with _ALLOWED_LABELS_LOCK:
            hit = _ALLOWED_LABELS_CACHE.get(allowed_labels_cache_key(base_url, collection))
        return list(hit) if hit is not None else None
    except Exception:
        return None


def set_cached_allowed_labels(base_url: str, collection: str, labels: list[str]) -> None:
    """Store allowed labels (including []) for a top-level collection."""
    try:
        clean = [str(lbl).strip() for lbl in (labels or []) if str(lbl).strip()]
        with _ALLOWED_LABELS_LOCK:
            _ALLOWED_LABELS_CACHE[allowed_labels_cache_key(base_url, collection)] = clean
    except Exception:
        pass


def _allowed_labels_disk_key(base_url: str, collection: str) -> str:
    try:
        base = (base_url or "").rstrip("/").lower()
    except Exception:
        base = ""
    top = top_level_collection(collection or "") or "whole repository"
    return f"{base}|{top}"


def read_allowed_labels_cache(
    workspace, base_url: str, collection: str
) -> list[str] | None:
    """Read allowed labels from disk for a top-level collection (None = unknown).

    Only slots stamped "probed" at format v2 by a real discovery round
    count as hits: the allowed set is probed exactly once per collection
    (the first time its alias is used) and served from cache afterwards.
    Older slots — unstamped, or v1 stamps written from the filter union
    rather than a probe — read as unknown so they get one fresh probe,
    then carry the v2 stamp going forward. A hit warms the memory cache.
    Falls back to the legacy bare-instance key written by older versions.
    Never raises.
    """
    try:
        path = Path(workspace) / _ALLOWED_LABELS_FILE
        if not path.exists():
            return None
        import json as _json

        raw = _json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None
        entry = raw.get(_allowed_labels_disk_key(base_url, collection))
        if not isinstance(entry, dict):
            # Legacy key: bare instance URL (pre-top-level cache).
            try:
                legacy = (base_url or "").rstrip("/").lower()
                entry = raw.get(legacy)
            except Exception:
                entry = None
        if not isinstance(entry, dict):
            return None
        if entry.get("probed") is not True or entry.get("v") != 2:
            # Unstamped, or v1-stamped from the filter union rather than a
            # probe: not a hit — one fresh discovery round happens, then
            # the slot carries the v2 stamp.
            return None
        labels = entry.get("labels", [])
        if not isinstance(labels, list):
            return None
        clean = [str(lbl) for lbl in labels if str(lbl).strip()]
        set_cached_allowed_labels(base_url, collection, clean)
        return clean
    except Exception:
        return None


def write_allowed_labels_cache(
    workspace, base_url: str, collection: str, labels: list[str]
) -> None:
    """Persist allowed labels for a top-level collection (best-effort).

    Stamps the slot v2/"probed": this write records the one discovery
    round for the collection, so later sessions serve the cache with zero
    calls. Callers must pass PURE probe results here — never the filter
    union (in-use labels ride in the dashboard cache instead).
    """
    try:
        import json as _json

        path = Path(workspace) / _ALLOWED_LABELS_FILE
        try:
            raw = _json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except Exception:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        try:
            coll = (collection or "").strip()
        except Exception:
            coll = ""
        raw[_allowed_labels_disk_key(base_url, collection)] = {
            "labels": [str(lbl) for lbl in (labels or []) if str(lbl).strip()],
            "collection": coll,
            "probed": True,
            "v": 2,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json.dumps(raw, indent=2), encoding="utf-8")
        set_cached_allowed_labels(base_url, collection, labels or [])
    except Exception:
        pass


# -- metadata blocks (field catalog broadcast by Dataverse) -------------------
# The Review-configuration page lists every metadata field the connected
# Dataverse knows about (block + field + display name), so curators can mark
# fields required / optional / unchecked. Endpoints:
#   GET /api/metadatablocks            -> [{id, name, displayName}, ...]
#   GET /api/metadatablocks/{name}     -> {metadataFields: {field: {...}}}
# Cached per instance on disk (metadatablocks_cache.json); never raises.

_METADATABLOCKS_FILE = "metadatablocks_cache.json"

_METADATABLOCKS_MEMO: dict[tuple, list[dict[str, Any]]] = {}
_METADATABLOCKS_LOCK = threading.Lock()


def _metadatablocks_disk_key(base_url: str) -> str:
    try:
        return (base_url or "").rstrip("/").lower()
    except Exception:
        return ""


def parse_metadatablock_names(payload: dict[str, Any]) -> list[str]:
    """Block names from a GET /api/metadatablocks payload. Never raises."""
    try:
        data = (payload or {}).get("data")
        items = data if isinstance(data, list) else []
        out = []
        for entry in items:
            if isinstance(entry, dict) and str(entry.get("name") or "").strip():
                out.append(str(entry["name"]).strip())
        return out
    except Exception:
        return []


def parse_metadatablock_display_names(payload: dict[str, Any]) -> dict[str, str]:
    """{block name: display name} from a GET /api/metadatablocks payload."""
    out: dict[str, str] = {}
    try:
        data = (payload or {}).get("data")
        items = data if isinstance(data, list) else []
        for entry in items:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "").strip()
            if not name:
                continue
            out[name] = str(entry.get("displayName") or name).strip() or name
    except Exception:
        pass
    return out


def parse_metadatablock_fields(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return [{block, field, label, parent?, ...}] from a metadatablocks payload.

    Values are mostly strings, but ``is_subfield`` is a bool — hence Any.
    Field map lives under data.metadataFields on older servers and under
    data.fields (dict keyed by field name, or a list) on newer ones
    (verified on 6.8: {"name": ..., "fields": {"geographicCoverage":
    {"name": ..., "displayName": ...}}}). Missing/unknown shapes yield [].
    """
    out: list[dict[str, Any]] = []
    try:
        data = (payload or {}).get("data") or {}
        block = str(data.get("name") or "").strip()
        fields = data.get("metadataFields")
        if fields is None:
            fields = data.get("fields")
        fields = fields or {}
        if isinstance(fields, dict):
            for fname, spec in fields.items():
                if not isinstance(fname, str) or not fname.strip():
                    continue
                label = fname.strip()
                if isinstance(spec, dict):
                    label = str(spec.get("displayName") or spec.get("displayname") or label)
                block_name = block or "citation"
                out.append({
                    "block": block_name, "field": fname.strip(),
                    "label": label.strip() or fname.strip(),
                })
                if isinstance(spec, dict):
                    sub = spec.get("childFields") or spec.get("subFields") or spec.get("fields")
                    if isinstance(sub, dict):
                        parent_label = label.strip() or fname.strip()
                        for sname, sspec in sub.items():
                            if not isinstance(sname, str) or not sname.strip():
                                continue
                            slabel = sname.strip()
                            if isinstance(sspec, dict):
                                slabel = str(sspec.get("title") or sspec.get("displayName")
                                             or sspec.get("displayname") or slabel)
                            out.append({
                                "block": block_name,
                                "field": f"{fname.strip()}.{sname.strip()}",
                                "label": slabel.strip() or sname.strip(),
                                "parent": fname.strip(),
                                "parent_label": parent_label,
                                "is_subfield": True,
                            })
        elif isinstance(fields, list):
            for spec in fields:
                if not isinstance(spec, dict):
                    continue
                fname = str(spec.get("name") or spec.get("typeName") or "").strip()
                if not fname:
                    continue
                label = str(spec.get("displayName") or spec.get("displayname") or fname)
                block_name = block or "citation"
                out.append({"block": block_name, "field": fname, "label": label})
                sub = spec.get("childFields") or spec.get("subFields") or spec.get("fields")
                if isinstance(sub, dict):
                    parent_label = label.strip() or fname
                    for sname, sspec in sub.items():
                        if not isinstance(sname, str) or not sname.strip():
                            continue
                        slabel = sname.strip()
                        if isinstance(sspec, dict):
                            slabel = str(sspec.get("title") or sspec.get("displayName")
                                         or sspec.get("displayname") or slabel)
                        out.append({
                            "block": block_name,
                            "field": f"{fname}.{sname.strip()}",
                            "label": slabel.strip() or sname.strip(),
                            "parent": fname,
                            "parent_label": parent_label,
                            "is_subfield": True,
                        })
    except Exception:
        pass
    return out


def get_cached_metadata_fields(base_url: str) -> list[dict[str, Any]] | None:
    try:
        with _METADATABLOCKS_LOCK:
            hit = _METADATABLOCKS_MEMO.get((_metadatablocks_disk_key(base_url),))
        return [dict(f) for f in hit] if hit is not None else None
    except Exception:
        return None


def set_cached_metadata_fields(base_url: str, fields: list[dict[str, Any]]) -> None:
    try:
        clean = [dict(f) for f in (fields or []) if isinstance(f, dict) and f.get("field")]
        with _METADATABLOCKS_LOCK:
            _METADATABLOCKS_MEMO[(_metadatablocks_disk_key(base_url),)] = clean
    except Exception:
        pass


def read_metadata_fields_cache(workspace, base_url: str) -> list[dict[str, Any]] | None:
    """Field catalog from disk for an instance (None = unknown). Never raises."""
    try:
        path = Path(workspace) / _METADATABLOCKS_FILE
        if not path.exists():
            return None
        import json as _json

        raw = _json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None
        entry = raw.get(_metadatablocks_disk_key(base_url))
        if not isinstance(entry, dict):
            return None
        fields = entry.get("fields", [])
        if not isinstance(fields, list):
            return None
        clean = [f for f in fields if isinstance(f, dict) and f.get("field")]
        set_cached_metadata_fields(base_url, clean)
        return clean
    except Exception:
        return None


def write_metadata_fields_cache(workspace, base_url: str, fields: list[dict[str, str]]) -> None:
    """Persist an instance's field catalog (best-effort)."""
    try:
        import json as _json

        path = Path(workspace) / _METADATABLOCKS_FILE
        try:
            raw = _json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except Exception:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        raw[_metadatablocks_disk_key(base_url)] = {
            "fields": [dict(f) for f in (fields or []) if isinstance(f, dict) and f.get("field")],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json.dumps(raw, indent=2), encoding="utf-8")
        set_cached_metadata_fields(base_url, fields or [])
    except Exception:
        pass


def parse_curation_status(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Parse a curationStatus response into {label, time, assigner} or None.

    Handles both the single-object form and the includeHistory=true array
    form (newest entry wins). Returns None when no label is assigned.
    """
    data = (payload or {}).get("data")
    if isinstance(data, list):
        if not data:
            return None
        # History is chronological; the current label is the last entry
        data = data[-1]
    if not isinstance(data, dict):
        return None
    label = str(data.get("label") or "").strip()
    if not label:
        return None
    return {
        "label": label,
        "time": str(data.get("createTime") or ""),
        "assigner": str(data.get("assigner") or data.get("user") or ""),
    }


# Values in the listCurationStates CSV that mean "no label assigned":
# "" (never set), "null"/"none"/"<none>" (bundle "dataset.curationstatus.none").
_CURATION_NONE_VALUES = frozenset({"", "null", "none", "<none>"})


def _clean_curation_value(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in _CURATION_NONE_VALUES else text


def parse_curation_states_csv(text: str) -> list[dict[str, Any]]:
    """Parse the superuser listCurationStates CSV report.

    Columns (by position — header labels are localized bundle strings):
    0 title-as-hyperlink formula =HYPERLINK("...persistentId=<PID>...","<title>"),
    1 draft creation date, 2 draft modification date, 3 assigned label
    ("" never set; none-ish when set-then-removed), 4 setter, 5 set time,
    6+ role-assignee columns (ignored).
    Returns [{persistent_id, title, creation_date, modification_date,
    label, label_time, assigner}]. Rows without an extractable PID are kept
    with persistent_id="" so callers can fall back to title matching.
    """
    import csv
    import io
    import re

    rows: list[dict[str, Any]] = []
    try:
        reader = csv.reader(io.StringIO(text or ""))
    except Exception:
        return rows
    link_re = re.compile(r'^=HYPERLINK\("(.+?)","(.*)"\)$', re.DOTALL)
    pid_re = re.compile(r"persistentId=([^\"]+)")
    for cells in reader:
        if not cells:
            continue
        first = (cells[0] or "").strip()
        pid = ""
        title = ""
        m = link_re.match(first)
        if m:
            url, title = m.group(1), m.group(2)
            pm = pid_re.search(url)
            if pm:
                pid = pm.group(1).strip()
            title = title.strip()
        else:
            # Header row or unexpected shape — keep the raw text as a
            # title candidate only if it cannot be the localized header.
            title = first
        def _cell(i: int, _cells=cells) -> str:
            return _cells[i].strip() if len(_cells) > i else ""
        label = _clean_curation_value(_cell(3))
        rows.append(
            {
                "persistent_id": pid,
                "title": title,
                "creation_date": _cell(1),
                "modification_date": _cell(2),
                "label": label,
                # When no label is assigned the setter/time cells carry the
                # same none-ish bundle value — normalize those too.
                "label_time": _clean_curation_value(_cell(5)) if label else "",
                "assigner": _clean_curation_value(_cell(4)) if label else "",
            }
        )
    # Drop only the leading header row (no PID and no hyperlink). Other
    # PID-less rows are kept for title fallback per the docstring — a
    # format change to plain-title cells must not silently vanish.
    if rows and not rows[0]["persistent_id"] and not rows[0]["title"].startswith("=HYPERLINK"):
        rows = rows[1:]
    rows = [r for r in rows if r["persistent_id"] or r["title"]]
    return rows


def _summarize_file_entry(entry: Any) -> dict[str, str]:
    """Condense a compare-API file object to {name, path, id, kind}."""
    if not isinstance(entry, dict):
        return {"name": str(entry or ""), "path": "", "id": "", "kind": ""}
    name = str(entry.get("fileName") or entry.get("label") or entry.get("name") or "")
    path = str(entry.get("filePath") or entry.get("directoryLabel") or "")
    fid = str(entry.get("fileId") or entry.get("id") or "")
    kind = str(entry.get("type") or entry.get("contentType") or "")
    return {"name": name, "path": path, "id": fid, "kind": kind}


def parse_version_compare(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Parse a versions/compare response into a normalized diff.

    Mirrors DatasetVersionDifference.compareVersionsAsJson: oldVersion /
    newVersion headers, metadataChanges (per block), TermsOfAccess, and
    filesAdded / filesRemoved / filesReplaced / fileChanges. Absent keys
    mean "no changes of that kind". Returns None when the payload has no
    usable data object.
    """
    data = (payload or {}).get("data")
    if not isinstance(data, dict):
        return None

    def _ver(key: str) -> dict[str, str]:
        v = data.get(key) or {}
        if not isinstance(v, dict):
            v = {}
        return {
            "number": str(v.get("versionNumber") or ""),
            "state": str(v.get("versionState") or ""),
            "note": str(v.get("versionNote") or ""),
            "updated": str(v.get("lastUpdatedDate") or ""),
        }

    def _field_changes(items: Any) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            out.append(
                {
                    "field": str(item.get("fieldName") or ""),
                    "old": "" if item.get("oldValue") is None else str(item.get("oldValue")),
                    "new": "" if item.get("newValue") is None else str(item.get("newValue")),
                }
            )
        return out

    metadata_changes: list[dict[str, str]] = []
    for block in data.get("metadataChanges") or []:
        if not isinstance(block, dict):
            continue
        block_name = str(block.get("blockName") or "")
        for change in _field_changes(block.get("changed")):
            change["block"] = block_name
            metadata_changes.append(change)

    toa = data.get("TermsOfAccess") or {}
    terms_changes = _field_changes((toa or {}).get("changed") if isinstance(toa, dict) else [])

    files_added = [_summarize_file_entry(f) for f in (data.get("filesAdded") or [])]
    files_removed = [_summarize_file_entry(f) for f in (data.get("filesRemoved") or [])]
    files_replaced = []
    for pair in data.get("filesReplaced") or []:
        if not isinstance(pair, dict):
            continue
        files_replaced.append(
            {"old": _summarize_file_entry(pair.get("oldFile")), "new": _summarize_file_entry(pair.get("newFile"))}
        )
    file_changes = []
    for entry in data.get("fileChanges") or []:
        if not isinstance(entry, dict):
            continue
        file_changes.append(
            {
                "file": str(entry.get("fileName") or ""),
                "id": str(entry.get("fileId") or ""),
                "changes": _field_changes(entry.get("changed")),
            }
        )

    total = (
        len(metadata_changes)
        + len(terms_changes)
        + len(files_added)
        + len(files_removed)
        + len(files_replaced)
        + sum(len(f["changes"]) for f in file_changes)
    )
    return {
        "old": _ver("oldVersion"),
        "new": _ver("newVersion"),
        "metadata_changes": metadata_changes,
        "terms_changes": terms_changes,
        "files_added": files_added,
        "files_removed": files_removed,
        "files_replaced": files_replaced,
        "file_changes": file_changes,
        "total_changes": total,
    }


def parse_dataset_versions(data: Any) -> list[dict[str, str]]:
    """Normalize a versions-list payload into version timeline entries.

    Each entry: {number ("1.0" or "Draft"), state, create_time,
    last_update, release_time, note}. Tolerates missing keys and
    non-list payloads (returns []).
    """
    out: list[dict[str, str]] = []
    if isinstance(data, dict):
        data = [data] if any(k in data for k in ("versionState", "versionNumber", "createTime")) else []
    items = data if isinstance(data, list) else []
    for v in items:
        if not isinstance(v, dict):
            continue
        state = str(v.get("versionState") or "").upper()
        num = v.get("versionNumber")
        minor = v.get("versionMinorNumber")
        try:
            number = "Draft" if state == "DRAFT" or num is None else f"{int(num)}.{int(minor or 0)}"
        except Exception:
            number = "Draft" if state == "DRAFT" else str(num or "")
        out.append(
            {
                "number": number,
                "state": state,
                "create_time": str(v.get("createTime") or ""),
                "last_update": str(v.get("lastUpdateTime") or ""),
                "release_time": str(v.get("releaseTime") or ""),
                "note": str(v.get("versionNote") or ""),
            }
        )
    return out


class DataverseClient:
    def __init__(self, base_url: str, api_token: str, timeout: int = 120) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_token = api_token
        self._timeout = timeout
        # Connection pooling: one Session reuses TCP+TLS across calls
        # (crawl locks, metadata, inventory) instead of handshaking per GET.
        self._session = requests.Session()
        try:
            from requests.adapters import HTTPAdapter

            adapter = HTTPAdapter(pool_connections=4, pool_maxsize=16)
            self._session.mount("https://", adapter)
            self._session.mount("http://", adapter)
        except Exception:
            pass
        # Probe-round bookkeeping for allowedCurationLabels (see
        # get_allowed_curation_labels / fetch_allowed_labels_shared):
        # _last_allowed_got_200 tracks the latest single attempt,
        # _last_fetch_answered aggregates the latest shared round.
        self._last_allowed_got_200 = False
        self._last_fetch_answered = False

    def close(self) -> None:
        try:
            self._session.close()
        except Exception:
            pass

    # -- low level -----------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self._api_token:
            headers["X-Dataverse-key"] = self._api_token
        return headers

    def _api(self, path: str) -> str:
        return f"{self._base_url}{path}"

    def _get_json(
        self, path: str, params: dict[str, str] | None = None
    ) -> dict[str, Any]:
        from applog import log_response

        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                start = time.monotonic()
                response = self._session.get(
                    self._api(path),
                    params=params,
                    headers=self._headers(),
                    timeout=self._timeout,
                )
                elapsed_ms = int((time.monotonic() - start) * 1000)
                summary = ""
                body: dict[str, Any] | None = None
                if response.ok:
                    try:
                        body = response.json()
                    except ValueError:
                        # Non-JSON 200 (e.g. HTML error page): surface body
                        # snippet instead of raw JSONDecodeError.
                        get_app_log().error(
                            f"GET {response.url} → {response.status_code}: "
                            f"non-JSON response: {response.text[:300]}"
                        )
                        response.raise_for_status()
                        raise RuntimeError(
                            f"GET {path} returned non-JSON response "
                            f"({response.status_code})"
                        ) from None
                    if path == "/api/search" and isinstance(body, dict):
                        try:
                            n = len(body.get("data", {}).get("items", []))
                        except Exception:
                            n = 0
                        summary = f"{n} item(s)" if n else ""
                status = response.status_code
                log_response("GET", str(response.url), status, elapsed_ms, summary)
                if not response.ok:
                    get_app_log().error(f"GET {response.url} → {status}: {response.text[:300]}")
                response.raise_for_status()
                # Reuse already-parsed body when available.
                if body is not None:
                    return body
                parsed: dict[str, Any] = response.json()
                return parsed
            except requests.HTTPError as exc:
                delay = _throttle_delay(exc)
                if delay is not None and attempt < 2:
                    wait = delay or 1.5 * (attempt + 1)
                    get_app_log().error(f"GET {path} throttled, retrying in {wait:.1f}s (attempt {attempt + 1}/3)")
                    time.sleep(wait)
                    continue
                raise
            except _RETRYABLE_NETWORK as exc:
                last_exc = exc
                get_app_log().error(f"GET {path} network error (attempt {attempt + 1}/3): {exc}")
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise requests.ConnectionError(
                    f"{exc} — the remote host closed the connection. "
                    "Try again; if it persists check your VPN/proxy or that "
                    f"{self._base_url} is reachable."
                ) from exc
            except Exception as exc:
                get_app_log().error(f"GET {path} failed: {exc}")
                raise
        assert last_exc is not None
        raise last_exc  # pragma: no cover

    def _get_text(
        self, path: str, params: dict[str, str] | None = None
    ) -> str:
        """GET returning raw text (for non-JSON endpoints like the CSV report).

        Same retry/logging contract as _get_json, except the Accept header
        advertises text/csv: the CSV report endpoint answers 406 when asked
        for application/json. HTTP errors propagate so callers can
        distinguish 403 (no permission) from other failures.
        """
        from applog import log_response

        headers = {"Accept": "text/csv, */*"}
        if self._api_token:
            headers["X-Dataverse-key"] = self._api_token
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                start = time.monotonic()
                response = self._session.get(
                    self._api(path),
                    params=params,
                    headers=headers,
                    timeout=self._timeout,
                )
                elapsed_ms = int((time.monotonic() - start) * 1000)
                summary = ""
                if response.ok:
                    summary = f"{len(response.content)} byte(s)"
                status = response.status_code
                log_response("GET", str(response.url), status, elapsed_ms, summary)
                if not response.ok:
                    get_app_log().error(f"GET {response.url} → {status}: {response.text[:300]}")
                response.raise_for_status()
                return str(response.text)
            except requests.HTTPError as exc:
                delay = _throttle_delay(exc)
                if delay is not None and attempt < 2:
                    wait = delay or 1.5 * (attempt + 1)
                    get_app_log().error(f"GET {path} throttled, retrying in {wait:.1f}s (attempt {attempt + 1}/3)")
                    time.sleep(wait)
                    continue
                raise
            except _RETRYABLE_NETWORK as exc:
                last_exc = exc
                get_app_log().error(f"GET {path} network error (attempt {attempt + 1}/3): {exc}")
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise requests.ConnectionError(
                    f"{exc} — the remote host closed the connection. "
                    "Try again; if it persists check your VPN/proxy or that "
                    f"{self._base_url} is reachable."
                ) from exc
            except Exception as exc:
                get_app_log().error(f"GET {path} failed: {exc}")
                raise
        assert last_exc is not None
        raise last_exc  # pragma: no cover

    # -- discovery -----------------------------------------------------------

    def _search_page(
        self, subtree: str = "", per_page: int = 100, start: int = 0
    ) -> tuple[list[dict[str, Any]], int | None]:
        """One Search API page → (rows, total_count).

        `total_count` is the server's total match count (None when the
        server omits it). Rows carry only what a Solr search doc has:
        no byte totals, no inventory.
        """
        params: dict[str, str] = {
            "q": "*",
            "type": "dataset",
            "per_page": str(per_page),
            "start": str(start),
        }
        subtree = (subtree or "").strip()
        if subtree and subtree.lower() not in ("root", ":root"):
            params["subtree"] = subtree
        get_app_log().info(f"Search API q=* type=dataset per_page={per_page} start={start} subtree='{subtree}'")
        try:
            payload = self._get_json("/api/search", params=params)
        except requests.HTTPError as exc:
            resp = getattr(exc, "response", None)
            if resp is not None and resp.status_code in (400, 404):
                body = ""
                try:
                    body = resp.json().get("message", "") or resp.text[:500]
                except Exception:
                    body = resp.text[:500] if hasattr(resp, "text") else ""
                raise RuntimeError(
                    f"Collection '{subtree}' not found or not accessible"
                    + (f": {body}" if body else "")
                    + " — try an empty alias for the whole repository, or check the alias spelling."
                ) from exc
            raise
        data_block = payload.get("data", {}) or {}
        items = data_block.get("items", [])
        try:
            total_count: int | None = int(data_block["total_count"])
        except (KeyError, TypeError, ValueError):
            total_count = None
        datasets: list[dict[str, Any]] = []
        for item in items:
            pid = item.get("global_id") or item.get("identifier") or ""
            contacts = item.get("contacts") or []
            contact = ", ".join(c.get("name", "") for c in contacts[:2] if c.get("name"))
            collection = item.get("name_of_dataverse") or item.get("identifier_of_dataverse") or ""
            if item.get("identifier_of_dataverse") and item.get("name_of_dataverse"):
                collection = f"{item['name_of_dataverse']} ({item['identifier_of_dataverse']})"
            # depositor not directly in search; use contact as fallback until detail is loaded
            state, has_draft = search_item_state(item)
            datasets.append(
                {
                    "persistent_id": pid,
                    "title": item.get("name") or item.get("title") or pid,
                    "contact": contact,
                    "depositor": contact,
                    "date_created": (item.get("createdAt") or "")[:10],
                    "date_published": (item.get("published_at") or "")[:10],
                    "collection": collection,
                    "state": state,
                    "has_draft": has_draft,
                    "publication_statuses": [str(s or "") for s in (item.get("publicationStatuses") or [])],
                    "file_count": int(item.get("fileCount") or 0),
                    # Search items carry no byte totals — None (unknown, shown
                    # as "—") rather than a misleading 0. The enrichment
                    # stage and the download quote provide real sums.
                    "total_size_bytes": None,
                    "files": [],
                }
            )
        return datasets, total_count

    def _search_fallback(
        self, subtree: str = "", per_page: int = 100, start: int = 0
    ) -> list[dict[str, Any]]:
        """One Search API page as rows only (compat wrapper)."""
        rows, _total = self._search_page(subtree, per_page, start)
        return rows

    def list_draft_datasets(
        self,
        subtree: str = "",
        per_page: int = 1000,
        max_pages: int = 100,
        progress: Callable[[int, int, int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> list[dict[str, Any]]:
        """All datasets in the subtree (superset of in-review).

        Pages the native Search API with `per_page` (1000 by default) and
        drives the loop from the server's `total_count`: the page count is
        known after the first response, so progress can be reported as
        "page N of M". Termination is belt-and-suspenders — the loop ends
        when the collected count reaches the total, when a page comes back
        short or empty (the ground truth for a corpus that shifts under a
        long crawl), or when the runaway guard trips. Whatever ends it, the
        collected count is reconciled against the total and any gap is
        logged loudly instead of pretending the pull was complete.

        `max_pages` is a runaway guard (100 × 1000 = 100k datasets), not a
        data cap. `progress(page, pages_total, collected)` is called after
        each page; `is_cancelled` stops the crawl cooperatively.
        """
        all_datasets: list[dict[str, Any]] = []
        seen: dict[str, int] = {}
        total_expected: int | None = None
        pages_total: int | None = None
        hit_page_cap = False
        page = 0
        while page < max_pages:
            if is_cancelled is not None:
                try:
                    if is_cancelled():
                        break
                except Exception:
                    pass
            page += 1
            start = (page - 1) * per_page
            batch, total_count = self._search_page(subtree, per_page, start)
            if total_count is not None and total_expected is None:
                total_expected = total_count
                try:
                    pages_total = max(1, -(-total_expected // per_page))
                except Exception:
                    pages_total = None
            if not batch:
                get_app_log().info(
                    f"Search page {page} (start={start}): empty — stopping"
                )
                break
            new = 0
            for d in batch:
                pid = d["persistent_id"]
                if pid not in seen:
                    seen[pid] = len(all_datasets)
                    all_datasets.append(d)
                    new += 1
                elif d.get("has_draft") and not all_datasets[seen[pid]].get("has_draft"):
                    # Same dataset surfaced twice (published doc shadows the
                    # draft doc): keep the draft row so in-progress versions
                    # stay visible to draft filtering.
                    all_datasets[seen[pid]] = d
                    new += 1
            get_app_log().info(
                f"Search page {page} (start={start}): {len(batch)} item(s), "
                f"{new} new, cumulative {len(all_datasets)}"
            )
            if progress is not None:
                try:
                    progress(page, pages_total or 0, len(all_datasets))
                except Exception:
                    pass
            if len(batch) < per_page:
                # Short page: the corpus is exhausted (or the server
                # clamped per_page). Ground truth — stop here.
                break
            if total_expected is not None and len(all_datasets) >= total_expected:
                # Reached the advertised total: the plan is done. The
                # short-page rule above covers a corpus that grew.
                break
            if page == max_pages:
                hit_page_cap = True
        if hit_page_cap:
            get_app_log().error(
                f"Search hit the {max_pages}-page runaway guard — results are "
                "TRUNCATED. Narrow the collection/subtree and refresh."
            )
        # Reconcile what we got against what the server advertised.
        if total_expected is not None and len(all_datasets) != total_expected:
            gap = total_expected - len(all_datasets)
            if gap > 0:
                get_app_log().error(
                    f"Search collected {len(all_datasets)} of {total_expected} "
                    f"dataset(s) — {gap} missing (the index changed during the "
                    "crawl, or the server clamps page size). Narrow the "
                    "collection and refresh if rows are missing."
                )
            else:
                get_app_log().info(
                    f"Search collected {len(all_datasets)} dataset(s) — "
                    f"{abs(gap)} more than the advertised total of "
                    f"{total_expected} (the index grew during the crawl)"
                )
        get_app_log().info(
            f"Search complete: {len(all_datasets)} dataset(s)"
            f"{' (TRUNCATED — see above)' if hit_page_cap else ''}"
        )
        return all_datasets

    def dataset_in_review(self, identifier: str) -> bool:
        try:
            if ":" in identifier:
                payload = self._get_json(
                    "/api/datasets/:persistentId/locks",
                    params={"persistentId": identifier},
                )
            else:
                payload = self._get_json(f"/api/datasets/{identifier}/locks")
            return locks_indicate_review(payload.get("data", []))
        except (requests.HTTPError, requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError, ConnectionResetError):
            return False

    def list_datasets_in_review(
        self, subtree: str = ""
    ) -> list[dict[str, Any]]:
        """Drafts from the crawl, kept only when locked IN_REVIEW."""
        drafts = self.list_draft_datasets(subtree)
        return [d for d in drafts if self.dataset_in_review(d["persistent_id"])]

    # -- authenticated identity --------------------------------------------
    # GET /api/users/:me answers for ANY valid token with the caller's
    # profile, including the `superuser` flag. Used to pick the superuser
    # vs curator code path (bulk CSV report vs per-draft label reads) once
    # per session instead of burning a doomed 403 first.

    def get_me(self) -> dict[str, Any] | None:
        """Fetch the authenticated user's profile (identity + superuser flag), or None.

        One network call per (instance, token) per process: successes are
        cached; failures return None without caching (a later retry may
        succeed). Never raises.
        """
        key = _me_cache_key(self._base_url, self._api_token)
        try:
            with _ME_LOCK:
                hit = _ME_CACHE.get(key)
            if isinstance(hit, dict):
                return dict(hit)
        except Exception:
            pass
        try:
            payload = self._get_json("/api/users/:me")
        except requests.HTTPError as exc:
            resp = getattr(exc, "response", None)
            status = resp.status_code if resp is not None else 0
            if status in (400, 401, 403, 404):
                try:
                    get_app_log().info(
                        f"users/:me unavailable (HTTP {status}) — "
                        "continuing without identity"
                    )
                except Exception:
                    pass
                return None
            raise
        except _RETRYABLE_NETWORK as exc:
            try:
                get_app_log().info(f"users/:me network error — continuing without identity ({exc})")
            except Exception:
                pass
            return None
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return None
        try:
            with _ME_LOCK:
                _ME_CACHE[key] = dict(data)
        except Exception:
            pass
        return dict(data)

    def user_is_superuser(self) -> bool | None:
        """True/False from /api/users/:me; None when identity is unknown."""
        try:
            me = self.get_me()
        except Exception:
            return None
        if not isinstance(me, dict):
            return None
        return bool(me.get("superuser"))

    def get_collection_roles(self, alias: str) -> list[str] | None:
        """Role names the calling user holds on one collection, or None.

        Matches the /api/users/:me identifier against
        GET /api/dataverses/{alias}/assignments (e.g. "@pratti" -> Admin).
        Cached per (instance, token, alias); denials and network failures
        return None without caching. Never raises for 4xx/network; other
        HTTP errors propagate like the other client methods.
        """
        alias = (alias or "").strip()
        if not alias:
            return None
        key = _me_cache_key(self._base_url, self._api_token) + (alias.lower(),)
        try:
            with _ME_LOCK:
                hit = _ROLE_CACHE.get(key)
            if isinstance(hit, list):
                return list(hit)
        except Exception:
            pass
        try:
            me = self.get_me()
        except Exception:
            return None
        identifier = str((me or {}).get("identifier") or "").strip()
        if not identifier:
            return None
        try:
            from urllib.parse import quote as _quote

            payload = self._get_json(
                f"/api/dataverses/{_quote(alias, safe='')}/assignments"
            )
        except requests.HTTPError as exc:
            resp = getattr(exc, "response", None)
            status = resp.status_code if resp is not None else 0
            if status in (400, 401, 403, 404):
                try:
                    get_app_log().info(
                        f"assignments for '{alias}' unavailable (HTTP {status}) — "
                        "continuing without collection role"
                    )
                except Exception:
                    pass
                return None
            raise
        except _RETRYABLE_NETWORK as exc:
            try:
                get_app_log().info(
                    f"assignments for '{alias}' network error — "
                    f"continuing without collection role ({exc})"
                )
            except Exception:
                pass
            return None
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            return None
        roles: list[str] = []
        for entry in data:
            try:
                if not isinstance(entry, dict):
                    continue
                if str(entry.get("assignee") or "").strip() != identifier:
                    continue
                name = str(
                    entry.get("roleName") or entry.get("_roleAlias") or ""
                ).strip()
                if name and name not in roles:
                    roles.append(name)
            except Exception:
                continue
        try:
            with _ME_LOCK:
                _ROLE_CACHE[key] = list(roles)
        except Exception:
            pass
        return roles

    # -- curation labels ---------------------------------------------------
    # See https://guides.dataverse.org/en/latest/api/curation-labels.html
    # Labels are configured per Dataverse instance/collection (AllowedCurationLabels),
    # so the allowed set can differ between instances. All methods degrade to
    # None/[] when labels are not configured or the caller lacks permission
    # (403/404), never raising for those cases.

    def _curation_paths(self, identifier: str, endpoint: str) -> tuple:
        if ":" in identifier:
            return (
                f"/api/datasets/:persistentId/{endpoint}",
                {"persistentId": identifier},
            )
        return f"/api/datasets/{identifier}/{endpoint}", None

    def get_curation_status(
        self, identifier: str, include_history: bool = False
    ) -> dict[str, Any] | None:
        """Return the current curation label for a draft dataset, or None if unset/unavailable."""
        path, base_params = self._curation_paths(identifier, "curationStatus")
        params = dict(base_params or {})
        if include_history:
            params["includeHistory"] = "true"
        try:
            payload = self._get_json(path, params=params or None)
        except requests.HTTPError as exc:
            resp = getattr(exc, "response", None)
            if resp is not None and resp.status_code in (400, 401, 403, 404):
                return None
            raise
        except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError, ConnectionResetError):
            return None
        return parse_curation_status(payload)

    def get_curation_history(self, identifier: str) -> list[dict[str, Any]]:
        """Full label-assignment history (oldest-first) for a draft dataset."""
        path, base_params = self._curation_paths(identifier, "curationStatus")
        params = dict(base_params or {})
        params["includeHistory"] = "true"
        try:
            payload = self._get_json(path, params=params)
        except requests.HTTPError as exc:
            resp = getattr(exc, "response", None)
            if resp is not None and resp.status_code in (400, 401, 403, 404):
                return []
            raise
        except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError, ConnectionResetError):
            return []
        data = (payload or {}).get("data")
        if not isinstance(data, list):
            single = parse_curation_status(payload)
            return [single] if single else []
        out = []
        for entry in data:
            if isinstance(entry, dict) and str(entry.get("label") or "").strip():
                out.append(
                    {
                        "label": str(entry.get("label")).strip(),
                        "time": str(entry.get("createTime") or ""),
                        "assigner": str(entry.get("assigner") or entry.get("user") or ""),
                    }
                )
        return out

    def get_allowed_curation_labels(self, identifier: str) -> list[str]:
        """Return allowed labels for one dataset (instance/collection-specific).

        Reports what the server answered to the app log: the received list
        on success, or the denial status when this dataset yields no answer
        (403/404/400 = no PublishDataset permission or not a draft — the
        caller probes further datasets in that case).
        """
        path, params = self._curation_paths(identifier, "allowedCurationLabels")
        try:
            payload = self._get_json(path, params=params)
            # A 200 answer (even an empty allowed set) is a DEFINITIVE
            # server answer — recorded so callers can tell "the server
            # said nothing is configured" apart from transport/server
            # errors, which must never freeze an empty cache in place.
            try:
                self._last_allowed_got_200 = True
            except Exception:
                pass
        except requests.HTTPError as exc:
            resp = getattr(exc, "response", None)
            status = resp.status_code if resp is not None else 0
            if status in (400, 401, 403, 404):
                try:
                    get_app_log().info(
                        f"allowedCurationLabels for {identifier}: HTTP {status} — "
                        "no answer from this dataset"
                    )
                except Exception:
                    pass
                return []
            raise
        except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError, ConnectionResetError):
            try:
                get_app_log().info(
                    f"allowedCurationLabels for {identifier}: network error — no answer"
                )
            except Exception:
                pass
            return []
        labels = parse_allowed_labels(payload.get("data"))
        try:
            get_app_log().info(
                f"allowedCurationLabels for {identifier}: received "
                + (", ".join(f"'{lbl}'" for lbl in labels) if labels else "(empty — none configured)")
            )
        except Exception:
            pass
        return labels

    def discover_curation_labels(
        self, persistent_ids: list[str], sample_size: int = 5
    ) -> list[str]:
        """Union of allowed labels across a sample of datasets.

        Allowed labels can vary per collection/dataset, so probe the first
        few datasets until at least one reports a non-empty set. Order of
        first appearance is preserved.
        """
        labels: list[str] = []
        for pid in (persistent_ids or [])[: max(1, sample_size)]:
            try:
                for label in self.get_allowed_curation_labels(pid):
                    if label not in labels:
                        labels.append(label)
            except Exception:
                continue
            if labels:
                break
        if not labels:
            # Fall back to sampling the rest if the head had none configured
            for pid in (persistent_ids or [])[max(1, sample_size):]:
                try:
                    for label in self.get_allowed_curation_labels(pid):
                        if label not in labels:
                            labels.append(label)
                except Exception:
                    continue
                if labels:
                    break
        return labels

    def fetch_allowed_labels_shared(
        self, collection: str, probe_pids: list[str], max_attempts: int = 3
    ) -> list[str]:
        """Return allowed labels via the top-level shared cache (probed once).

        Memory cache first; on miss, probe drafts in order and stop at the
        first non-empty answer, so one discovery round costs a single API
        call. A stamped disk entry (first alias use) serves every later
        session with zero calls; only a new top-level collection (or an
        unstamped legacy entry, once) misses the cache. A 200-confirmed
        empty answer stamps [] exactly once; transport/server errors
        (nothing answered) are cached in memory only and retried next
        session — never frozen to disk. See last_allowed_probe_answered().
        """
        try:
            cached = get_cached_allowed_labels(self._base_url, collection)
        except Exception:
            cached = None
        if cached is not None:
            try:
                get_app_log().info(
                    "allowedCurationLabels: cache hit for "
                    f"'{collection or 'whole repository'}': "
                    + (", ".join(f"'{lbl}'" for lbl in cached) if cached else "(empty)")
                )
            except Exception:
                pass
            return list(cached)
        labels: list[str] = []
        try:
            attempts = max(1, int(max_attempts or 1))
        except Exception:
            attempts = 3
        probed = 0
        answered = False
        for pid in (probe_pids or [])[:attempts]:
            if not pid:
                continue
            probed += 1
            try:
                self._last_allowed_got_200 = False
                found = self.get_allowed_curation_labels(pid)
                if self._last_allowed_got_200:
                    answered = True
            except Exception:
                found = []
            for label in found or []:
                if label not in labels:
                    labels.append(label)
            if labels:
                break
        try:
            self._last_fetch_answered = bool(answered)
        except Exception:
            pass
        try:
            get_app_log().info(
                f"allowedCurationLabels: probed {probed} dataset(s), "
                + (", ".join(f"'{lbl}'" for lbl in labels) if labels
                   else ("no dataset answered — will retry next session"
                         if not answered else "none configured"))
            )
        except Exception:
            pass
        try:
            set_cached_allowed_labels(self._base_url, collection, labels)
        except Exception:
            pass
        return labels

    def last_allowed_probe_answered(self) -> bool:
        """Whether the latest shared probe round got a server answer.

        True when at least one attempt returned HTTP 200 (labels found or
        confirmed-empty). False after transport/server errors or when no
        round ran — callers must not stamp the disk slot in that case.
        """
        try:
            return bool(getattr(self, "_last_fetch_answered", False))
        except Exception:
            return False

    # -- metadata blocks (field catalog) ------------------------------------

    def get_metadatablock_names(self) -> list[str]:
        """Block names from GET /api/metadatablocks ([] when unavailable)."""
        try:
            payload = self._get_json("/api/metadatablocks")
        except Exception:
            return []
        return parse_metadatablock_names(payload)

    def get_metadatablock_display_names(self) -> dict[str, str]:
        """{block name: display name} from GET /api/metadatablocks ({} on miss)."""
        try:
            payload = self._get_json("/api/metadatablocks")
        except Exception:
            return {}
        return parse_metadatablock_display_names(payload)

    def get_metadatablock_fields(self, block: str) -> list[dict[str, Any]]:
        """[{block, field, label}] for one block ([] when unavailable)."""
        try:
            payload = self._get_json(f"/api/metadatablocks/{block}")
        except Exception:
            return []
        return parse_metadatablock_fields(payload)

    def fetch_metadata_field_catalog(self) -> list[dict[str, Any]]:
        """Full field catalog across blocks (memory/disk cache first).

        One /api/metadatablocks call plus one per block on miss; cached per
        instance, so the Review-configuration page costs zero calls on
        repeat opens. Each field carries block_label (the block's display
        name) alongside block/field/label. Empty results are NOT served
        from memory — [] means the fetch failed, so the next call retries
        instead of freezing an empty catalog in the process. Never raises.
        """
        try:
            cached = get_cached_metadata_fields(self._base_url)
        except Exception:
            cached = None
        if cached:
            return list(cached)
        fields: list[dict[str, str]] = []
        try:
            labels = self.get_metadatablock_display_names()
        except Exception:
            labels = {}
        try:
            names = list(labels) if labels else self.get_metadatablock_names()
            for block in names:
                try:
                    for entry in self.get_metadatablock_fields(block):
                        if isinstance(entry, dict) and entry.get("field"):
                            entry["block_label"] = labels.get(block, "")
                            fields.append(entry)
                except Exception:
                    continue
        except Exception:
            fields = []
        try:
            set_cached_metadata_fields(self._base_url, fields)
        except Exception:
            pass
        return fields

    def list_curation_states(self) -> list[dict[str, Any]] | None:
        """Bulk curation-status report for ALL draft datasets (one CSV call).

        Returns parsed rows on success (possibly empty), or None when the
        caller lacks permission or the network fails — callers fall back to
        per-dataset curationStatus in that case. Other HTTP errors propagate.
        """
        try:
            text = self._get_text("/api/datasets/listCurationStates")
        except requests.HTTPError as exc:
            resp = getattr(exc, "response", None)
            if resp is not None and resp.status_code in (400, 401, 403, 404):
                get_app_log().info(
                    "listCurationStates unavailable "
                    f"({resp.status_code}) — falling back to per-dataset curationStatus"
                )
                return None
            raise
        except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError, ConnectionResetError):
            return None
        return parse_curation_states_csv(text)

    def compare_versions(
        self,
        identifier: str,
        old: str = ":latest-published",
        new: str = ":draft",
    ) -> dict[str, Any] | None:
        """Diff two dataset versions (default: published vs draft).

        Wraps GET /api/datasets/{id}/versions/{old}/compare/{new}, which
        returns changed metadata/terms fields plus added/removed/replaced
        files. Returns the normalized parse_version_compare() dict, or None
        when there is nothing comparable (no published version yet, draft
        missing, 4xx) or the network fails. Other HTTP errors propagate.
        """
        if ":" in identifier:
            path = f"/api/datasets/:persistentId/versions/{old}/compare/{new}"
            params: dict[str, str] | None = {"persistentId": identifier}
        else:
            path = f"/api/datasets/{identifier}/versions/{old}/compare/{new}"
            params = None
        try:
            payload = self._get_json(path, params=params)
        except requests.HTTPError as exc:
            resp = getattr(exc, "response", None)
            if resp is not None and resp.status_code in (400, 401, 403, 404):
                get_app_log().info(
                    f"compare {old}→{new} unavailable for {identifier} "
                    f"({resp.status_code})"
                )
                return None
            raise
        except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError, ConnectionResetError):
            return None
        return parse_version_compare(payload)

    def list_versions(self, identifier: str) -> list[dict[str, str]]:
        """All versions of a dataset (oldest-first as returned) for timelines.

        Returns [] when the dataset has no visible versions, on 4xx, or on
        network failure — callers treat this as best-effort timeline data.
        """
        if ":" in identifier:
            path = "/api/datasets/:persistentId/versions"
            params: dict[str, str] | None = {"persistentId": identifier}
        else:
            path = f"/api/datasets/{identifier}/versions"
            params = None
        try:
            payload = self._get_json(path, params=params)
        except requests.HTTPError as exc:
            resp = getattr(exc, "response", None)
            if resp is not None and resp.status_code in (400, 401, 403, 404):
                return []
            raise
        except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError, ConnectionResetError):
            return []
        return parse_dataset_versions((payload or {}).get("data"))

    def get_timestamps(
        self, identifier: str, numeric_id: Any = None
    ) -> dict[str, str]:
        """Lifecycle timestamps for a dataset (create/publication/DOI/draft touches).

        Wraps GET /api/datasets/{id}/timestamps. Tries the :persistentId form
        first, then the numeric dataset id when known (some instances only
        route one form). Returns {} when unavailable (4xx) or on network
        failure — callers treat this as best-effort timeline data.
        """
        candidates: list[tuple] = []
        if ":" in identifier:
            candidates.append(
                ("/api/datasets/:persistentId/timestamps", {"persistentId": identifier})
            )
        else:
            candidates.append((f"/api/datasets/{identifier}/timestamps", None))
        try:
            numeric = int(numeric_id)  # type: ignore[arg-type]
            candidates.append((f"/api/datasets/{numeric}/timestamps", None))
        except Exception:
            pass
        for path, params in candidates:
            try:
                payload = self._get_json(path, params=params)
            except requests.HTTPError as exc:
                resp = getattr(exc, "response", None)
                if resp is not None and resp.status_code in (400, 401, 403, 404):
                    continue
                raise
            except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError, ConnectionResetError):
                return {}
            parsed = parse_timestamps(payload)
            if parsed:
                return parsed
        return {}

    def find_review_submissions(
        self,
        persistent_id: str,
        per_page: int = 100,
        max_pages: int = 5,
    ) -> list[dict[str, str]]:
        """Review-submission events for a dataset from the user's notifications.

        Dataverse exposes no submitted-for-review timestamp on the dataset
        itself; submission does notify curators (SUBMITTEDDS), and those
        notifications carry sentTimestamp. Scans the token owner's inbox in
        in-app format (newest first), matching on the structured
        datasetPersistentIdentifier — no text comparison. The collection name
        comes from each note's ownerDisplayName as pulled from the API.
        Returns matches (possibly []) — never raises for 4xx/network issues.
        """
        matches: list[dict[str, str]] = []
        if not (persistent_id or "").strip():
            return matches
        try:
            for page in range(max_pages):
                try:
                    payload = self._get_json(
                        "/api/notifications/all",
                        params={
                            "limit": str(per_page),
                            "offset": str(page * per_page),
                            "inAppNotificationFormat": "true",
                        },
                    )
                except requests.HTTPError as exc:
                    resp = getattr(exc, "response", None)
                    if resp is not None and resp.status_code in (400, 401, 403, 404):
                        break
                    raise
                items = (payload or {}).get("data")
                if isinstance(items, dict):
                    # Real shape: {"notifications": [...], ...}
                    items = items.get("notifications") or []
                if not isinstance(items, list):
                    break
                for note in items:
                    hit = note_review_submission(persistent_id, note)
                    if hit and hit not in matches:
                        matches.append(hit)
                if len(items) < per_page:
                    break
        except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError, ConnectionResetError):
            pass
        return matches

    def set_curation_label(self, identifier: str, label: str) -> bool:
        """Assign a curation label to a draft dataset. Returns True on success."""
        from applog import log_response

        path, base_params = self._curation_paths(identifier, "curationStatus")
        params = dict(base_params or {})
        params["label"] = label
        try:
            start = time.monotonic()
            response = self._session.put(
                self._api(path),
                params=params,
                headers=self._headers(),
                timeout=self._timeout,
            )
            elapsed_ms = int((time.monotonic() - start) * 1000)
            log_response("PUT", str(response.url), response.status_code, elapsed_ms, label)
            if not response.ok:
                get_app_log().error(f"PUT {response.url} → {response.status_code}: {response.text[:300]}")
            response.raise_for_status()
            return True
        except Exception as exc:
            get_app_log().error(f"PUT {path} label={label!r} failed: {exc}")
            return False

    def delete_curation_label(self, identifier: str) -> bool:
        """Remove the curation label from a draft dataset. Returns True on success."""
        from applog import log_response

        path, params = self._curation_paths(identifier, "curationStatus")
        try:
            start = time.monotonic()
            response = self._session.delete(
                self._api(path),
                params=params,
                headers=self._headers(),
                timeout=self._timeout,
            )
            elapsed_ms = int((time.monotonic() - start) * 1000)
            log_response("DELETE", str(response.url), response.status_code, elapsed_ms, "")
            if not response.ok:
                get_app_log().error(f"DELETE {response.url} → {response.status_code}: {response.text[:300]}")
            response.raise_for_status()
            return True
        except Exception as exc:
            get_app_log().error(f"DELETE {path} failed: {exc}")
            return False

    # -- metadata ------------------------------------------------------------

    def get_dataset_metadata(self, identifier: str) -> dict[str, Any]:
        if ":" in identifier:
            payload = self._get_json(
                "/api/datasets/:persistentId",
                params={"persistentId": identifier},
            )
        else:
            payload = self._get_json(f"/api/datasets/{identifier}")
        data: dict[str, Any] = payload.get("data", {})
        return data

    def get_variable_metadata(self, file_id: str) -> dict[str, dict[str, str]] | None:
        """Variable-level metadata for one tabular file, from its DDI.

        Returns ``{variable name: {"label": str, "type": str}}`` (label may
        be empty), or None when the fetch/parse fails — callers treat None
        as "unknown coverage", never as "no documentation".
        """
        try:
            text = self._get_text(f"/api/access/datafile/{file_id}/metadata/ddi")
            import xml.etree.ElementTree as ET

            root = ET.fromstring(text)
        except Exception:
            return None
        out: dict[str, dict[str, str]] = {}
        try:
            for var in root.iter():
                tag = var.tag.rsplit("}", 1)[-1]
                if tag != "var":
                    continue
                name = str(var.get("name") or "").strip()
                if not name:
                    continue
                label = ""
                intrvl = str(var.get("intrvl") or "")
                for child in var:
                    ctag = child.tag.rsplit("}", 1)[-1]
                    if ctag == "labl":
                        label = (child.text or "").strip()
                out[name] = {"label": label, "type": intrvl}
        except Exception:
            return None
        return out or None

    def get_guestbook(self, guestbook_id: int | str) -> dict[str, Any]:
        """Fetch one guestbook definition (required fields + custom questions).

        Dataverse requires an API token for this call. The returned dict is
        what the download window renders: ``nameRequired``/``emailRequired``/
        ``institutionRequired``/``positionRequired`` plus ``customQuestions``
        (each with ``id``, ``question``, ``required``, ``type`` and, for
        type ``options``, ``optionValues``).
        """
        payload = self._get_json(f"/api/guestbooks/{guestbook_id}")
        data = payload.get("data") if isinstance(payload, dict) else None
        return data if isinstance(data, dict) else {}

    def get_current_user(self) -> dict[str, Any]:
        """Best-effort account details for guestbook prefill.

        Never raises: a missing/limited token just means the download window
        starts with empty fields. `affiliation` is the guestbook's
        institution; the account may have no position (the window then asks
        for it, because Dataverse rejects a missing required position).
        """
        try:
            payload = self._get_json("/api/users/:me")
        except Exception:
            return {}
        data = payload.get("data") if isinstance(payload, dict) else None
        return data if isinstance(data, dict) else {}

    def get_file_inventory(
        self, identifier: str, version: str = "draft"
    ) -> list[dict[str, Any]]:
        data, api_version, tried = self._fetch_version_data(identifier, version)
        if api_version != f":{version.lstrip(':').lower()}":
            get_app_log().error(
                f"Inventory for {identifier}: requested :{version} "
                f"unavailable, using {api_version} (tried {tried}) — "
                "verify you are reviewing the intended version"
            )
        return normalize_files(_version_files_data(data))

    def _fetch_version_data(
        self,
        identifier: str,
        version: str = "draft",
        fall_back_on_auth: bool = False,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """Fetch the raw `data` payload for one dataset version.

        Tries `version` first (correct lowercase, e.g. `:draft`), then
        `:latest` / `:latest-published`, then an unversioned metadata read.
        Returns `(data, used_version, tried)`.

        With `fall_back_on_auth=False` (the default, used for the actual
        check inventory) an auth failure (401/403) fails fast — retrying
        other versions would mask a bad token and risk running checks on
        the wrong version silently.

        With `fall_back_on_auth=True` (dashboard enrichment) an auth
        failure on one version only means "you may not see that
        version" — a published dataset has no readable draft, and a
        guest token cannot see drafts at all. Enrichment then tries the
        next version, and raises only if EVERY version was refused (which
        does mean the token itself is bad).
        """
        tried: list[str] = []
        auth_errors: list[Exception] = []
        for ver in (version, "latest", "latest-published"):
            api_version = ver if ver.startswith(":") else f":{ver.lower()}"
            try:
                if ":" in identifier:
                    payload = self._get_json(
                        f"/api/datasets/:persistentId/versions/{api_version}",
                        params={"persistentId": identifier},
                    )
                else:
                    payload = self._get_json(
                        f"/api/datasets/{identifier}/versions/{api_version}"
                    )
                return payload.get("data", {}), api_version, tried
            except requests.HTTPError as exc:
                resp = getattr(exc, "response", None)
                status = resp.status_code if resp is not None else 0
                tried.append(f"{api_version}={status}")
                if status in (401, 403):
                    if not fall_back_on_auth:
                        # Auth failure: do not silently try other versions.
                        raise
                    # "You may not see this version" — remember it and try
                    # the next one. A refusal on EVERY version means the
                    # token itself is bad, which the caller must know.
                    auth_errors.append(exc)
                    get_app_log().info(
                        f"Version {api_version} not readable for {identifier} "
                        f"({status}), trying next version"
                    )
                    continue
                if status in (400, 404):
                    get_app_log().info(f"Version {api_version} not available for {identifier} ({status}), trying next")
                    continue
                raise
        # Every version was refused (401/403) — the token cannot read this
        # dataset at all. Surface it so the caller can abort the batch.
        if auth_errors:
            raise auth_errors[-1]
        # fallback: try without version (latest published)
        payload = self._get_json(
            "/api/datasets/:persistentId" if ":" in identifier else f"/api/datasets/{identifier}",
            params={"persistentId": identifier} if ":" in identifier else None,
        )
        # dataset metadata contains latestVersion files? try to extract
        data = payload.get("data", {})
        return data, "unversioned", tried

    def enrich_datasets_with_inventory(
        self,
        datasets: list[dict[str, Any]],
        max_rows: int = 200,
        max_workers: int = 5,
        progress: Callable[[int, int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> dict[str, int]:
        """Patch thin search rows with live inventory sums + depositor + state.

        For each row lacking `total_size_bytes`, fetches one version doc
        (`:draft`, falling back like `get_file_inventory`) and patches
        `total_size_bytes` (summed), `file_count` (only when the search
        value is falsy), `depositor` (only when the version carries one),
        `state` (never clobbering an "In Review" lock confirmation), and
        `has_draft` (set True when the `:draft` doc answers). Patched rows
        get `size_enriched=True`; rows beyond `max_rows` keep thin data and
        get `size_pending=True` so the UI can say so. Never embeds file
        arrays — sums and counts only.

        Drafts go first so a capped run enriches curation candidates before
        published rows. Per-item isolation: one dataset's failure never
        fails the batch. Auth failure (401/403) aborts the remaining
        queue — every later item would fail the same way. Never raises;
        returns {"attempted", "enriched", "pending", "auth_failed"}.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        try:
            rows = [d for d in (datasets or []) if isinstance(d, dict)]
        except Exception:
            return {"attempted": 0, "enriched": 0, "pending": 0, "auth_failed": 0}
        candidates = [
            ds for ds in rows
            if ds.get("total_size_bytes") is None and str(ds.get("persistent_id") or "")
        ]
        # Drafts first: capped runs spend calls on curation candidates.
        try:
            candidates.sort(key=lambda ds: 0 if is_draft_dataset(ds) else 1)
        except Exception:
            pass
        todo = candidates[:max_rows] if max_rows >= 0 else list(candidates)
        for ds in candidates[len(todo):]:
            try:
                if ds.get("total_size_bytes") is None:
                    ds["size_pending"] = True
            except Exception:
                pass
        result = {"attempted": 0, "enriched": 0, "pending": len(candidates) - len(todo), "auth_failed": 0}
        if not todo:
            return result

        def _fetch_one(ds: dict) -> tuple[dict, tuple]:
            pid = str(ds.get("persistent_id") or "")
            # fall_back_on_auth: a published dataset has no readable draft
            # and a guest token cannot see drafts at all — fall through to
            # the published version instead of failing the dataset.
            data, used_version, _tried = self._fetch_version_data(
                pid, fall_back_on_auth=True
            )
            files, depositor, state, files_known = _summarize_version_data(data)
            return ds, (
                files, depositor, state, used_version, files_known,
                _version_last_update(data),
            )

        def _auth_denied(exc: BaseException) -> bool:
            try:
                resp = getattr(exc, "response", None)
                return resp is not None and resp.status_code in (401, 403)
            except Exception:
                return False

        total = len(todo)
        done = 0
        try:
            with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
                futures = {pool.submit(_fetch_one, ds): ds for ds in todo}
                for fut in as_completed(futures):
                    if is_cancelled is not None:
                        try:
                            if is_cancelled():
                                for f in futures:
                                    f.cancel()
                                break
                        except Exception:
                            pass
                    ds = futures[fut]
                    result["attempted"] += 1
                    try:
                        _ds, summary = fut.result()
                    except Exception as exc:
                        if _auth_denied(exc):
                            result["auth_failed"] = 1
                            for f in futures:
                                f.cancel()
                            break
                        continue
                    try:
                        (
                            files, depositor, state, used_version, files_known,
                            last_update,
                        ) = summary
                        if last_update:
                            ds["draft_updated_at"] = last_update
                        if files_known:
                            ds["total_size_bytes"] = sum(
                                int(f.get("size_bytes") or 0) for f in files
                            )
                            ds["size_enriched"] = True
                            try:
                                ds.pop("size_pending", None)
                            except Exception:
                                pass
                            if not ds.get("file_count") and files:
                                ds["file_count"] = len(files)
                        if depositor and (not ds.get("depositor") or ds.get("depositor") == ds.get("contact")):
                            ds["depositor"] = depositor
                        if state and "REVIEW" not in str(ds.get("state") or "").upper():
                            ds["state"] = state
                        if used_version == ":draft":
                            ds["has_draft"] = True
                        result["enriched"] += 1
                    except Exception:
                        continue
                    done += 1
                    if progress is not None:
                        try:
                            progress(done, total)
                        except Exception:
                            pass
        except Exception:
            pass
        return result

    # -- download ------------------------------------------------------------

    def _stream_url(
        self,
        url: str,
        params: dict[str, str],
        dl_headers: dict[str, str],
        dest: Path,
        progress: Callable[[int], None] | None,
        label: str,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> int | None:
        """Stream one URL to `dest`, with retries.

        Returns bytes received, or None when the server answers 400/404
        (version unavailable — caller tries the next version). Auth failures
        (401/403) raise immediately so a bad token is not masked by version
        fallback. Raises on persistent network/HTTP failure. `dest` is
        truncated at the start of every attempt, so callers must pass a
        .part path. `is_cancelled` is polled per chunk; a True answer
        raises DownloadCancelled, which is never retried.
        """
        from applog import log_response

        if is_cancelled and is_cancelled():
            raise DownloadCancelled(label)
        for attempt in range(3):
            try:
                start = time.monotonic()
                with self._session.get(
                    url,
                    params=params,
                    headers=dl_headers,
                    stream=True,
                    timeout=self._timeout,
                ) as response:
                    if response.status_code in (401, 403):
                        get_app_log().error(
                            f"Download {label} denied ({response.status_code}) — "
                            "check API token, not trying other versions"
                        )
                        response.raise_for_status()
                    if response.status_code in (400, 404):
                        message = _error_message(response)
                        if "guestbook" in message.lower():
                            get_app_log().error(
                                f"Download {label} blocked by a guestbook requirement"
                            )
                            raise GuestbookRequired(
                                (message or "This dataset requires a Guestbook response.")
                                + " Reload the dataset metadata so the download "
                                "window can show the guestbook fields, then try again."
                            )
                        self._last_download_error = (
                            f"{message or 'The dataset or version was not found.'} "
                            f"(HTTP {response.status_code})"
                        )
                        get_app_log().info(
                            f"Download {label} not available ({response.status_code}): "
                            f"{message or 'no server message'}"
                        )
                        return None
                    log_response("GET", str(response.url), response.status_code, 0, "streaming…")
                    response.raise_for_status()
                    # Pre-flight disk-space check when the server advertises size.
                    try:
                        total_hdr = response.headers.get("Content-Length")
                        if total_hdr:
                            need = int(total_hdr)
                            free = __import__("shutil").disk_usage(str(dest.parent)).free
                            if need and free < need:
                                raise OSError(
                                    f"insufficient disk space for {label}: "
                                    f"need {need} bytes, {free} free"
                                )
                    except (TypeError, ValueError):
                        pass
                    received = 0
                    with open(dest, "wb") as handle:
                        for chunk in response.iter_content(chunk_size=_STREAM_CHUNK):
                            if not chunk:
                                continue
                            if is_cancelled and is_cancelled():
                                raise DownloadCancelled(label)
                            handle.write(chunk)
                            received += len(chunk)
                            if progress:
                                try:
                                    progress(received)
                                except Exception:
                                    pass
                elapsed_ms = int((time.monotonic() - start) * 1000)
                get_app_log().info(f"Downloaded {received} bytes in {elapsed_ms} ms ({label})")
                return received
            except requests.HTTPError as exc:
                resp = getattr(exc, "response", None)
                if resp is not None and resp.status_code in (401, 403):
                    raise
                if resp is not None and resp.status_code in (400, 404):
                    get_app_log().info(f"Download {label} failed ({resp.status_code}), trying next")
                    return None
                delay = _throttle_delay(exc)
                if delay is not None and attempt < 2:
                    wait = delay or 1.5 * (attempt + 1)
                    get_app_log().error(f"Download {label} throttled, retrying in {wait:.1f}s (attempt {attempt + 1}/3)")
                    time.sleep(wait)
                    continue
                raise
            except _RETRYABLE_NETWORK as exc:
                get_app_log().error(f"Download {label} network error (attempt {attempt + 1}/3): {exc}")
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise
        raise requests.ConnectionError(f"Download {label} failed after 3 attempts")  # pragma: no cover

    def _stream_download(
        self,
        path: str,
        params: dict[str, str],
        dl_headers: dict[str, str],
        dest: Path,
        progress: Callable[[int], None] | None,
        label: str,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> int | None:
        """Stream an API path (one version attempt) — see _stream_url."""
        return self._stream_url(
            self._api(path), params, dl_headers, dest, progress, label, is_cancelled
        )

    def _guestbook_signed_url(
        self, identifier: str, guestbook_response: dict[str, Any]
    ) -> str:
        """POST a guestbook response and return Dataverse's signed download URL.

        Dataverse never streams the bundle for a guestbook-protected dataset
        directly: POSTing the answers records the response and answers with
        ``{"data": {"signedUrl": "..."}}``; the signed URL then streams the
        ZIP (it carries ``gbrecs=true``/``gbrids=...``). The POST requires an
        API token, so a guestbook cannot be answered without one.
        """
        if not self._api_token:
            raise requests.HTTPError(
                "This dataset requires a guestbook response, which needs a "
                "Dataverse API token. Add one in Settings (Ctrl+,)."
            )
        by_pid = ":" in identifier
        path = "/api/access/dataset/:persistentId" if by_pid else f"/api/access/dataset/{identifier}"
        params = {"persistentId": identifier} if by_pid else {}
        headers = {
            "X-Dataverse-key": self._api_token,
            "Content-Type": "application/json",
        }
        response = self._session.post(
            self._api(path),
            params=params,
            headers=headers,
            json={"guestbookResponse": guestbook_response or {}},
            timeout=self._timeout,
        )
        try:
            if response.status_code == 400:
                message = _error_message(response)
                raise requests.HTTPError(
                    "Dataverse rejected the guestbook response: "
                    + (message or "a required answer is missing.")
                )
            response.raise_for_status()
            payload = response.json()
        finally:
            try:
                response.close()
            except Exception:
                pass
        data = payload.get("data") if isinstance(payload, dict) else None
        signed = data.get("signedUrl") if isinstance(data, dict) else None
        if not signed:
            raise requests.HTTPError(
                "Dataverse accepted the guestbook response but returned no "
                "download link. Try downloading from the dataset's web page."
            )
        get_app_log().info("Guestbook accepted — streaming the signed download URL")
        return str(signed)

    def download_dataset_zip(
        self,
        identifier: str,
        dest: Path,
        version: str = "draft",
        progress: Callable[[int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
        guestbook_response: dict[str, Any] | None = None,
    ) -> Path:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Access API expects plain version name (draft/latest) without colon; keep original case for dataset.xhtml but API is lower
        # Use Accept: */* for zip download (application/json causes 406)
        dl_headers = {}
        if self._api_token:
            dl_headers["X-Dataverse-key"] = self._api_token
        access_version = version.lstrip(":").lower()
        by_pid = ":" in identifier
        self._last_download_error = ""
        if guestbook_response is not None:
            # Answering the guestbook is a separate exchange: POST the answers,
            # then stream the signed URL. Version fallback does not apply (the
            # POST endpoint already picks the draft when the token may see it).
            signed_url = self._guestbook_signed_url(identifier, guestbook_response)
            if self._stream_url(
                signed_url, {}, {}, dest, progress, "guestbook", is_cancelled
            ) is not None:
                return dest
            detail = getattr(self, "_last_download_error", "") or "the bundle was not found"
            raise requests.HTTPError(f"Dataset bundle download failed: {detail}.")
        # Try requested version, fall back to latest if not found
        for ver in (access_version, "latest"):
            params = {"persistentId": identifier, "version": ver} if by_pid else {"version": ver}
            path = "/api/access/dataset/:persistentId" if by_pid else f"/api/access/dataset/{identifier}"
            if self._stream_download(path, params, dl_headers, dest, progress, f"version {ver}", is_cancelled) is not None:
                return dest
        # final attempt without version
        path = "/api/access/dataset/:persistentId" if by_pid else f"/api/access/dataset/{identifier}"
        params = {"persistentId": identifier} if by_pid else {}
        if self._stream_download(path, params, dl_headers, dest, progress, "unversioned", is_cancelled) is None:
            detail = getattr(self, "_last_download_error", "") or "the dataset or version was not found"
            raise requests.HTTPError(
                f"Dataset bundle download failed: {detail}. Check that the dataset "
                "exists on this Dataverse and that the API token can access it."
            )
        return dest

    def get_tabular_ingest_status(self, file_id: str) -> dict[str, Any]:
        """Tabular ingest status for one file (GET /api/files/{id}/ingestStatus).

        Returns {"status": str, "error": str} with "" on unavailable/failed
        calls — never raises (ingest status is advisory UI data).
        """
        try:
            payload = self._get_json(f"/api/files/{file_id}/ingestStatus")
        except Exception:
            return {"status": "", "error": ""}
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return {"status": "", "error": ""}
        status = str(
            data.get("status") or data.get("ingestStatus") or data.get("state") or ""
        )
        error = str(
            data.get("errorMessage")
            or data.get("error")
            or data.get("ingestError")
            or ""
        )
        return {"status": status, "error": error}

    def download_datafile_original(
        self,
        file_id: str,
        dest: Path,
        progress: Callable[[int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> Path:
        """Download one file in its ORIGINAL uploaded format.

        Tabular ingests are served as generated .tab by default; passing
        ?format=original returns the depositor's upload (e.g. .sav). Raises
        RuntimeError when unavailable so callers can skip the file.
        `is_cancelled` is polled before each attempt and per chunk; a True
        answer raises DownloadCancelled, which is never retried.
        """
        from applog import log_response

        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dl_headers: dict[str, str] = {"Accept": "*/*"}
        if self._api_token:
            dl_headers["X-Dataverse-key"] = self._api_token
        if is_cancelled and is_cancelled():
            raise DownloadCancelled(f"datafile {file_id}")
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                start = time.monotonic()
                with self._session.get(
                    self._api(f"/api/access/datafile/{file_id}"),
                    params={"format": "original"},
                    headers=dl_headers,
                    stream=True,
                    timeout=self._timeout,
                ) as response:
                    if response.status_code in (400, 401, 403, 404):
                        raise RuntimeError(
                            f"original format unavailable for file {file_id} "
                            f"({response.status_code})"
                        )
                    log_response("GET", str(response.url), response.status_code, 0, "streaming original…")
                    try:
                        response.raise_for_status()
                    except requests.HTTPError as http_exc:
                        # Honor Retry-After on throttle / transient overload.
                        delay = _throttle_delay(http_exc)
                        if delay is not None and attempt < 2:
                            wait = delay or 1.5 * (attempt + 1)
                            get_app_log().error(
                                f"GET datafile/{file_id} throttled, retrying in "
                                f"{wait:.1f}s (attempt {attempt + 1}/3)"
                            )
                            time.sleep(wait)
                            # Retry without truncating a prior partial twice:
                            # loop re-opens dest with "wb".
                            raise _RetryOriginal() from None
                        raise
                    received = 0
                    with open(dest, "wb") as handle:
                        for chunk in response.iter_content(chunk_size=_STREAM_CHUNK):
                            if not chunk:
                                continue
                            if is_cancelled and is_cancelled():
                                raise DownloadCancelled(f"datafile {file_id}")
                            handle.write(chunk)
                            received += len(chunk)
                            if progress:
                                try:
                                    progress(received)
                                except Exception:
                                    pass
                elapsed_ms = int((time.monotonic() - start) * 1000)
                get_app_log().info(f"Downloaded original ({received} bytes) in {elapsed_ms} ms")
                return dest
            except RuntimeError:
                raise
            except _RetryOriginal:
                last_exc = RuntimeError("throttled")
                continue
            except _RETRYABLE_NETWORK as exc:
                last_exc = exc
                get_app_log().error(f"GET datafile/{file_id} network error (attempt {attempt + 1}/3): {exc}")
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise RuntimeError(f"original-format download failed for file {file_id}: {exc}") from exc
        assert last_exc is not None
        raise RuntimeError(f"original-format download failed for file {file_id}: {last_exc}")

    @staticmethod
    def hash_file(path: Path, algorithm: str) -> str:
        digest = hashlib.new(algorithm)
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(_STREAM_CHUNK), b""):
                digest.update(chunk)
        return digest.hexdigest()
