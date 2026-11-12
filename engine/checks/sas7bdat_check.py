"""SAS dataset inspection (.sas7bdat and .xpt transport files).

Port of CUR_Res_CurationTools Scripts/Inspect_sas7bdat_Script.R: header-based
format detection, data dictionary extraction (variable names, labels, types,
value labels) and a non-ASCII encoding scan over character columns.
"""

from pathlib import Path

from engine.checks.base import Check, CheckResult

_XPORT_MAGIC = b"HEADER RECORD*******LIBRARY HEADER RECORD"
_SAS7BDAT_MAGIC = b"SAS FILE"
_ROW_LIMIT = 100
_MAX_UNLABELED_LISTED = 20
_MAX_VARIABLES_LISTED = 200


def _detect_format(path: Path) -> str:
    with open(path, "rb") as handle:
        header = handle.read(128)
    if header.startswith(_XPORT_MAGIC):
        return "xport"
    if _SAS7BDAT_MAGIC in header:
        return "sas7bdat"
    return "unknown"


def _read(path: Path, fmt: str):
    import pyreadstat

    # output_format="dict" keeps the check free of a pandas/polars runtime
    # dependency (pandas is deliberately not declared anywhere in this repo).
    if fmt == "xport":
        return pyreadstat.read_xport(str(path), row_limit=_ROW_LIMIT, output_format="dict")
    return pyreadstat.read_sas7bdat(str(path), row_limit=_ROW_LIMIT, output_format="dict")


def _has_non_ascii(frame) -> bool:
    for _column, values in frame.items():
        for value in values[:_ROW_LIMIT]:
            if isinstance(value, str):
                if any(ord(ch) > 127 for ch in value):
                    return True
            elif isinstance(value, bytes):
                try:
                    value.decode("ascii")
                except UnicodeDecodeError:
                    return True
    return False


class Sas7bdatCheck(Check):
    """SAS check - port of the CUR_Res_CurationTools R inspector."""

    check_id = "format.sas"
    extensions = {".sas7bdat", ".xpt"}

    def run(self, files: list[Path]) -> list[CheckResult]:
        # Per-file isolation like every other check (_detect_format opens the
        # file outside the guarded _read, so a raw OSError must not kill the
        # batch — run_per_file converts it to a finding).
        from engine.checks._util import run_per_file

        return run_per_file(self, files, self._run_one)

    def _run_one(self, path: Path) -> list[CheckResult]:
        try:
            import pyreadstat  # noqa: F401  ensure available before format detection
        except ImportError:
            from engine.checks._util import missing_library
            from engine.checks._util import skipped as _skipped

            return [
                _skipped(
                    "format.sas.format_detected",
                    f"{path.name}: format detection skipped (pyreadstat not installed)",
                ),
                missing_library("format.sas.openable", "pyreadstat"),
                _skipped(
                    "format.sas.dictionary",
                    f"{path.name}: dictionary skipped (pyreadstat not installed)",
                ),
                _skipped(
                    "format.sas.labels",
                    f"{path.name}: label scan skipped (pyreadstat not installed)",
                ),
                _skipped(
                    "format.sas.encoding",
                    f"{path.name}: encoding scan skipped (pyreadstat not installed)",
                ),
            ]
        name = path.name
        fmt = _detect_format(path)
        detected = CheckResult(
            check_id="format.sas.format_detected",
            level="info" if fmt != "unknown" else "warning",
            passed=fmt != "unknown",
            message=f"{name}: format {fmt}",
            details={"format": fmt},
        )

        try:
            frame, meta = _read(path, fmt)
        except Exception as exc:
            from engine.checks._util import skipped as _skipped2

            return [
                detected,
                CheckResult(
                    check_id="format.sas.openable",
                    level="error",
                    passed=False,
                    message=f"{name}: failed to read ({exc})",
                ),
                _skipped2(
                    "format.sas.dictionary",
                    f"{name}: dictionary skipped (unreadable file)",
                ),
                _skipped2(
                    "format.sas.labels",
                    f"{name}: label scan skipped (unreadable file)",
                ),
                _skipped2(
                    "format.sas.encoding",
                    f"{name}: encoding scan skipped (unreadable file)",
                ),
            ]

        labels = list(meta.column_labels or [])
        types = list(meta.original_variable_types or [])
        value_labels = getattr(meta, "variable_value_labels", None) or {}

        variables = []
        unlabeled = []
        columns = list(frame)
        for index, column in enumerate(columns):
            label = labels[index] if index < len(labels) else None
            var_type = types[index] if index < len(types) else "unknown"
            variables.append(
                {
                    "name": column,
                    "label": label or "",
                    "type": var_type,
                    "has_value_labels": column in value_labels,
                }
            )
            if not label:
                unlabeled.append(column)

        openable = CheckResult(
            check_id="format.sas.openable",
            level="info",
            passed=True,
            message=f"{name}: parsed (showing first {_ROW_LIMIT} rows)",
        )
        dictionary = CheckResult(
            check_id="format.sas.dictionary",
            level="info",
            passed=True,
            message=(
                f"{name}: {len(columns)} variables "
                f"({len(value_labels)} with value labels)"
            ),
            details={"variables": variables[:_MAX_VARIABLES_LISTED]},
        )
        labels_check = CheckResult(
            check_id="format.sas.labels",
            level="warning" if unlabeled else "info",
            passed=not unlabeled,
            message=(
                f"{name}: {len(unlabeled)} variable(s) without a label: "
                + ", ".join(unlabeled[:_MAX_UNLABELED_LISTED])
                + (" ..." if len(unlabeled) > _MAX_UNLABELED_LISTED else "")
                if unlabeled
                else f"{name}: all variables labelled"
            ),
        )
        encoding = CheckResult(
            check_id="format.sas.encoding",
            level="warning" if _has_non_ascii(frame) else "info",
            passed=not _has_non_ascii(frame),
            message=(
                f"{name}: character columns contain non-ASCII values"
                if _has_non_ascii(frame)
                else f"{name}: character columns are ASCII"
            ),
        )

        return [detected, openable, dictionary, labels_check, encoding]
