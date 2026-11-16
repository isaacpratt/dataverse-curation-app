"""Stata (.dta) inspection.

Port of CUR_Res_CurationTools Scripts/Inspect_dta_Script.R (metadata quality
and PII): dictionary extraction, label coverage, non-ASCII scan and a
structured-PII scan on character columns (piigex + CA pack).
"""

from pathlib import Path

from engine.checks._util import find_pii, pii_result
from engine.checks.base import Check, CheckResult

_ROW_LIMIT = 100
_MAX_UNLABELED_LISTED = 20
_MAX_VARIABLES_LISTED = 200


def _has_non_ascii(frame) -> bool:
    for column in frame.columns:
        for value in frame[column].dropna().head(_ROW_LIMIT):
            if isinstance(value, str) and any(ord(ch) > 127 for ch in value):
                return True
    return False


def _find_pii(frame) -> list:
    found = []
    for column in frame.columns:
        for value in frame[column].dropna().head(_ROW_LIMIT):
            if isinstance(value, str):
                found.extend(find_pii(value))
    seen = set()
    unique = []
    for item in found:
        key = (item["type"], item["value"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


class DtaCheck(Check):
    """Stata check - port of the CUR_Res_CurationTools R inspector."""

    check_id = "format.stata"
    extensions = {".dta"}

    def run(self, files: list[Path]) -> list[CheckResult]:
        from engine.checks._util import run_per_file

        return run_per_file(self, files, self._run_one)

    def _run_one(self, path: Path) -> list[CheckResult]:
        try:
            import pyreadstat
        except ImportError:
            from engine.checks._util import missing_library
            from engine.checks._util import skipped as _skipped

            return [
                missing_library("format.stata.openable", "pyreadstat"),
                _skipped(
                    "format.stata.dictionary",
                    f"{path.name}: dictionary skipped (pyreadstat not installed)",
                ),
                _skipped(
                    "format.stata.labels",
                    f"{path.name}: label scan skipped (pyreadstat not installed)",
                ),
                _skipped(
                    "format.stata.encoding",
                    f"{path.name}: encoding scan skipped (pyreadstat not installed)",
                ),
                _skipped(
                    "format.stata.pii",
                    f"{path.name}: PII scan skipped (pyreadstat not installed)",
                ),
            ]
        name = path.name
        try:
            frame, meta = pyreadstat.read_dta(str(path), row_limit=_ROW_LIMIT)
        except Exception as exc:
            from engine.checks._util import skipped as _skipped2

            return [
                CheckResult(
                    check_id="format.stata.openable",
                    level="error",
                    passed=False,
                    message=f"{name}: failed to read ({exc})",
                ),
                _skipped2(
                    "format.stata.dictionary",
                    f"{name}: dictionary skipped (unreadable file)",
                ),
                _skipped2(
                    "format.stata.labels",
                    f"{name}: label scan skipped (unreadable file)",
                ),
                _skipped2(
                    "format.stata.encoding",
                    f"{name}: encoding scan skipped (unreadable file)",
                ),
                _skipped2(
                    "format.stata.pii",
                    f"{name}: PII scan skipped (unreadable file)",
                ),
            ]

        labels = list(meta.column_labels or [])
        types = list(meta.original_variable_types or [])
        value_labels = getattr(meta, "variable_value_labels", None) or {}

        variables = []
        unlabeled = []
        for index, column in enumerate(frame.columns):
            label = labels[index] if index < len(labels) else None
            var_type = types[index] if index < len(types) else str(frame[column].dtype)
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
            check_id="format.stata.openable",
            level="info",
            passed=True,
            message=f"{name}: parsed (first {_ROW_LIMIT} rows)",
        )
        dictionary = CheckResult(
            check_id="format.stata.dictionary",
            level="info",
            passed=True,
            message=(
                f"{name}: {len(frame.columns)} variables ({len(value_labels)} with value labels)"
            ),
            details={"variables": variables[:_MAX_VARIABLES_LISTED]},
        )
        labels_check = CheckResult(
            check_id="format.stata.labels",
            level="warning" if unlabeled else "info",
            passed=not unlabeled,
            message=(
                (
                    f"{name}: {len(unlabeled)} variable(s) without a label: "
                    + ", ".join(unlabeled[:_MAX_UNLABELED_LISTED])
                )
                if unlabeled
                else f"{name}: all variables labelled"
            ),
        )
        encoding = CheckResult(
            check_id="format.stata.encoding",
            level="warning" if _has_non_ascii(frame) else "info",
            passed=not _has_non_ascii(frame),
            message=(
                f"{name}: character columns contain non-ASCII values"
                if _has_non_ascii(frame)
                else f"{name}: character columns are ASCII"
            ),
        )

        pii = pii_result(
            "format.stata.pii",
            name,
            _find_pii(frame),
            scope=f"first {_ROW_LIMIT} rows",
        )
        return [openable, dictionary, labels_check, encoding, pii]
