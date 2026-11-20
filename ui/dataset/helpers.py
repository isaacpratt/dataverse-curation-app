"""Shared helpers and tables for the dataset detail page.

The formatting helpers the sections use to render file sizes, file
icons, manifest rows, the status pill and raw metadata.  They live here
so every section renders the same values the same way.
"""

import json
from pathlib import Path
from typing import Any

from ui.i18n import t


def _human_size(n: int) -> str:
    # Re-exported from the shared helper (dv-005): labels are decimal (KB/MB).
    from ui.widgets import human_size as _shared

    return _shared(n)


def _icon_for_ext(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext in (".csv",):
        return "description"
    if ext in (".nc", ".h5", ".hdf5"):
        return "map"
    if ext in (".zip", ".tar", ".gz", ".7z"):
        return "code"
    if ext in (".pdf",):
        return "picture_as_pdf"
    if ext in (".json",):
        return "data_object"
    if ext in (".txt", ".md"):
        return "article"
    return "description"


def _manifest_display_for_entry(e: dict[str, Any]) -> tuple[str, int, str]:
    """(display_path, size_bytes, fmt) for one file-inventory entry.

    Tabular ingests are server-generated `.tab` derivatives of the
    depositor's upload: show the ORIGINAL file (name/format/size) so the
    manifest reads `eco.sav` / SAV rather than `eco.tab` / TAB. The display
    path matches where `DownloadManager.download_originals` stages the
    original (`parent/original_name`), so staged checks and engine-report
    matching keep working. Non-tabular entries (or tabular ones without a
    recorded original) fall back to the inventory path as before.
    """
    try:
        path = str(e.get("path", "") or "")
    except Exception:
        return "", 0, "FILE"
    if not isinstance(e, dict):
        return path, 0, "FILE"
    try:
        size = int(e.get("size_bytes", 0) or 0)
    except (TypeError, ValueError):
        size = 0
    mime = str(e.get("mime_type", "") or "")
    if not (e.get("tabular") and str(e.get("original_name", "") or "").strip()):
        ext = Path(path).suffix.lower().lstrip(".").upper()
        return path, size, ext or mime.split("/")[-1].upper() or "FILE"
    original_base = Path(str(e["original_name"])).name
    parent = path.rpartition("/")[0] if "/" in path else ""
    display = f"{parent}/{original_base}" if parent else original_base
    ext = Path(original_base).suffix.lower().lstrip(".").upper()
    if not ext:
        # Original name without an extension: map the recorded MIME type.
        try:
            import mimetypes as _mimetypes

            guessed = _mimetypes.guess_extension(
                str(e.get("original_format", "") or "").split(";")[0].strip()
            )
            ext = (guessed or "").lstrip(".").upper()
        except Exception:
            ext = ""
    try:
        original_size = int(e.get("original_size", 0) or 0)
    except (TypeError, ValueError):
        original_size = 0
    return (
        display,
        original_size or size,
        ext or Path(path).suffix.lower().lstrip(".").upper() or "FILE",
    )


def _pill_state(version_state: str, in_review: bool = False) -> tuple[str, str]:
    """Return the same words as the dashboard status column (Draft/Published/In Review)."""
    s = (version_state or "").upper()
    if s == "DRAFT":
        if in_review:
            return ("PillInReview", t("dashboard.display_state.review"))
        return ("PillDraft", t("dashboard.display_state.draft"))
    if s in ("RELEASED", "PUBLISHED"):
        return ("PillReady", t("dashboard.display_state.published"))
    if s == "DEACCESSIONED":
        return ("PillDraft", t("dashboard.display_state.deaccessioned"))
    if "REVIEW" in s:
        return ("PillInReview", t("dashboard.display_state.review"))
    if not s:
        return ("PillDraft", t("dashboard.display_state.draft"))
    return ("PillDraft", s.title())


def _format_metadata(metadata: dict[str, Any]) -> str:
    if not metadata:
        return t("detail.meta.no_metadata")
    try:
        lines = []
        latest = metadata.get("latestVersion") or {}
        blocks = latest.get("metadataBlocks") or metadata.get("metadataBlocks") or {}
        if blocks:
            for block_name, block in blocks.items():
                lines.append(
                    t(
                        "detail.meta.block_format",
                        block=block_name,
                        name=block.get("displayName", ""),
                    )
                )
                for field in block.get("fields", []):
                    type_name = field.get("typeName", "")
                    v = field.get("value", "")
                    if isinstance(v, list):
                        v = t("detail.meta.value_separator").join(
                            str(x.get("value") if isinstance(x, dict) and "value" in x else x)
                            for x in v[:5]
                        )
                    lines.append(t("detail.meta.field_format", type=type_name, value=v))
                lines.append("")
        lines.append(t("detail.meta.full_json"))
        lines.append(json.dumps(metadata, indent=2, ensure_ascii=False)[:12000])
        return "\n".join(lines)
    except Exception as exc:
        return json.dumps(metadata, indent=2, ensure_ascii=False)[:12000] + t(
            "detail.meta.format_error", exc=exc
        )
