"""Dataverse Native API client with crawler-based discovery.

Discovery delegates to the dataverse-metadata-crawler CLI (its internal
imports are not import-safe as a library across releases, so we drive the
stable CLI surface). In-review status is confirmed per dataset via the
locks endpoint. See docs/dataverse-integration.md for endpoints and auth.

All requests/responses are recorded in an in-memory log (see applog.py)
which the UI can display.
"""

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests

from applog import get_app_log

_STREAM_CHUNK = 1 << 20

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


def _dvmeta_available() -> bool:
    if getattr(sys, "frozen", False):
        return False
    spec = importlib.util.find_spec("dvmeta.main")
    return spec is not None and spec.origin is not None


def _dvmeta_cli_path() -> Path:
    spec = importlib.util.find_spec("dvmeta.main")
    if spec is None or not spec.origin:
        raise RuntimeError(
            "dataverse-metadata-crawler is not installed "
            "(pip install git+https://github.com/scholarsportal/"
            "dataverse-metadata-crawler.git)"
        )
    return Path(spec.origin)


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


def parse_ds_metadata_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse a dvmeta ds_metadata_*.json export into normalized datasets."""
    datasets: list[dict[str, Any]] = []
    for entry in payload.values():
        if not isinstance(entry, dict):
            continue
        data = entry.get("data")
        if not isinstance(data, dict):
            continue
        version = data.get("datasetVersion")
        if not isinstance(version, dict):
            continue
        files = normalize_files(version)
        # collection from dvmeta is not directly in version; try data fields
        collection = data.get("ownerName") or data.get("dataverseAlias") or ""
        depositor_val = _field_value(version, "depositor")
        depositor = depositor_val if isinstance(depositor_val, str) else ""
        if not depositor:
            # sometimes depositor is in dataset-level fields
            depositor = data.get("depositorName") or ""
        datasets.append(
            {
                "persistent_id": (
                    data.get("datasetPersistentId")
                    or data.get("persistentId")
                    or ""
                ),
                "title": extract_title(version),
                "contact": _extract_contact(version),
                "depositor": depositor,
                "date_created": (version.get("createTime") or "")[:10],
                "date_published": (data.get("publicationDate") or version.get("lastUpdateTime") or "")[:10],
                "collection": collection,
                "state": version.get("versionState", ""),
                "file_count": len(files),
                "total_size_bytes": sum(f["size_bytes"] for f in files),
                "files": files,
            }
        )
    return datasets


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
        return "In Review", True
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

_METADATABLOCKS_MEMO: dict[tuple, list[dict[str, str]]] = {}
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


def parse_metadatablock_fields(payload: dict[str, Any]) -> list[dict[str, str]]:
    """[{block, field, label}] from a GET /api/metadatablocks/{name} payload.

    Field map lives under data.metadataFields on older servers and under
    data.fields (dict keyed by field name, or a list) on newer ones
    (verified on 6.8: {"name": ..., "fields": {"geographicCoverage":
    {"name": ..., "displayName": ...}}}). Missing/unknown shapes yield [].
    """
    out: list[dict[str, str]] = []
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
                out.append({"block": block or "citation", "field": fname.strip(), "label": label.strip() or fname.strip()})
        elif isinstance(fields, list):
            for spec in fields:
                if not isinstance(spec, dict):
                    continue
                fname = str(spec.get("name") or spec.get("typeName") or "").strip()
                if not fname:
                    continue
                label = str(spec.get("displayName") or spec.get("displayname") or fname)
                out.append({"block": block or "citation", "field": fname, "label": label})
    except Exception:
        pass
    return out


def get_cached_metadata_fields(base_url: str) -> list[dict[str, str]] | None:
    try:
        with _METADATABLOCKS_LOCK:
            hit = _METADATABLOCKS_MEMO.get((_metadatablocks_disk_key(base_url),))
        return [dict(f) for f in hit] if hit is not None else None
    except Exception:
        return None


def set_cached_metadata_fields(base_url: str, fields: list[dict[str, str]]) -> None:
    try:
        clean = [dict(f) for f in (fields or []) if isinstance(f, dict) and f.get("field")]
        with _METADATABLOCKS_LOCK:
            _METADATABLOCKS_MEMO[(_metadatablocks_disk_key(base_url),)] = clean
    except Exception:
        pass


def read_metadata_fields_cache(workspace, base_url: str) -> list[dict[str, str]] | None:
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
                body = None
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
                return response.json()
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
                return response.text
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

    def _crawl(self, subtree: str, workdir: Path | None = None) -> Path:
        """Run the dvmeta CLI at version=draft; returns the export JSON path.

        When `workdir` is None a temp dir is created. It is intentionally
        NOT auto-deleted here because the caller reads the export file
        afterwards — see `list_draft_datasets` which cleans up auto-created
        dirs after parsing.
        """
        auto_created = workdir is None
        workdir = Path(workdir or tempfile.mkdtemp(prefix="dvmeta-"))
        workdir.mkdir(parents=True, exist_ok=True)
        # Tag auto-created dirs so the caller can clean them up.
        try:
            (workdir / ".dvmeta-auto-tmp").touch(exist_ok=True) if auto_created else None
        except OSError:
            pass
        command = [
            sys.executable,
            str(_dvmeta_cli_path()),
            "-c",
            subtree or "root",
            "-v",
            "draft",
            "-d",
            "--no-log",
        ]
        env = dict(os.environ)
        env["BASE_URL"] = self._base_url.rstrip("/") + "/"
        # SECURITY: API_KEY is visible in the child's environment to same-user
        # process inspectors for the crawl duration (up to timeout below).
        # Prefer DATAVERSE_API_TOKEN env-only (no config.json) when crawling
        # untrusted machines. Full fix needs dvmeta stdin/file key support.
        env["API_KEY"] = self._api_token or "none"
        completed = subprocess.run(
            command,
            cwd=str(workdir),
            env=env,
            capture_output=True,
            text=True,
            timeout=3600,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"dvmeta crawl failed: {completed.stderr[-2000:]}"
            )
        exports = sorted(
            (workdir / "exported_files" / "json_files").glob(
                "ds_metadata_*.json"
            )
        )
        if not exports:
            raise RuntimeError("dvmeta produced no ds_metadata export")
        return exports[-1]

    def _search_fallback(self, subtree: str = "", per_page: int = 100, start: int = 0) -> list[dict[str, Any]]:
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
        items = payload.get("data", {}).get("items", [])
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
                    # as "—") rather than a misleading 0. The dvmeta path and
                    # the download quote provide real sums.
                    "total_size_bytes": None,
                    "files": [],
                }
            )
        return datasets

    def list_draft_datasets(
        self, subtree: str = "", workdir: Path | None = None, max_pages: int = 10
    ) -> list[dict[str, Any]]:
        """All draft datasets in the subtree (superset of in-review).

        Uses the dvmeta crawler when available (dev installs); in the
        frozen portable build or when dvmeta is absent, paginates through
        the native Search API so the dashboard gets ALL datasets.
        """
        if _dvmeta_available():
            export_path = None
            auto_tmp = workdir is None
            try:
                export_path = self._crawl(subtree, workdir)
                # Guard huge exports: stream-parse size check before full load.
                try:
                    if export_path.stat().st_size > 200 << 20:
                        get_app_log().error(
                            f"dvmeta export {export_path.stat().st_size} bytes exceeds "
                            "200MB cap — falling back to Search API"
                        )
                        raise ValueError("dvmeta export too large")
                except OSError:
                    pass
                payload = json.loads(export_path.read_text(encoding="utf-8"))
                return parse_ds_metadata_payload(payload)
            except Exception as exc:
                get_app_log().error(f"dvmeta crawl failed ({exc}) — falling back to Search API")
            finally:
                # Clean up auto-created temp dirs (success or Search-fallback).
                if auto_tmp and export_path is not None:
                    try:
                        import shutil

                        tmp_root = export_path.parents[2] if len(export_path.parents) >= 3 else export_path.parent
                        # Only delete dirs we created (marker file present).
                        if (tmp_root / ".dvmeta-auto-tmp").exists():
                            shutil.rmtree(tmp_root, ignore_errors=True)
                    except Exception:
                        pass
        all_datasets: list[dict[str, Any]] = []
        seen: dict[str, int] = {}
        hit_page_cap = False
        for page in range(1, max_pages + 1):
            start = (page - 1) * 100
            batch = self._search_fallback(subtree, per_page=100, start=start)
            if not batch:
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
            get_app_log().info(f"Search page {page} (start={start}): {len(batch)} item(s), {new} new, cumulative {len(all_datasets)}")
            if len(batch) < 100:
                break
            if page == max_pages:
                # Full pages all the way to the cap: the tail is silently
                # cut. Say so loudly instead of pretending N is the total.
                hit_page_cap = True
        if hit_page_cap:
            get_app_log().error(
                f"Search hit the {max_pages * 100}-dataset page cap — results are "
                "TRUNCATED. Narrow the collection/subtree and refresh."
            )
        get_app_log().info(f"Search complete: {len(all_datasets)} dataset(s){' (TRUNCATED — see above)' if hit_page_cap else ''}")
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
        self, subtree: str = "", workdir: Path | None = None
    ) -> list[dict[str, Any]]:
        """Drafts from the crawl, kept only when locked IN_REVIEW."""
        drafts = self.list_draft_datasets(subtree, workdir)
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

    def get_metadatablock_fields(self, block: str) -> list[dict[str, str]]:
        """[{block, field, label}] for one block ([] when unavailable)."""
        try:
            payload = self._get_json(f"/api/metadatablocks/{block}")
        except Exception:
            return []
        return parse_metadatablock_fields(payload)

    def fetch_metadata_field_catalog(self) -> list[dict[str, str]]:
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
        return payload.get("data", {})

    def get_file_inventory(
        self, identifier: str, version: str = "draft"
    ) -> list[dict[str, Any]]:
        # Try draft first (with correct lowercase ":draft"), fall back to
        # :latest for published datasets. Auth failures (401/403) fail fast
        # — retrying other versions would mask a bad token and risk running
        # checks on the wrong version silently.
        tried: list[str] = []
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
                data = payload.get("data", {})
                # Dataverse versions API puts files at data.files (not data.datasetVersion.files)
                version_data = data.get("datasetVersion") or data
                # files may be at version_data.files or data.files
                if not version_data.get("files") and data.get("files"):
                    version_data = {"files": data.get("files", [])}
                if api_version != f":{version.lstrip(':').lower()}":
                    get_app_log().error(
                        f"Inventory for {identifier}: requested :{version} "
                        f"unavailable, using {api_version} (tried {tried}) — "
                        "verify you are reviewing the intended version"
                    )
                return normalize_files(version_data)
            except requests.HTTPError as exc:
                resp = getattr(exc, "response", None)
                status = resp.status_code if resp is not None else 0
                tried.append(f"{api_version}={status}")
                if status in (401, 403):
                    # Auth failure: do not silently try other versions.
                    raise
                if status in (400, 404):
                    get_app_log().info(f"Version {api_version} not available for {identifier} ({status}), trying next")
                    continue
                raise
        # fallback: try without version (latest published)
        payload = self._get_json(
            "/api/datasets/:persistentId" if ":" in identifier else f"/api/datasets/{identifier}",
            params={"persistentId": identifier} if ":" in identifier else None,
        )
        # dataset metadata contains latestVersion files? try to extract
        data = payload.get("data", {})
        version_data = data.get("latestVersion") or {}
        return normalize_files(version_data)

    # -- download ------------------------------------------------------------

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
        """One version attempt of a streaming download, with retries.

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
                    self._api(path),
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
                        get_app_log().info(f"Download {label} not available ({response.status_code}), trying next")
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

    def download_dataset_zip(
        self,
        identifier: str,
        dest: Path,
        version: str = "draft",
        progress: Callable[[int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
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
            raise requests.HTTPError("Dataset bundle download not available (404)")
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