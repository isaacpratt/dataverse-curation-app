"""Dashboard cache: slot keys, row fingerprints, diffing and persistence.

Qt-free by design: the dashboard's cache logic is pure data handling, so it
lives here rather than in ``ui/dashboard.py`` (which imports PySide6). The
engine tests exercise this module directly and stay out of the view layer —
that is what keeps the engine test suite free of Qt (dv-hcg.26).

``ui/dashboard.py`` imports these helpers and re-exports the two private
names it has always used, so nothing in the view layer changed.

None of these functions raise: the dashboard must survive a corrupt cache,
a half-written file or a malformed row.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

DASHBOARD_CACHE_NAME = "dashboard_cache.json"

# Cache-slot token for "no collection selected". Internal and deliberately
# untranslated: it keys the on-disk cache, it is never shown to the user
# (the interface wording is ``dashboard.status.whole_repository``).
CACHE_SLOT_ALL_COLLECTIONS = "whole repository"

# How many collection slots the on-disk cache keeps (10 collections x their
# full row sets is the working assumption).
_MAX_CACHE_SLOTS = 10


def dashboard_cache_key(base_url: str, collection: str) -> str:
    """Cache slot per instance + collection (both normalized, never raises)."""
    try:
        base = (base_url or "").rstrip("/").lower()
        coll = (collection or "").strip().lower() or CACHE_SLOT_ALL_COLLECTIONS
        return f"{base}|{coll}"
    except Exception:
        return "default"


def dataset_fingerprint(ds: dict[str, Any]) -> tuple[Any, ...]:
    """Server-meaningful identity of a row (local enrichment excluded).

    downloaded_at / total_size_bytes / size_from_cache are filled in from
    disk after the crawl, so they must NOT count as changes — otherwise
    every refresh would report every row as updated.
    """
    try:
        statuses = ds.get("publication_statuses") or []
        statuses = tuple(str(s or "") for s in statuses)
    except Exception:
        statuses = ()
    return (
        str(ds.get("title") or ""),
        str(ds.get("contact") or ""),
        str(ds.get("depositor") or ""),
        str(ds.get("date_created") or ""),
        str(ds.get("date_published") or ""),
        str(ds.get("collection") or ""),
        str(ds.get("state") or ""),
        bool(ds.get("has_draft")),
        statuses,
        str(ds.get("file_count") or ""),
        str(ds.get("curation_label") or ""),
        str(ds.get("curation_time") or ""),
        str(ds.get("curation_assigner") or ""),
    )


def diff_dashboard_datasets(
    old: list[dict[str, Any]], new: list[dict[str, Any]]
) -> dict[str, list[str]]:
    """Diff two crawls by persistent_id → {added, removed, changed} pid lists.

    Never raises; corrupt rows are compared by fingerprint best-effort.
    """
    try:
        old_map = {str(d.get("persistent_id") or ""): d for d in (old or []) if isinstance(d, dict)}
        new_map = {str(d.get("persistent_id") or ""): d for d in (new or []) if isinstance(d, dict)}
        old_map.pop("", None)
        new_map.pop("", None)
        added = [pid for pid in new_map if pid not in old_map]
        removed = [pid for pid in old_map if pid not in new_map]
        changed = []
        for pid in old_map:
            if pid in new_map:
                try:
                    if dataset_fingerprint(old_map[pid]) != dataset_fingerprint(new_map[pid]):
                        changed.append(pid)
                except Exception:
                    continue
        return {"added": added, "removed": removed, "changed": changed}
    except Exception:
        return {"added": [], "removed": [], "changed": []}


def merge_enriched_rows(  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
    existing: list[dict[str, Any]], batch: list[dict[str, Any]]
) -> int:
    """Patch worker enrichment batches into painted rows, matched by pid.

    Copies scalars only (the worker keeps its live dicts for the final
    finished() payload). An "In Review" lock confirmation is never
    clobbered by an enrichment state, and a live enriched size wins over a
    stale disk-cache fill. Returns the merged count; never raises.
    """
    try:
        by_pid: dict[str, dict[str, Any]] = {}
        for d in existing or []:
            if not isinstance(d, dict):
                continue
            try:
                pid = str(d.get("persistent_id") or "")
            except Exception:
                continue
            if pid:
                by_pid[pid] = d
        merged = 0
        for src in batch or []:
            if not isinstance(src, dict):
                continue
            try:
                pid = str(src.get("persistent_id") or "")
            except Exception:
                continue
            dst = by_pid.get(pid) if pid else None
            if dst is None:
                continue
            try:
                for key in (
                    "total_size_bytes",
                    "file_count",
                    "depositor",
                    "state",
                    "has_draft",
                    "size_enriched",
                ):
                    if key not in src:
                        continue
                    if key == "state" and "REVIEW" in str(dst.get("state") or "").upper():
                        continue
                    dst[key] = src[key]
                if src.get("size_enriched"):
                    try:
                        dst.pop("size_from_cache", None)
                    except Exception:
                        pass
                merged += 1
            except Exception:
                continue
        return merged
    except Exception:
        return 0


def load_dashboard_cache(workspace: Path, key: str) -> dict[str, Any] | None:
    """Load cached {saved_at, datasets, labels} for one instance+collection slot.

    Returns None when missing/corrupt — never raises.
    """
    try:
        path = Path(workspace) / DASHBOARD_CACHE_NAME
        if not path.exists():
            return None
        import json as _json

        raw = _json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None
        entry = raw.get(key)
        if not isinstance(entry, dict):
            return None
        datasets = entry.get("datasets")
        labels = entry.get("labels", [])
        if not isinstance(datasets, list) or not isinstance(labels, list):
            return None
        return {
            "saved_at": str(entry.get("saved_at") or ""),
            "datasets": [d for d in datasets if isinstance(d, dict)],
            "labels": [str(lbl) for lbl in labels if str(lbl).strip()],
        }
    except Exception:
        return None


def save_dashboard_cache(
    workspace: Path, key: str, datasets: list[dict[str, Any]], labels: list[Any]
) -> None:
    """Persist one dashboard slot (best-effort, never raises).

    Strips per-row `_sort_*` caches and caps stored slots to avoid unbounded
    growth (up to 10 collections × their full row sets).
    """
    try:
        import datetime as _dt
        import json as _json
        import os
        import tempfile

        path = Path(workspace) / DASHBOARD_CACHE_NAME
        try:
            raw = _json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except Exception:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        clean_rows = []
        for d in datasets or []:
            if not isinstance(d, dict):
                continue
            clean_rows.append({k: v for k, v in d.items() if not k.startswith("_sort_")})
        raw[key] = {
            "saved_at": _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"),
            "datasets": clean_rows,
            "labels": [str(lbl) for lbl in (labels or []) if str(lbl).strip()],
        }
        # Prune oldest slots beyond 10 to bound file size.
        try:
            if len(raw) > _MAX_CACHE_SLOTS:
                # Keep current key + 9 most recent by saved_at.
                items = sorted(
                    raw.items(),
                    key=lambda kv: str((kv[1] or {}).get("saved_at") or ""),
                    reverse=True,
                )
                raw = dict(items[:_MAX_CACHE_SLOTS])
                if key not in raw:
                    raw[key] = {
                        "saved_at": _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"),
                        "datasets": clean_rows,
                        "labels": [str(lbl) for lbl in (labels or []) if str(lbl).strip()],
                    }
        except Exception:
            pass
        path.parent.mkdir(parents=True, exist_ok=True)
        data = _json.dumps(raw, indent=2)
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(data)
            os.replace(tmp_name, path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
    except Exception:
        return
