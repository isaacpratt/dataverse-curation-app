"""Identity/labels/metadatablock caches for the client.

In-memory maps keyed by base_url + token fingerprint - never the token
itself - and best-effort disk persistence (metadatablocks_cache.json and
curation_labels.json). Write failures are logged and swallowed.
"""

import hashlib
import threading
from pathlib import Path
from typing import Any

from client.parsers import top_level_collection

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


def read_allowed_labels_cache(workspace, base_url: str, collection: str) -> list[str] | None:
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


def get_cached_metadata_fields(base_url: str) -> list[dict[str, Any]] | None:
    """Return the cached field catalog for a base URL, if present."""
    try:
        with _METADATABLOCKS_LOCK:
            hit = _METADATABLOCKS_MEMO.get((_metadatablocks_disk_key(base_url),))
        return [dict(f) for f in hit] if hit is not None else None
    except Exception:
        return None


def set_cached_metadata_fields(base_url: str, fields: list[dict[str, Any]]) -> None:
    """Persist the field catalog for a base URL (best effort)."""
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
