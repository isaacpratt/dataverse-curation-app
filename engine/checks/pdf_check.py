"""PDF archival inspection.

Port of CUR_Res_CurationTools Scripts/Inspect_PDF_Script.R: openability,
encryption state, page count and digital text presence (OCR is an optional
follow-up handled separately).
"""

from pathlib import Path
from typing import ClassVar

from engine.checks.base import Check, CheckResult

_MAX_PAGES_SAMPLED = 3


class PdfCheck(Check):
    """PDF check - port of the CUR_Res_CurationTools R inspector."""

    check_id = "format.pdf"
    extensions: ClassVar[set[str]] = {".pdf"}

    def run(self, files: list[Path]) -> list[CheckResult]:
        from engine.checks._util import run_per_file

        return run_per_file(self, files, self._run_one)

    def _run_one(self, path: Path) -> list[CheckResult]:
        try:
            from pypdf import PdfReader
        except ImportError:
            from engine.checks._util import missing_library
            from engine.checks._util import skipped as _skipped

            return [
                missing_library("format.pdf.openable", "pypdf"),
                _skipped(
                    "format.pdf.text",
                    f"{path.name}: text scan skipped (pypdf not installed)",
                ),
            ]

        name = path.name
        reader = PdfReader(str(path))
        try:
            if reader.is_encrypted:
                from engine.checks._util import skipped as _skipped2

                # Report encryption without touching .pages (accessing pages
                # on an encrypted file is version-dependent and can raise).
                return [
                    CheckResult(
                        check_id="format.pdf.openable",
                        level="warning",
                        passed=False,
                        message=f"{name}: encrypted PDF",
                    ),
                    _skipped2(
                        "format.pdf.text",
                        f"{name}: text scan skipped (encrypted PDF)",
                    ),
                ]

            # Sample the first few pages: a cover-only scan must not condemn
            # a 200-page text PDF (or vice versa).
            page_count = len(reader.pages)
            sampled = 0
            text_pages = 0
            for page in reader.pages:
                if sampled >= _MAX_PAGES_SAMPLED:
                    break
                sampled += 1
                if (page.extract_text() or "").strip():
                    text_pages += 1
        finally:
            try:
                stream = getattr(reader, "stream", None)
                if stream is not None:
                    stream.close()
            except Exception:
                pass

        results = [
            CheckResult(
                check_id="format.pdf.openable",
                level="info",
                passed=True,
                message=f"{name}: readable PDF ({page_count} pages)",
            )
        ]
        if text_pages:
            results.append(
                CheckResult(
                    check_id="format.pdf.text",
                    level="info",
                    passed=True,
                    message=(
                        f"{name}: digital text present ({text_pages}/{sampled} sampled page(s))"
                    ),
                )
            )
        else:
            results.append(
                CheckResult(
                    check_id="format.pdf.text",
                    level="warning",
                    passed=False,
                    message=(
                        f"{name}: no digital text on sampled page(s) - "
                        "scanned image? OCR recommended"
                    ),
                )
            )
        return results
