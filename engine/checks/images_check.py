"""Image quality control and fixity.

Port of CUR_Res_CurationTools Scripts/Inspect_Images_Script.R: open/verify,
dimensions, colour mode and format detection.

Pillow is preferred (full verify + mode detection). When Pillow is absent
(lite portable build without the sibling full folder, or offline dev venv)
a pure-stdlib header parser covers JPG/PNG/GIF/BMP/WEBP dimensions so common
images still validate instead of reporting "Missing".
"""

import struct
from pathlib import Path

from engine.checks.base import Check, CheckResult

# Cap header reads: dimensions live in the first bytes; never slurp GBs.
_STDLIB_HEADER_BYTES = 1 << 20


def _parse_png(data: bytes) -> tuple[int, int, str] | None:
    # 8-byte signature + IHDR chunk (width/height BE uint32).
    if len(data) < 33 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    try:
        if data[12:16] != b"IHDR":
            return None
        width, height = struct.unpack(">II", data[16:24])
        color_type = data[25]
        mode = {0: "L", 2: "RGB", 3: "P", 4: "LA", 6: "RGBA"}.get(color_type, "unknown")
        if not (0 < width <= 100000 and 0 < height <= 100000):
            return None
        return width, height, mode
    except Exception:
        return None


def _parse_gif(data: bytes) -> tuple[int, int, str] | None:
    if len(data) < 10 or data[:6] not in (b"GIF87a", b"GIF89a"):
        return None
    try:
        width, height = struct.unpack("<HH", data[6:10])
        if not (0 < width <= 100000 and 0 < height <= 100000):
            return None
        return width, height, "P"
    except Exception:
        return None


def _parse_bmp(data: bytes) -> tuple[int, int, str] | None:
    if len(data) < 30 or data[:2] != b"BM":
        return None
    try:
        width = struct.unpack("<i", data[18:22])[0]
        height = abs(struct.unpack("<i", data[22:26])[0])
        bitcount = struct.unpack("<H", data[28:30])[0]
        mode = {1: "P", 4: "P", 8: "P", 16: "RGB", 24: "RGB", 32: "RGBA"}.get(bitcount, "unknown")
        if not (0 < width <= 100000 and 0 < height <= 100000):
            return None
        return width, height, mode
    except Exception:
        return None


def _parse_jpeg(data: bytes) -> tuple[int, int, str] | None:
    # SOI + scan markers for SOFn (frame header holds dimensions).
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        return None
    sof_markers = {
        0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
        0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
    }
    try:
        pos = 2
        n = len(data)
        while pos + 4 <= n:
            if data[pos] != 0xFF:
                pos += 1
                continue
            # Skip padding FFs.
            while pos < n and data[pos] == 0xFF:
                pos += 1
            if pos >= n:
                break
            marker = data[pos]
            pos += 1
            if marker == 0xD8 or (0xD0 <= marker <= 0xD9):
                continue  # standalone, no length
            if pos + 2 > n:
                break
            seg_len = struct.unpack(">H", data[pos : pos + 2])[0]
            if seg_len < 2:
                break
            if marker in sof_markers:
                if pos + 7 >= n:
                    break
                height = struct.unpack(">H", data[pos + 3 : pos + 5])[0]
                width = struct.unpack(">H", data[pos + 5 : pos + 7])[0]
                components = data[pos + 7]
                mode = {1: "L", 3: "RGB", 4: "CMYK"}.get(components, "unknown")
                if not (0 < width <= 100000 and 0 < height <= 100000):
                    return None
                return width, height, mode
            pos += seg_len
        return None
    except Exception:
        return None


def _parse_webp(data: bytes) -> tuple[int, int, str] | None:
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    try:
        pos = 12
        n = len(data)
        while pos + 8 <= n:
            fourcc = data[pos : pos + 4]
            size = struct.unpack("<I", data[pos + 4 : pos + 8])[0]
            payload = data[pos + 8 : pos + 8 + min(size, 32)]
            if fourcc == b"VP8X" and len(payload) >= 10:
                w = int.from_bytes(payload[4:7], "little") + 1
                h = int.from_bytes(payload[7:10], "little") + 1
                if 0 < w <= 100000 and 0 < h <= 100000:
                    return w, h, "RGBA"
            elif fourcc == b"VP8 " and len(payload) >= 10:
                # Frame tag (3) + magic (3) + width/height (4, 14-bit LE).
                if payload[3:6] == b"\x9d\x01\x2a":
                    w = struct.unpack("<H", payload[6:8])[0] & 0x3FFF
                    h = struct.unpack("<H", payload[8:10])[0] & 0x3FFF
                    if 0 < w <= 100000 and 0 < h <= 100000:
                        return w, h, "RGB"
            elif fourcc == b"VP8L" and len(payload) >= 5:
                if payload[0] == 0x2F:
                    b1, b2, b3, b4 = payload[1], payload[2], payload[3], payload[4]
                    w = 1 + (((b2 & 0x3F) << 8) | b1)
                    h = 1 + (((b4 & 0x0F) << 10) | (b3 << 2) | ((b2 & 0xC0) >> 6))
                    if 0 < w <= 100000 and 0 < h <= 100000:
                        return w, h, "RGBA"
            pos += 8 + size + (size & 1)  # chunks are even-padded
            if pos > _STDLIB_HEADER_BYTES:
                break
        # Valid WEBP container even if dimensions unparseable.
        return None
    except Exception:
        return None


def _stdlib_image_result(path: Path) -> list[CheckResult]:
    """Validate common rasters without Pillow (header-only, no decode)."""
    name = path.name
    suffix = path.suffix.lower()
    try:
        size = path.stat().st_size
    except OSError as exc:
        return [
            CheckResult(
                check_id="format.images.valid",
                level="error",
                passed=False,
                message=f"{name}: unreadable ({exc})",
            )
        ]
    if size == 0:
        return [
            CheckResult(
                check_id="format.images.valid",
                level="error",
                passed=False,
                message=f"{name}: file is empty",
            )
        ]
    try:
        with open(path, "rb") as handle:
            data = handle.read(min(size, _STDLIB_HEADER_BYTES))
    except OSError as exc:
        return [
            CheckResult(
                check_id="format.images.valid",
                level="error",
                passed=False,
                message=f"{name}: unreadable ({exc})",
            )
        ]
    parsed: tuple[int, int, str] | None = None
    fmt = suffix.lstrip(".").upper() or "IMAGE"
    if suffix in (".jpg", ".jpeg"):
        parsed = _parse_jpeg(data)
        fmt = "JPEG"
    elif suffix == ".png":
        parsed = _parse_png(data)
        fmt = "PNG"
    elif suffix == ".gif":
        parsed = _parse_gif(data)
        fmt = "GIF"
    elif suffix == ".bmp":
        parsed = _parse_bmp(data)
        fmt = "BMP"
    elif suffix == ".webp":
        parsed = _parse_webp(data)
        fmt = "WEBP"
    else:
        # Unknown suffix reaching here: magic-sniff across parsers.
        for parser, label in (
            (_parse_jpeg, "JPEG"),
            (_parse_png, "PNG"),
            (_parse_gif, "GIF"),
            (_parse_bmp, "BMP"),
            (_parse_webp, "WEBP"),
        ):
            parsed = parser(data)
            if parsed:
                fmt = label
                break
    if parsed is None:
        # WEBP with valid container but exotic chunk order still counts as
        # present-but-unparsed rather than corrupt when magic matches.
        magic_ok = data[:4] == b"RIFF" and data[8:12] == b"WEBP"
        if suffix == ".webp" and magic_ok:
            return [
                CheckResult(
                    check_id="format.images.valid",
                    level="info",
                    passed=True,
                    message=f"{name}: valid WEBP image (dimensions unreadable without Pillow)",
                    details={"format": "WEBP", "method": "stdlib-header"},
                )
            ]
        return [
            CheckResult(
                check_id="format.images.valid",
                level="error",
                passed=False,
                message=f"{name}: not a valid {fmt} image (header parse failed)",
            )
        ]
    width, height, mode = parsed
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
                "method": "stdlib-header",
            },
        )
    ]


class ImagesCheck(Check):
    """Images check - port of the CUR_Res_CurationTools R inspector."""

    check_id = "format.images"
    extensions = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}

    def run(self, files: list[Path]) -> list[CheckResult]:
        from engine.checks._util import run_per_file

        return run_per_file(self, files, self._run_one)

    def _run_one(self, path: Path) -> list[CheckResult]:
        try:
            from PIL import Image, ImageFile  # type: ignore

            _have_pil = True
        except ImportError:
            Image = None  # type: ignore
            ImageFile = None  # type: ignore
            _have_pil = False

        name = path.name
        if not _have_pil:
            # Offline / lite-build fallback: pure-stdlib header parse so
            # common JPG/PNG/GIF/BMP/WEBP still validate without Pillow.
            return _stdlib_image_result(path)
        # Decompression-bomb guard: refuse absurd pixel counts before decode.
        try:
            Image.MAX_IMAGE_PIXELS = 178_956_970  # ~0.18 GP, Pillow default-equivalent
        except Exception:
            pass
        try:
            with Image.open(str(path)) as image:
                image.verify()
            with Image.open(str(path)) as image:
                width, height = image.size
                mode = image.mode
                fmt = image.format
        except Image.DecompressionBombError as exc:
            return [
                CheckResult(
                    check_id="format.images.valid",
                    level="error",
                    passed=False,
                    message=f"{name}: image too large to safely open ({exc})",
                )
            ]
        except ImageFile.TruncatedFileError:
            # Taxonomy (docs/html/checks-reference.html): unreadable image = error.
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
