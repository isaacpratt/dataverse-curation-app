"""Lucide icons (ISC licence, https://lucide.dev) bundled as SVG.

Files live in ui/assets/lucide/<name>.svg (upstream `stroke="currentColor"`
artwork); this module resolves them frozen-safe via theme.asset_path,
tints by replacing currentColor, and caches the results. Everything here
is best-effort and never raises at the call site — a missing asset yields
an empty QIcon, and says so once.
"""

import warnings

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QLabel

from ui.theme import (
    STATE_ERROR_GRAPHIC,
    STATE_SUCCESS_GRAPHIC,
    STATE_WARNING_GRAPHIC,
    TEXT_ON_TINT,
    TEXT_PRIMARY,
    asset_path,
    transparent_qss,
)

INK = TEXT_PRIMARY
MUTED = TEXT_ON_TINT
GREEN = STATE_SUCCESS_GRAPHIC
AMBER = STATE_WARNING_GRAPHIC
RED = STATE_ERROR_GRAPHIC

# One glyph per role, the list the docs, the gallery sheet and
# ui/tests/test_icon_inventory.py all read (dv-kvb). A role says what a
# mark is for; the value names the bundled asset. Adding a role here is how
# a control gets its glyph - a text character or a hand-drawn path is never
# the answer (see docs/html/development.html, "Icons").
ICON_ROLES: dict[str, str] = {
    "refresh": "rotate-ccw",
    "reset": "rotate-ccw",
    "back": "arrow-left",
    "sidebar_hide": "panel-right-close",
    "sidebar_show": "panel-right-open",
    "more": "ellipsis",
    "close": "x",
    "add": "plus",
    "remove": "minus",
    "expand": "chevron-down",
    "collapse": "chevron-right",
    "sort_ascending": "chevron-up",
    "sort_descending": "chevron-down",
    "done": "check",
    "info": "info",
    "warning": "triangle-alert",
    "error": "octagon-x",
    "settings": "settings",
    "log": "square-text",
}

_MISSING: set[str] = set()

_ICON_CACHE: dict[tuple[str, str, int], QIcon] = {}
_SVG_CACHE: dict[str, str] = {}


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

    An unknown name returns an empty QIcon *and warns once*: a silent null
    icon is how a mark disappears from the interface with nothing failing
    (dv-kvb). ``ui/tests/test_icon_inventory.py`` turns the warning into a
    CI failure by asserting every name in the app resolves.
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
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            try:
                renderer.render(painter)
            finally:
                painter.end()
            if not pixmap.isNull():
                result = QIcon(pixmap)
        if result.isNull() and str(name) not in _MISSING:
            _MISSING.add(str(name))
            warnings.warn(
                f"Lucide icon not bundled: {name!r} (expected "
                f"ui/assets/lucide/{name}.svg). Add the asset; a text "
                "character is not a substitute (dv-kvb).",
                RuntimeWarning,
                stacklevel=3,
            )
    except Exception:
        result = QIcon()
    try:
        _ICON_CACHE[key] = result
    except Exception:
        pass
    return result


def role_icon(role: str, color: str | None = None, size: int = 16) -> QIcon:
    """QIcon for one of the documented roles in ``ICON_ROLES``.

    The role is what the control *is* -- refresh, back, sidebar_hide, more
    -- so two refresh buttons, or two close buttons, cannot drift onto
    different glyphs.
    """
    return icon(ICON_ROLES.get(str(role), str(role)), color=color, size=size)


def icon_label(name: str, size: int = 16, color: str | None = None) -> QLabel:
    """Fixed-size icon QLabel (transparent, centred) for row layouts."""
    from PySide6.QtWidgets import QLabel as _QLabel

    lbl = _QLabel()
    try:
        lbl.setPixmap(icon(name, color=color, size=size).pixmap(QSize(int(size), int(size))))
        lbl.setFixedSize(int(size) + 4, int(size) + 4)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(transparent_qss("QLabel"))
    except Exception:
        pass
    return lbl


# Tree branch chevrons are painted by ui.widgets._BranchPainting, not by
# a QTreeView::branch stylesheet: the Windows 11 style still painted its
# own grey branch chip (with an accent chevron that read as a blue stripe
# on the selected row) even with ``image: none`` set (dv-coj).


_FILE_ICONS = {
    ".csv": "file-spreadsheet",
    ".tsv": "file-spreadsheet",
    ".dta": "file-spreadsheet",
    ".sav": "file-spreadsheet",
    ".sas7bdat": "file-spreadsheet",
    ".xls": "file-spreadsheet",
    ".xlsx": "file-spreadsheet",
    ".txt": "file-text",
    ".md": "file-text",
    ".pdf": "file-text",
    ".json": "file-json",
    ".xml": "file-code",
    ".py": "file-code",
    ".r": "file-code",
    ".m": "file-code",
    ".jl": "file-code",
    ".ipynb": "file-code",
    ".do": "file-code",
    ".png": "file-image",
    ".jpg": "file-image",
    ".jpeg": "file-image",
    ".tif": "file-image",
    ".tiff": "file-image",
    ".gif": "file-image",
    ".bmp": "file-image",
    ".zip": "file-archive",
    ".tar": "file-archive",
    ".gz": "file-archive",
    ".7z": "file-archive",
    ".bz2": "file-archive",
    ".nc": "database",
    ".h5": "database",
    ".hdf5": "database",
    ".mat": "database",
    ".db": "database",
    ".sqlite": "database",
    ".sqlite3": "database",
    ".fastq": "dna",
    ".fq": "dna",
    ".fasta": "dna",
    ".fa": "dna",
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
