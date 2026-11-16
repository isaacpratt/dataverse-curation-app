"""Dataverse client package - implementation split out of dataverse_client.py.

Public surface is intentionally identical to the original module, and
``dataverse_client`` re-exports all of it; existing imports keep working.
Layout:

- ``client.constants`` - retry/backoff pools, stream chunk, state tokens
- ``client.errors``    - _RetryOriginal, DownloadCancelled, GuestbookRequired
- ``client.http``      - small HTTP helpers (_error_message, _throttle_delay)
- ``client.parsers``   - pure payload parsers/normalizers (no network)
- ``client.caches``    - identity/labels/metadatablock caches (memory + disk)
- ``client.client``    - DataverseClient: session, retries, downloads, guestbook
"""

from client.caches import (
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
from client.client import DataverseClient
from client.constants import (
    _RETRYABLE_NETWORK,
    _RETRYABLE_STATUS,
    _STREAM_CHUNK,
    STATE_IN_REVIEW,
)
from client.errors import (
    DownloadCancelled,
    GuestbookRequired,
    _RetryOriginal,
)
from client.http import (
    _error_message,
    _throttle_delay,
)
from client.parsers import (
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
