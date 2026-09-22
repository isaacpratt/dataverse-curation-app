"""Lucide icons (ISC licence, https://lucide.dev) bundled as SVG.

Files live in ui/assets/lucide/<name>.svg (upstream `stroke="currentColor"`
artwork); this module resolves them frozen-safe via theme.asset_path,
tints by replacing currentColor, and caches the results. Everything here
is best-effort and never raises — a missing asset yields an empty QIcon.
"""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer  # noqa: F401 (forces PyInstaller to bundle QtSvg)
from PySide6.QtWidgets import QLabel

from ui.theme import asset_path

INK = "#131b2e"
MUTED = "#57657a"
GREEN = "#16a34a"
AMBER = "#d97706"
RED = "#ba1a1a"

_ICON_CACHE: dict = {}
_SVG_CACHE: dict = {}


def _svg_text(name: str) -> str:
    """Raw SVG text for a bundled icon ("" when missing)."""
    if name in _SVG_CACHE:
        return _SVG_CACHE[name]
    text = ""
    try:
        path = asset_path(f"lucide/{name}.svg")
        if path:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
    except Exception:
        text = ""
    try:
        _SVG_CACHE[name] = text
    except Exception:
        pass
    return text


def icon(name: str, color: str | None = None, size: int = 16) -> QIcon:
    """QIcon for a bundled Lucide icon, tinted + cached.

    color replaces the artwork's currentColor (default INK). size is the
    rendered pixel size; QIcon scales from the cached pixmap gracefully.
    """
    key = (name, color or INK, int(size))
    try:
        hit = _ICON_CACHE.get(key)
        if hit is not None:
            return hit
    except Exception:
        pass
    result = QIcon()
    try:
        text = _svg_text(name)
        if text and "<svg" in text[:800]:
            tinted = text.replace("currentColor", color or INK)
            renderer = QSvgRenderer(bytearray(tinted.encode("utf-8")))
            pixmap = QPixmap(max(1, int(size)), max(1, int(size)))
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            try:
                renderer.render(painter)
            finally:
                painter.end()
            if not pixmap.isNull():
                result = QIcon(pixmap)
    except Exception:
        result = QIcon()
    try:
        _ICON_CACHE[key] = result
    except Exception:
        pass
    return result


def icon_label(name: str, size: int = 16, color: str | None = None) -> QLabel:
    """Fixed-size icon QLabel (transparent, centred) for row layouts."""
    from PySide6.QtWidgets import QLabel as _QLabel

    lbl = _QLabel()
    try:
        lbl.setPixmap(
            icon(name, color=color, size=size).pixmap(QSize(int(size), int(size)))
        )
        lbl.setFixedSize(int(size) + 4, int(size) + 4)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(
            "QLabel { background: transparent; border: none; }"
        )
    except Exception:
        pass
    return lbl


def tree_branch_qss() -> str:
    """QTreeView branch rules using Lucide chevrons (replaces text carets).

    Also kills the dotted indent-guide lines Qt draws through child rows
    (has-siblings/adjoins-item states) — clean indent, no vertical rules.
    """
    lines_off = (
        "QTreeView::branch:has-siblings:!adjoins-item { border-image: none; }"
        "QTreeView::branch:has-siblings:adjoins-item { border-image: none; }"
        "QTreeView::branch:!has-siblings:adjoins-item { border-image: none; }"
    )
    right = asset_path("lucide/chevron-right-ink.svg")
    down = asset_path("lucide/chevron-down-ink.svg")
    if not right or not down:
        return "QTreeView::branch { image: none; border-image: none; }" + lines_off
    return (
        "QTreeView::branch:closed:has-children { image: url(" + right + "); }"
        "QTreeView::branch:open:has-children { image: url(" + down + "); }"
        "QTreeView::branch:has-children { width: 16px; height: 16px; }"
        "QTreeView::branch:!has-children { image: none; border-image: none; }"
        + lines_off
    )


_FILE_ICONS = {
    ".csv": "file-spreadsheet", ".tsv": "file-spreadsheet",
    ".dta": "file-spreadsheet", ".sav": "file-spreadsheet",
    ".sas7bdat": "file-spreadsheet", ".xls": "file-spreadsheet",
    ".xlsx": "file-spreadsheet",
    ".txt": "file-text", ".md": "file-text", ".pdf": "file-text",
    ".json": "file-json", ".xml": "file-code",
    ".py": "file-code", ".r": "file-code", ".m": "file-code",
    ".jl": "file-code", ".ipynb": "file-code", ".do": "file-code",
    ".png": "file-image", ".jpg": "file-image", ".jpeg": "file-image",
    ".tif": "file-image", ".tiff": "file-image", ".gif": "file-image",
    ".bmp": "file-image",
    ".zip": "file-archive", ".tar": "file-archive", ".gz": "file-archive",
    ".7z": "file-archive", ".bz2": "file-archive",
    ".nc": "database", ".h5": "database", ".hdf5": "database",
    ".mat": "database", ".db": "database", ".sqlite": "database",
    ".sqlite3": "database",
    ".fastq": "dna", ".fq": "dna", ".fasta": "dna", ".fa": "dna",
}


def file_icon_name(path: str) -> str:
    """Lucide icon name for a file path (extension map, "file" fallback)."""
    try:
        from pathlib import Path as _Path

        return _FILE_ICONS.get(_Path(str(path or "")).suffix.lower(), "file")
    except Exception:
        return "file"


def file_icon(path: str, staged: bool = True, size: int = 16) -> QIcon:
    """File-type icon; unstaged files render muted (replaces the ✓/○ prefix)."""
    try:
        return icon(file_icon_name(path), color=(INK if staged else MUTED), size=size)
    except Exception:
        return QIcon()


def status_icon_name(kind: str) -> tuple[str, str]:
    """(icon name, tint) for check/file statuses.

    kinds: pass/clean, fail (error), warn, skipped, unchecked, neutral.
    """
    k = str(kind or "").lower()
    if k in ("fail", "error"):
        return ("octagon-x", RED)
    if k in ("warn", "warning"):
        return ("octagon-alert", AMBER)
    if k in ("pass", "clean", "check"):
        return ("check", GREEN)
    if k in ("skip", "skipped"):
        return ("circle-dashed", MUTED)
    if k in ("unchecked", "minus"):
        return ("minus", MUTED)
    return ("circle", MUTED)


def status_icon(kind: str, size: int = 16) -> QIcon:
    """QIcon for a check/file status kind (see status_icon_name)."""
    try:
        name, color = status_icon_name(kind)
        return icon(name, color=color, size=size)
    except Exception:
        return QIcon()
