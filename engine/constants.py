"""Central caps and tuning constants for the check engine.

Previously scattered across csv/text/code/sav/dta/sas/json/extensions checks
and the UI — single source of truth for sample sizes, row caps, and parse
limits.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class EngineCaps:
    sample_bytes: int = 1 << 20
    # Secrets get a larger window than encoding/TODO scans (matches hush's
    # own 5 MiB file cap) without reading multi-GB renamed .txt blobs whole.
    secret_sample_bytes: int = 5 << 20
    sniff_bytes: int = 32 << 10
    max_rows_scanned: int = 50_000
    max_seen_rows: int = 20_000
    pii_sample_rows: int = 1_000
    # Cap objects embedded in CheckResult.details; the full count still
    # appears in the message and details.count (explicit truncation copy).
    secret_max_listed: int = 20
    pii_max_samples: int = 10
    row_limit_tabular: int = 100
    max_full_parse_bytes: int = 64 << 20
    max_members: int = 10_000
    max_uncompressed_bytes: int = 2 << 30
    max_entries_listed: int = 50
    max_objects_visited: int = 5_000
    max_items_listed: int = 200
    max_count_scan: int = 100_000
    fastq_reads_sampled: int = 1_000
    fastq_max_line_chars: int = 1_000_000
    max_image_pixels: int = 178_956_970


CAPS = EngineCaps()
