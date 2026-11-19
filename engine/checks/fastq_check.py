"""FASTQ validation and metadata extraction.

Port of CUR_Res_CurationTools Scripts/check_fastq.R (ShortRead): 4-line
record structure, sequence/quality length agreement, read lengths and GC
content on a sample. Transparently handles gzip-compressed files.
"""

import gzip
from pathlib import Path
from typing import ClassVar, TextIO

from engine.checks.base import Check, CheckResult

try:
    from engine.constants import CAPS as _CAPS

    _MAX_READS_SAMPLED = _CAPS.fastq_reads_sampled
    _MAX_LINE_CHARS = _CAPS.fastq_max_line_chars
except Exception:  # pragma: no cover
    _MAX_READS_SAMPLED = 1000
    _MAX_LINE_CHARS = 1_000_000


def _open_text(path: Path) -> TextIO:
    with open(path, "rb") as probe:
        magic = probe.read(2)
    if magic == b"\x1f\x8b":
        return gzip.open(str(path), "rt", encoding="ascii", errors="replace")
    return open(str(path), encoding="ascii", errors="replace")


class FastqCheck(Check):
    """FASTQ check - port of the CUR_Res_CurationTools R inspector."""

    check_id = "format.fastq"
    scope: ClassVar[str] = "file"
    extensions: ClassVar[set[str]] = {".fastq", ".fq"}

    def run(self, files: list[Path]) -> list[CheckResult]:
        from engine.checks._util import run_per_file

        return run_per_file(self, files, self._run_one)

    def _run_one(self, path: Path) -> list[CheckResult]:
        name = path.name
        reads = 0
        total_length = 0
        gc_count = 0
        bad_records = 0
        record: list[str] = []

        def _finish_record() -> None:
            """Validate one buffered 4-line record (header/seq/plus/qual)."""
            nonlocal reads, total_length, gc_count, bad_records
            if len(record) != 4:
                bad_records += 1
                return
            header, seq, plus, qual = record
            if not header.startswith("@") or not plus.startswith("+"):
                bad_records += 1
                return
            if len(seq) != len(qual):
                bad_records += 1
                return
            reads += 1
            total_length += len(seq)
            gc_count += sum(1 for ch in seq.upper() if ch in "GC")

        with _open_text(path) as handle:
            for raw_line in handle:
                # Line-length cap: a malformed single-line file must not
                # buffer GBs in one string.
                if len(raw_line) > _MAX_LINE_CHARS:
                    bad_records += 1
                    record = []
                    if reads >= _MAX_READS_SAMPLED:
                        break
                    continue
                record.append(raw_line.rstrip("\r\n"))
                if len(record) == 4:
                    _finish_record()
                    record = []
                    # Stop only on a record boundary — never mid-record.
                    if reads >= _MAX_READS_SAMPLED:
                        break
        if record:
            # Trailing partial record (truncated file tail).
            bad_records += 1

        if reads == 0:
            from engine.checks._util import skipped as _skipped

            return [
                CheckResult(
                    check_id="format.fastq.valid",
                    level="error",
                    passed=False,
                    message=f"{name}: no valid reads found",
                    details={"bad_records": bad_records},
                ),
                _skipped(
                    "format.fastq.metadata",
                    f"{name}: metadata skipped (no valid reads)",
                ),
            ]

        avg_length = total_length / reads
        gc_content = gc_count / total_length if total_length else 0.0
        results = [
            CheckResult(
                check_id="format.fastq.valid",
                level="warning" if bad_records else "info",
                passed=not bad_records,
                message=(
                    f"{name}: {bad_records} malformed record(s) in first {reads}"
                    if bad_records
                    else f"{name}: structure OK (first {reads} reads)"
                ),
            ),
            CheckResult(
                check_id="format.fastq.metadata",
                level="info",
                passed=True,
                message=(f"{name}: avg read length {avg_length:.1f}, GC {gc_content:.2%}"),
                details={
                    "reads_sampled": reads,
                    "avg_length": round(avg_length, 1),
                    "gc_content": round(gc_content, 4),
                },
            ),
        ]
        return results
