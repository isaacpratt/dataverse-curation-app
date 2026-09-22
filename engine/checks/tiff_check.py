"""TIFF inspection for scientific archiving.

Port of CUR_Res_CurationTools Scripts/Inspect_Tiff_Script.R: openability,
page/series structure, dimensions, data type and compression.
"""

from pathlib import Path

from engine.checks.base import Check, CheckResult


class TiffCheck(Check):
    """TIFF check - port of the CUR_Res_CurationTools R inspector."""

    check_id = "format.tiff"
    extensions = {".tif", ".tiff"}

    def run(self, files: list[Path]) -> list[CheckResult]:
        from engine.checks._util import run_per_file

        return run_per_file(self, files, self._run_one)

    def _run_one(self, path: Path) -> list[CheckResult]:
        try:
            import tifffile
        except ImportError:
            from engine.checks._util import missing_library

            return [missing_library("format.tiff.valid", "tifffile")]

        name = path.name
        with tifffile.TiffFile(str(path)) as tif:
            pages = len(tif.pages)
            if not pages:
                return [
                    CheckResult(
                        check_id="format.tiff.valid",
                        level="error",
                        passed=False,
                        message=f"{name}: TIFF with no pages",
                    )
                ]
            series_count = len(tif.series)
            first = tif.pages[0]
            shape = tuple(first.shape)
            dtype = str(first.dtype)
            compression = first.compression or "none"
            is_ome = tif.is_ome

        message = (
            f"{name}: {pages} page(s), {shape}, {dtype}, "
            f"compression={compression}"
        )
        if series_count > 1:
            message += f", {series_count} series"
        if is_ome:
            message += ", OME-TIFF"

        return [
            CheckResult(
                check_id="format.tiff.valid",
                level="info",
                passed=True,
                message=message,
                details={
                    "pages": pages,
                    "shape": list(shape),
                    "dtype": dtype,
                    "compression": str(compression),
                    "ome": is_ome,
                },
            )
        ]