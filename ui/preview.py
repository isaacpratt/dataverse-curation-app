"""In-app file previews for the file manifest (dv-koz).

Everything here is head-byte bounded: text-like files are read at most
``HEAD_BYTES``; tabular/PDF/XLSX backends stream with caps; images load
through Pillow with a stdlib header parse as the fallback; archives list
up to ``ARCHIVE_CAP`` entries. A file larger than ``MAX_PREVIEW_BYTES``
gets the "too large — open folder" fallback instead of a parse.

Optional-library failures degrade to the standard "Missing: …" notice
(``_missing_library``) exactly like the automated checks. Pure stdlib:
nothing in this module reads the network, the registry or Dataverse.
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

from ui.i18n import t
from ui.theme import FONT_CAPTION
from ui.widgets import (
    add_info_tip,
    make_action_button,
    make_caption_label,
    make_card,
    make_plain_text_view,
)

HEAD_BYTES = 256 * 1024
MAX_PREVIEW_BYTES = 8 << 20  # 8 MiB
TEXT_LINES = 40
TABLE_ROWS = 8
TABLE_COLS = 12
ARCHIVE_CAP = 60
IMAGE_MAX_PX = 240
PDF_SNIPPET_CHARS = 600

_TEXT_EXTS = {
    ".txt", ".md", ".markdown", ".rst", ".tex", ".rmd",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".log", ".xml", ".html", ".htm", ".csv.bak", ".texmf",
}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}
_ARCHIVE_SUFFIXES = ((".tar.gz",), (".tar.bz2",), (".tar.xz",), (".tgz",), (".txz",))
_ARCHIVE_EXTS = {".zip", ".tar", ".gz", ".bz2", ".xz", ".7z"}

_NUMBER_RE = re.compile(r"^-?\d+(\.\d+)?([eE][-+]?\d+)?$")
_INT_RE = re.compile(r"^-?\d+$")


def _have(module: str) -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec(module) is not None
    except Exception:
        return False


def _missing_library(lib: str) -> str:
    """Return missing-library text in the engine's wording convention."""
    import sys

    if getattr(sys, "frozen", False):
        return t("detail.preview.missing_lite", lib=lib)
    return t("detail.preview.missing_pip", lib=lib)


def _read_head(path: Path, cap: int = HEAD_BYTES) -> bytes:
    with open(path, "rb") as handle:
        return handle.read(cap)


def _decode(raw: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8"


def _is_number(text: str) -> bool:
    return bool(_NUMBER_RE.match(text.strip()))


def _is_int(text: str) -> bool:
    return bool(_INT_RE.match(text.strip()))


def _column_types(rows: list[list[str]]) -> list[str]:
    types: list[str] = []
    ncols = max((len(r) for r in rows), default=0)
    for c in range(ncols):
        col = [
            str(r[c]).strip()
            for r in rows
            if c < len(r) and str(r[c]).strip() not in ("", "NA", "NaN", "na", "n/a")
        ]
        if col and all(_is_int(v) for v in col):
            types.append("integer")
        elif col and all(_is_number(v) for v in col):
            types.append("numeric")
        else:
            types.append("text")
    return types


def _tabular_from_rows(rows: list[list[str]], source: str) -> dict[str, Any]:
    rows = [list(r) for r in rows if any(str(c).strip() for c in r)]
    if not rows:
        return {"kind": "tabular", "source": source, "columns": [], "types": [],
                "rows": [], "truncated": False}
    # Drop trailing all-empty cells so short sheets don't render a wall of
    # empty columns (openpyxl iter_rows pads to max_col).
    widest = max(len(r) for r in rows) if rows else 0
    while widest and all(
        len(r) < widest or not str(r[widest - 1]).strip() for r in rows
    ):
        widest -= 1
    rows = [r[:widest] for r in rows] if widest else [[]]
    header = [str(c) for c in rows[0][:TABLE_COLS]]
    body = [list(r[:TABLE_COLS]) for r in rows[1 : TABLE_ROWS + 1]]
    types = _column_types(rows[1:])[:TABLE_COLS]
    truncated = len(rows) - 1 > TABLE_ROWS or any(len(r) > TABLE_COLS for r in rows)
    return {
        "kind": "tabular",
        "source": source,
        "columns": header,
        "types": types,
        "rows": [[str(c) for c in r] for r in body],
        "truncated": truncated,
    }


def preview_file(
    path: Path | str, *, max_bytes: int = MAX_PREVIEW_BYTES
) -> dict[str, Any]:
    """Preview one file; never raises. ``kind`` drives the renderer."""
    try:
        path = Path(path)
        size = path.stat().st_size
    except OSError as exc:
        return {"kind": "error", "message": str(exc)}
    if size > max_bytes:
        return {"kind": "too_large", "size_bytes": size, "cap_bytes": max_bytes}
    ext = path.suffix.lower()
    lower = path.name.lower()
    try:
        if ext == ".csv" or ext == ".tsv":
            return _preview_delimited(path, "\t" if ext == ".tsv" else ",", ext)
        if ext == ".json":
            return _preview_json(path, size)
        if ext in _IMAGE_EXTS:
            return _preview_image(path)
        if ext == ".pdf":
            return _preview_pdf(path)
        if ext in (".xlsx", ".xlsm"):
            return _preview_xlsx(path)
        if ext in (".sav", ".dta", ".sas7bdat"):
            return _preview_spss(path, ext)
        if ext in (".nc", ".netcdf", ".h5", ".hdf5"):
            return _preview_hdf(path, ext)
        if (
            ext in _ARCHIVE_EXTS
            or any(lower.endswith(s) for s in _ARCHIVE_SUFFIXES)
        ):
            return _preview_archive(path)
        if ext in _TEXT_EXTS or ext == "":
            return _preview_text(path)
        head = _read_head(path, 8192)
        if b"\x00" in head:
            return {"kind": "unsupported", "extension": ext, "binary": True}
        return _preview_text(path)
    except Exception as exc:  # a broken file must never break the page
        return {"kind": "error", "message": str(exc)}


def _preview_delimited(path: Path, delimiter: str, ext: str) -> dict[str, Any]:
    raw = _read_head(path)
    text, encoding = _decode(raw)
    try:
        rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    except csv.Error:
        rows = [[line] for line in text.splitlines()[: TABLE_ROWS + 1]]
    out = _tabular_from_rows(rows, ext.lstrip("."))
    out["encoding"] = encoding
    return out


def _preview_json(path: Path, size: int) -> dict[str, Any]:
    if size <= HEAD_BYTES:
        text, encoding = _decode(_read_head(path))
        try:
            parsed = json.loads(text)
            pretty = json.dumps(parsed, indent=2, ensure_ascii=False)
        except Exception:
            pretty = text
        lines = pretty.splitlines()
        lines = lines[:TEXT_LINES]
        return {
            "kind": "json",
            "text": "\n".join(lines),
            "truncated": len(pretty.splitlines()) > TEXT_LINES,
            "encoding": encoding,
        }
    head = _read_head(path)
    text, _enc = _decode(head)
    return {
        "kind": "json",
        "text": text,
        "truncated": True,
        "encoding": "utf-8",
    }


def _preview_text(path: Path) -> dict[str, Any]:
    raw = _read_head(path)
    text, encoding = _decode(raw)
    lines = text.splitlines()
    shown = lines[:TEXT_LINES]
    truncated = len(lines) > TEXT_LINES
    return {
        "kind": "text",
        "lines": shown,
        "text": "\n".join(shown),
        "truncated": truncated,
        "encoding": encoding,
    }


def _preview_image(path: Path) -> dict[str, Any]:
    fmt = path.suffix.lower().lstrip(".").upper()
    if _have("PIL"):
        try:
            from PIL import Image

            with Image.open(path) as img:
                width, height = img.size
                img.thumbnail((IMAGE_MAX_PX, IMAGE_MAX_PX))
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGBA") if "A" in img.mode else img.convert("RGB")
                buf = io.BytesIO()
                img.save(buf, "PNG")
                return {
                    "kind": "image",
                    "width": width,
                    "height": height,
                    "format": getattr(img, "format", None) or fmt,
                    "thumbnail": buf.getvalue(),
                }
        except Exception:
            pass
    # stdlib header parse (no Pillow): dimensions only.
    try:
        data = _read_head(path, 256 * 1024)
        from engine.checks.images_check import (
            _parse_bmp,
            _parse_gif,
            _parse_jpeg,
            _parse_png,
            _parse_webp,
        )

        for parser in (_parse_png, _parse_gif, _parse_bmp, _parse_jpeg, _parse_webp):
            parsed = parser(data)
            if parsed:
                width, height, detected = parsed
                return {
                    "kind": "image",
                    "width": width,
                    "height": height,
                    "format": detected,
                    "thumbnail": None,
                }
    except Exception:
        pass
    return {
        "kind": "image",
        "width": 0,
        "height": 0,
        "format": fmt,
        "thumbnail": None,
    }


def _preview_pdf(path: Path) -> dict[str, Any]:
    if not _have("pypdf"):
        return {"kind": "missing", "library": "pypdf", "message": _missing_library("pypdf")}
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        pages = len(reader.pages)
        try:
            text = (reader.pages[0].extract_text() or "")[:PDF_SNIPPET_CHARS]
        except Exception:
            text = ""
        return {"kind": "pdf", "pages": pages, "snippet": text.strip()}
    except Exception as exc:
        return {"kind": "error", "message": str(exc)}


def _preview_xlsx(path: Path) -> dict[str, Any]:
    if not _have("openpyxl"):
        return {
            "kind": "missing",
            "library": "openpyxl",
            "message": _missing_library("openpyxl"),
        }
    try:
        import openpyxl

        wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
        try:
            sheet = wb.sheetnames[0] if wb.sheetnames else ""
            ws = wb[sheet] if sheet else None
            rows: list[list[str]] = []
            if ws is not None:
                for row in ws.iter_rows(max_row=TABLE_ROWS + 1,
                                        max_col=TABLE_COLS,
                                        values_only=True):
                    rows.append(["" if c is None else str(c) for c in row])
            out = _tabular_from_rows(rows, "xlsx")
            out["sheet"] = sheet
            return out
        finally:
            wb.close()
    except Exception as exc:
        return {"kind": "error", "message": str(exc)}


def _preview_spss(path: Path, ext: str) -> dict[str, Any]:
    if not _have("pyreadstat"):
        return {
            "kind": "missing",
            "library": "pyreadstat",
            "message": _missing_library("pyreadstat"),
        }
    try:
        import pyreadstat

        if ext == ".sav":
            df, meta = pyreadstat.read_sav(
                str(path), row_limit=TABLE_ROWS + 1, metadataonly=False
            )
        elif ext == ".dta":
            df, meta = pyreadstat.read_dta(
                str(path), row_limit=TABLE_ROWS + 1, metadataonly=False
            )
        else:
            df, meta = pyreadstat.read_sas7bdat(
                str(path), row_limit=TABLE_ROWS + 1, metadataonly=False
            )
        columns = list(getattr(meta, "column_names", []) or list(df.columns))
        labels = list(getattr(meta, "column_labels", []) or [])
        types = list(getattr(meta, "original_variable_types", []) or [])
        n_rows = int(getattr(meta, "number_rows", len(df)) or len(df))
        n_cols = int(getattr(meta, "number_columns", len(columns)) or len(columns))
        try:
            preview_rows = [
                ["" if v is None else str(v) for v in row][:TABLE_COLS]
                for row in df.head(TABLE_ROWS).itertuples(index=False)
            ]
        except Exception:
            preview_rows = [
                [str(v) for v in row[:TABLE_COLS]]
                for row in list(df.values)[:TABLE_ROWS]
            ] if df is not None else []
        return {
            "kind": "tabular",
            "source": ext.lstrip("."),
            "columns": [str(c) for c in columns[:TABLE_COLS]],
            "labels": [str(v or "") for v in labels[:TABLE_COLS]],
            "types": [str(v) for v in types[:TABLE_COLS]] or _column_types(preview_rows),
            "rows": preview_rows,
            "truncated": len(preview_rows) >= TABLE_ROWS,
            "dimensions": (n_rows, n_cols),
        }
    except Exception as exc:
        return {"kind": "error", "message": str(exc)}


def _preview_hdf(path: Path, ext: str) -> dict[str, Any]:
    is_netcdf = ext in (".nc", ".netcdf")
    lib = "netCDF4" if is_netcdf else "h5py"
    if not _have(lib):
        return {"kind": "missing", "library": lib, "message": _missing_library(lib)}
    lines: list[str] = []
    try:
        if is_netcdf:
            from netCDF4 import Dataset

            with Dataset(str(path)) as ds:
                for name, dim in list(ds.dimensions.items())[:40]:
                    lines.append(t("detail.preview.structure_dim", name=name, size=dim.size))
                for name, var in list(ds.variables.items())[:40]:
                    lines.append(
                        t(
                            "detail.preview.structure_var",
                            name=name,
                            dimensions=var.dimensions,
                            dtype=var.dtype,
                        )
                    )
        else:
            import h5py

            count = 0
            with h5py.File(str(path), "r") as handle:
                for key in handle.keys():
                    obj = handle[key]
                    lines.append(f"{key}: {'group' if isinstance(obj, h5py.Group) else 'dataset'}")
                    count += 1
                    if count >= 100:
                        break
    except Exception as exc:
        return {"kind": "error", "message": str(exc)}
    return {
        "kind": "structure",
        "lines": lines,
        "text": "\n".join(lines),
        "truncated": len(lines) >= 100,
    }


# ── Qt widget ──────────────────────────────────────────────────────────────

_COL_CLAMP = 24  # cell text is clamped so wide CSVs never widen the card


def _clamp(text: Any, limit: int = _COL_CLAMP) -> str:
    text = "" if text is None else str(text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def render_tabular(result: dict[str, Any]) -> str:
    """Monospace table for the tabular preview kinds."""
    cols = [_clamp(c, _COL_CLAMP) for c in (result.get("columns") or [])]
    types = [_clamp(c, _COL_CLAMP) for c in (result.get("types") or [])]
    rows = result.get("rows") or []
    out: list[str] = []
    if cols:
        out.append(" | ".join(cols))
        if types:
            out.append(" | ".join(types))
        out.append("")
    for row in rows:
        out.append(" | ".join(_clamp(c) for c in row))
    legend = " · ".join(
        f"{_clamp(c, 18)}: {_clamp(t, 18)}"
        for c, t in zip(result.get("columns") or [], result.get("types") or [], strict=False)
        if c
    )
    if legend:
        out.append("")
        out.append(legend)
    labels = result.get("labels") or []
    label_bits = [
        f"{_clamp(c, 18)}: {_clamp(lbl, 40)}"
        for c, lbl in zip(result.get("columns") or [], labels, strict=False)
        if lbl
    ]
    if label_bits:
        out.append("")
        out.append(" · ".join(label_bits))
    dims = result.get("dimensions")
    if dims:
        out.append("")
        out.append(t("detail.preview.dimensions", rows=dims[0], cols=dims[1]))
    return "\n".join(out)


class PreviewCard(QFrame):
    """Bounded preview of one staged file (dv-koz).

    The card itself owns a ``make_card`` chrome; the body swaps between a
    placeholder, a monospace view, an image and an Open-folder fallback
    depending on the preview ``kind``.
    """

    def __init__(self, on_open_folder=None, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        card, body, _title, _header = make_card(t("detail.preview.title"))
        add_info_tip(_header, t("detail.preview.tip"), name=t("detail.preview.title"))
        lay.addWidget(card)

        self._placeholder = make_caption_label(t("detail.preview.select_file"))
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setMinimumHeight(120)
        body.addWidget(self._placeholder)

        self._mono = make_plain_text_view("", font_size=FONT_CAPTION)
        self._mono.setMinimumHeight(150)
        self._mono.setVisible(False)
        body.addWidget(self._mono, 1)

        self._image = QLabel()
        self._image.setObjectName("PreviewImage")
        self._image.setAlignment(Qt.AlignCenter)
        self._image.setMinimumHeight(80)
        self._image.setVisible(False)
        body.addWidget(self._image)

        self._note = make_caption_label("")
        self._note.setVisible(False)
        body.addWidget(self._note)

        self._open_btn = make_action_button(
            t("detail.preview.open_folder"), kind="secondary", size="md"
        )
        self._open_btn.setVisible(False)
        self._open_btn.clicked.connect(
            lambda: self._on_open_folder() if self._on_open_folder else None
        )
        body.addWidget(self._open_btn)

        self._on_open_folder = on_open_folder
        self._rel = ""

    # -- public API ---------------------------------------------------------
    def set_not_staged(self, rel: str = "") -> str:
        self._reset()
        self._rel = rel or ""
        self._placeholder.setVisible(False)
        self._note.setText(t("detail.preview.not_staged"))
        self._note.setVisible(True)
        return "not_staged"

    def set_path(self, path: Path | str, rel: str = "") -> str:
        kind = "error"
        try:
            result = preview_file(Path(path))
            kind = str(result.get("kind", "error"))
        except Exception as exc:  # never break the page on a curator's file
            result = {"kind": "error", "message": str(exc)}
        self._reset()
        self._rel = rel or Path(path).name
        try:
            if kind == "tabular":
                self._mono.setPlainText(self._with_footer(render_tabular(result), result))
                self._mono.setVisible(True)
            elif kind in ("text", "json", "structure"):
                text = result.get("text") or "\n".join(result.get("lines") or [])
                self._mono.setPlainText(self._with_footer(text, result))
                self._mono.setVisible(True)
            elif kind == "pdf":
                pages = result.get("pages", 0)
                head = t("detail.preview.pdf_pages", pages=pages)
                snippet = result.get("snippet") or t("detail.preview.no_pdf_text")
                self._mono.setPlainText(f"{head}\n\n{snippet}")
                self._mono.setVisible(True)
            elif kind == "archive":
                entries = result.get("entries") or []
                total = result.get("total", len(entries))
                body_text = "\n".join(entries)
                if total > len(entries):
                    body_text += "\n" + t(
                        "detail.preview.archive_more",
                        extra=total - len(entries),
                        total=total,
                    )
                self._mono.setPlainText(body_text)
                self._mono.setVisible(True)
            elif kind == "image":
                self._show_image(result)
            elif kind == "too_large":
                cap = int(result.get("cap_bytes", MAX_PREVIEW_BYTES)) >> 20
                self._note.setText(t("detail.preview.too_large", cap=cap))
                self._note.setVisible(True)
                self._open_btn.setVisible(True)
            elif kind == "missing":
                self._mono.setPlainText(str(result.get("message", "")))
                self._mono.setVisible(True)
            elif kind == "unsupported":
                ext = str(result.get("extension", "")).lstrip(".") or "?"
                self._note.setText(t("detail.preview.unsupported", ext=ext))
                self._note.setVisible(True)
            else:
                reason = str(result.get("message", t("detail.preview.unknown_error")))
                self._note.setText(t("detail.preview.error", message=reason))
                self._note.setVisible(True)
        except Exception:
            self._note.setText(t("detail.preview.error", message=t("detail.preview.render_failed")))
            self._note.setVisible(True)
        return kind

    # -- internals ----------------------------------------------------------
    def _reset(self) -> None:
        self._placeholder.setVisible(False)
        self._mono.setVisible(False)
        self._mono.setPlainText("")
        self._image.setVisible(False)
        self._image.clear()
        self._note.setVisible(False)
        self._note.setText("")
        self._open_btn.setVisible(False)

    @staticmethod
    def _with_footer(text: str, result: dict[str, Any]) -> str:
        if result.get("truncated"):
            text = text.rstrip("\n") + "\n\n" + t("detail.preview.truncated")
        return text

    def _show_image(self, result: dict[str, Any]) -> None:
        thumb = result.get("thumbnail")
        width = int(result.get("width") or 0)
        height = int(result.get("height") or 0)
        fmt = str(result.get("format") or "")
        if thumb:
            pixmap = QPixmap()
            pixmap.loadFromData(thumb, "PNG")
            self._image.setPixmap(pixmap)
            self._image.setVisible(True)
        dims = (
            t("detail.preview.dims", width=width, height=height, format=fmt)
            if width
            else fmt
        )
        self._note.setText(dims)
        self._note.setVisible(True)


def _preview_archive(path: Path) -> dict[str, Any]:
    lower = path.name.lower()
    entries: list[str] = []
    total = 0
    try:
        if lower.endswith((".tar", ".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".txz", ".gz", ".bz2", ".xz")):
            import tarfile

            with tarfile.open(str(path)) as handle:
                for idx, member in enumerate(handle):
                    if idx < ARCHIVE_CAP:
                        entries.append(
                            t(
                                "detail.preview.archive_entry",
                                name=member.name,
                                size=member.size,
                            )
                        )
                    total = idx + 1
                    if idx >= ARCHIVE_CAP * 10:
                        break
        else:
            import zipfile

            with zipfile.ZipFile(str(path)) as handle:
                infos = handle.infolist()
                total = len(infos)
                for info in infos[:ARCHIVE_CAP]:
                    entries.append(
                        t(
                            "detail.preview.archive_entry",
                            name=info.filename,
                            size=info.file_size,
                        )
                    )
    except Exception as exc:
        return {"kind": "error", "message": str(exc)}
    return {
        "kind": "archive",
        "entries": entries,
        "total": total,
        "truncated": total > ARCHIVE_CAP,
    }
