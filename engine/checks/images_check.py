"""Image quality control and fixity.

Port of CUR_Res_CurationTools Scripts/Inspect_Images_Script.R: open/verify,
dimensions, colour mode and format detection.
"""

from pathlib import Path
from typing import List

from engine.checks.base import Check, CheckResult


class ImagesCheck(Check):
    """Images check - port of the CUR_Res_CurationTools R inspector."""

    check_id = "format.images"
    extensions = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}

    def run(self, files: List[Path]) -> List[CheckResult]:
        from engine.checks._util import run_per_file

        return run_per_file(self, files, self._run_one)

    def _run_one(self, path: Path) -> List[CheckResult]:
        try:
            from PIL import Image, ImageFile
        except ImportError:
            from engine.checks._util import missing_library

            return [missing_library("format.images.valid", "Pillow")]

        name = path.name
        try:
            with Image.open(str(path)) as image:
                image.verify()
            with Image.open(str(path)) as image:
                width, height = image.size
                mode = image.mode
                fmt = image.format
        except ImageFile.TruncatedFileError:
            # Taxonomy (docs/checks-reference.md): unreadable image = error.
            return [
                CheckResult(
                    check_id="format.images.valid",
                    level="error",
                    passed=False,
                    message=f"{name}: truncated image data",
                )
            ]

        return [
            CheckResult(
                check_id="format.images.valid",
                level="info",
                passed=True,
                message=f"{name}: valid {fmt} image ({width}x{height}, {mode})",
                details={
                    "width": width,
                    "height": height,
                    "mode": mode,
                    "format": fmt,
                },
            )
        ]