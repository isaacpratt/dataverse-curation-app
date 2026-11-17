"""Dataverse client package - the Native/Search API client.

Public surface: ``curation.client`` re-exports everything the app and the
tests import; the implementation is split across focused modules. Layout:

- ``curation.client.constants`` - retry/backoff pools, stream chunk, state tokens
- ``curation.client.errors``    - _RetryOriginal, DownloadCancelled, GuestbookRequired
- ``curation.client.http``      - small HTTP helpers (_error_message, _throttle_delay)
- ``curation.client.parsers``   - pure payload parsers/normalizers (no network)
- ``curation.client.caches``    - identity/labels/metadatablock caches (memory + disk)
- ``curation.client.client``    - DataverseClient: session, retries, downloads, guestbook
"""

from typing import Any

from curation.client.caches import (
    _ALLOWED_LABELS_CACHE,
    _ALLOWED_LABELS_FILE,
    _ALLOWED_LABELS_LOCK,
    _ME_CACHE,
    _ME_LOCK,
    _METADATABLOCKS_FILE,
    _METADATABLOCKS_LOCK,
    _METADATABLOCKS_MEMO,
    _ROLE_CACHE,
    _allowed_labels_disk_key,
    _me_cache_key,
    _metadatablocks_disk_key,
    allowed_labels_cache_key,
    get_cached_allowed_labels,
    get_cached_metadata_fields,
    read_allowed_labels_cache,
    read_metadata_fields_cache,
    set_cached_allowed_labels,
    set_cached_metadata_fields,
    write_allowed_labels_cache,
    write_metadata_fields_cache,
)
from curation.client.client import DataverseClient
from curation.client.constants import (
    _REFUSAL_COMPARE,
    _REFUSAL_VERSIONS,
    _RETRYABLE_NETWORK,
    _RETRYABLE_STATUS,
    _STREAM_CHUNK,
    _VERSION_DRAFT,
    _VERSION_LATEST,
    _VERSION_PUBLISHED,
    STATE_IN_REVIEW,
)
from curation.client.errors import (
    DownloadCancelled,
    GuestbookRequired,
    _RetryOriginal,
)
from curation.client.http import (
    _error_message,
    _throttle_delay,
)
from curation.client.parsers import (
    _CURATION_NONE_VALUES,
    _DATE_RE,
    REVIEW_SUBMIT_TYPES,
    _clean_curation_value,
    _extract_contact,
    _field_value,
    _scan_restriction_dates,
    _summarize_file_entry,
    _summarize_version_data,
    _version_files_data,
    extract_file_restrictions,
    extract_title,
    is_draft_dataset,
    locks_indicate_review,
    normalize_files,
    note_review_submission,
    parse_allowed_labels,
    parse_curation_states_csv,
    parse_curation_status,
    parse_dataset_versions,
    parse_metadatablock_display_names,
    parse_metadatablock_fields,
    parse_metadatablock_names,
    parse_timestamps,
    parse_version_compare,
    search_item_state,
    top_level_collection,
)


def _refusal(path: str, status: int, body: str = "") -> tuple[str, str]:
    """Classify a 4xx answer: (machine code, explanation) or ("", "") when unexpected."""
    p = str(path or "").lower()
    text = str(body or "").lower()
    if status not in (400, 401, 403, 404):
        return "", ""
    is_versions = _REFUSAL_VERSIONS in p
    is_draft = "/versions/:draft" in p
    is_published = "/versions/:latest" in p
    is_compare = _REFUSAL_COMPARE in p
    is_curation = "curationstatus" in p
    is_labels = "allowedcurationlabels" in p
    says_missing = "not found" in text or "does not exist" in text

    if status in (401, 403):
        if says_missing and is_versions:
            if is_draft:
                return ("no_draft_version", "the dataset has no draft version")
            return ("no_published_version", "the dataset has no published version")
        if is_compare:
            return ("versions_not_readable", "this account may not compare versions")
        if is_draft or (is_versions and not is_published):
            return ("draft_not_readable", "this account may not read the draft version")
        if is_published:
            return ("version_not_readable", "this account may not read the published version")
        if is_curation:
            return ("not_under_curation", "curation status is readable only for datasets under curation")
        if is_labels:
            return ("labels_not_readable", "this account is not allowed to read curation labels")
        return "", ""
    if status == 400:
        return "", ""
    if is_compare:
        return ("no_versions_to_compare", "there is no published/draft version pair to compare")
    if is_draft:
        return ("no_draft_version", "the dataset has no draft version")
    if is_published:
        return ("no_published_version", "the dataset has no published version")
    if is_versions:
        return ("no_visible_versions", "the dataset has no visible versions")
    if is_curation:
        return ("not_under_curation", "the dataset is not under curation")
    if is_labels:
        return ("labels_unavailable", "this collection does not expose curation labels")
    return "", ""


def expected_api_reason(path: str, status: int, body: str = "") -> str:
    """Why a refusal from this endpoint is the documented answer ("" = a bug)."""
    try:
        return _refusal(path, status, body)[1]
    except Exception:
        return ""


def refusal_code(path: str, status: int, body: str = "") -> str:
    """Machine code for an expected refusal (empty when the answer is unexpected)."""
    try:
        return _refusal(path, status, body)[0]
    except Exception:
        return ""


def probe_skip_reason(ds: Any) -> str:
    """Why a version probe was skipped for this row (empty when nothing was skipped)."""
    try:
        if not isinstance(ds, dict):
            return ""
        if is_draft_dataset(ds):
            return ""
        state = str(ds.get("state") or "").upper()
        if state == "DEACCESSIONED":
            return (
                "the search payload lists this dataset as deaccessioned ??? its "
                "record answers, but it has no version to ask for"
            )
        return (
            "the search payload lists this dataset as published with no draft ??? "
            "the dataset read answers with the published version in one call"
        )
    except Exception:
        return ""


def version_probe_order(ds: Any) -> list[str]:
    """Which version specifiers to probe for a crawl row (empty = read the dataset once)."""
    try:
        if not isinstance(ds, dict):
            return []
        if is_draft_dataset(ds):
            return [_VERSION_DRAFT]
        return []
    except Exception:
        return []


__all__ = [
    "REVIEW_SUBMIT_TYPES",
    "STATE_IN_REVIEW",
    "_ALLOWED_LABELS_CACHE",
    "_ALLOWED_LABELS_FILE",
    "_ALLOWED_LABELS_LOCK",
    "_CURATION_NONE_VALUES",
    "_DATE_RE",
    "_METADATABLOCKS_FILE",
    "_METADATABLOCKS_LOCK",
    "_METADATABLOCKS_MEMO",
    "_ME_CACHE",
    "_ME_LOCK",
    "_RETRYABLE_NETWORK",
    "_RETRYABLE_STATUS",
    "_ROLE_CACHE",
    "_STREAM_CHUNK",
    "_VERSION_DRAFT",
    "_VERSION_LATEST",
    "_VERSION_PUBLISHED",
    "DataverseClient",
    "DownloadCancelled",
    "GuestbookRequired",
    "_RetryOriginal",
    "_allowed_labels_disk_key",
    "_clean_curation_value",
    "_error_message",
    "_extract_contact",
    "_field_value",
    "_me_cache_key",
    "_metadatablocks_disk_key",
    "_scan_restriction_dates",
    "_summarize_file_entry",
    "_summarize_version_data",
    "_throttle_delay",
    "_version_files_data",
    "allowed_labels_cache_key",
    "extract_file_restrictions",
    "extract_title",
    "get_cached_allowed_labels",
    "get_cached_metadata_fields",
    "is_draft_dataset",
    "locks_indicate_review",
    "normalize_files",
    "note_review_submission",
    "parse_allowed_labels",
    "parse_curation_states_csv",
    "parse_curation_status",
    "parse_dataset_versions",
    "parse_metadatablock_display_names",
    "parse_metadatablock_fields",
    "parse_metadatablock_names",
    "parse_timestamps",
    "parse_version_compare",
    "read_allowed_labels_cache",
    "read_metadata_fields_cache",
    "search_item_state",
    "set_cached_allowed_labels",
    "set_cached_metadata_fields",
    "top_level_collection",
    "write_allowed_labels_cache",
    "write_metadata_fields_cache",
]
