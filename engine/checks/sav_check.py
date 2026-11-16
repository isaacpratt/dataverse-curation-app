"""SPSS (.sav) inspection.

Port of CUR_Res_CurationTools Scripts/Inspect_sav_Script.R: dictionary
extraction (variable names, labels, types, value labels), label coverage and
a non-ASCII encoding scan.
"""

from pathlib import Path

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


class SavCheck(Check):
    """SPSS check - port of the CUR_Res_CurationTools R inspector."""

    check_id = "format.spss"
    extensions = {".sav"}

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
                missing_library("format.spss.openable", "pyreadstat"),
                _skipped(
                    "format.spss.dictionary",
                    f"{path.name}: dictionary skipped (pyreadstat not installed)",
                ),
                _skipped(
                    "format.spss.labels",
                    f"{path.name}: label scan skipped (pyreadstat not installed)",
                ),
                _skipped(
                    "format.spss.encoding",
                    f"{path.name}: encoding scan skipped (pyreadstat not installed)",
                ),
            ]
        name = path.name
        try:
            frame, meta = pyreadstat.read_sav(str(path), row_limit=_ROW_LIMIT)
        except Exception as exc:
            from engine.checks._util import skipped as _skipped2

            return [
                CheckResult(
                    check_id="format.spss.openable",
                    level="error",
                    passed=False,
                    message=f"{name}: failed to read ({exc})",
                ),
                _skipped2(
                    "format.spss.dictionary",
                    f"{name}: dictionary skipped (unreadable file)",
                ),
                _skipped2(
                    "format.spss.labels",
                    f"{name}: label scan skipped (unreadable file)",
                ),
                _skipped2(
                    "format.spss.encoding",
                    f"{name}: encoding scan skipped (unreadable file)",
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
            check_id="format.spss.openable",
            level="info",
            passed=True,
            message=f"{name}: parsed (first {_ROW_LIMIT} rows)",
        )
        dictionary = CheckResult(
            check_id="format.spss.dictionary",
            level="info",
            passed=True,
            message=(
                f"{name}: {len(frame.columns)} variables ({len(value_labels)} with value labels)"
            ),
            details={"variables": variables[:_MAX_VARIABLES_LISTED]},
        )
        labels_check = CheckResult(
            check_id="format.spss.labels",
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
            check_id="format.spss.encoding",
            level="warning" if _has_non_ascii(frame) else "info",
            passed=not _has_non_ascii(frame),
            message=(
                f"{name}: character columns contain non-ASCII values"
                if _has_non_ascii(frame)
                else f"{name}: character columns are ASCII"
            ),
        )
        return [openable, dictionary, labels_check, encoding]
