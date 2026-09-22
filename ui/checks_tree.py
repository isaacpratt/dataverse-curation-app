"""Folder > file > check tree model for the File Manifest card.

Carbon Tree View-inspired behavior (caret-left expanders, indented children,
arrow-key navigation via QTreeView) implemented natively in PySide6 with the
app's existing palette — Carbon web components are not available on desktop.

Node kinds (Qt.UserRole dict on column-0 item):
  folder: {"kind": "folder", "dir": str, "base": str}
  file:   {"kind": "file", "path": str, "base": str}
  check:  {"kind": "check", "path": str, "check_id": str}

Icons are Lucide (see ui/icons.py), set as item icons — never text glyphs:
folder/folder-open track expanded state, file icons follow the extension
(staged files ink, unstaged muted), check rows carry octagon-x (errors),
octagon-alert (warnings), check (passes) or circle-dashed (skipped).
Expand affordance itself comes from QTreeView branch images (Lucide
chevrons via ui.icons.tree_branch_qss); update_carets() keeps folder
icons in sync with live expanded state and must run after every
expand/collapse (see dataset_detail).

Columns: Name | Size | Format | Scan. Folder rows aggregate children counts;
file rows show the scan aggregate (engine.status.status_label); check rows
show the full untruncated message with PASS/WARN/FAIL/SKIPPED badge text in
the Scan column and a details tooltip.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel

from engine.status import classify, file_status, status_label
from ui.icons import file_icon, icon, status_icon

COLUMNS = ["Name", "Size", "Format", "Scan"]

_KIND_ROLE = Qt.UserRole + 1

CHECK_BADGE = {
    "passed": "PASS",
    "failed-warning": "WARN",
    "failed-error": "FAIL",
    "skipped": "SKIPPED",
}

# Legacy text glyphs (pre-Lucide). Kept so update_carets() can strip them
# from any model built before the icon switch; nothing emits them anymore.
_CARET_PREFIXES = ("▸ ", "▾ ")


def _strip_legacy_caret(text: str) -> str:
    try:
        for prefix in _CARET_PREFIXES:
            if text.startswith(prefix):
                return text[len(prefix):]
    except Exception:
        pass
    return text


def update_carets(model, is_expanded) -> None:
    """Sync folder icons + names with the tree's live expanded state.

    model: QStandardItemModel built by build_tree_model.
    is_expanded(index) -> bool, e.g. QTreeView.isExpanded bound method.
    Names always read the stored base text (legacy caret prefixes are
    stripped); folder icons flip folder/folder-open. Never raises.
    """
    if model is None:
        return

    def _sync(item, index) -> None:
        try:
            data = item.data(_KIND_ROLE) if item is not None else None
        except Exception:
            data = None
        if item is None or not isinstance(data, dict):
            return
        base = data.get("base")
        if base is None:
            return
        try:
            if item.text() != base:
                item.setText(_strip_legacy_caret(base))
        except Exception:
            pass
        if data.get("kind") != "folder":
            return
        try:
            opened = bool(is_expanded(index))
        except Exception:
            opened = False
        try:
            item.setIcon(icon("folder-open" if opened else "folder"))
        except Exception:
            pass

    try:
        for r in range(model.rowCount()):
            idx = model.index(r, 0)
            item = model.item(r, 0)
            _sync(item, idx)
            if item is None:
                continue
            try:
                kids = item.rowCount()
            except Exception:
                kids = 0
            for i in range(kids):
                try:
                    _sync(item.child(i, 0), model.index(i, 0, idx))
                except Exception:
                    continue
    except Exception:
        pass


def check_badge_text(result) -> str:
    return CHECK_BADGE.get(classify(result), "PASS")


def format_details_tooltip(result) -> str:
    parts = [
        f"{result.check_id} [{result.level}]",
        result.message,
    ]
    details = result.details or {}
    shown = {k: v for k, v in details.items() if k != "skipped"}
    if details.get("skipped"):
        reason = details.get("reason") or details.get("required", "")
        parts.append(f"Skipped: {reason}" if reason else "Skipped")
    if shown:
        import json as _json

        try:
            parts.append(_json.dumps(shown, indent=1)[:2000])
        except Exception:
            parts.append(str(shown)[:2000])
    return "\n".join(parts)


def _human_size(n: int) -> str:
    try:
        n = int(n)
    except Exception:
        return str(n)
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024**2:.1f} MB"


def _new_item(text: str, tooltip: str = "") -> QStandardItem:
    item = QStandardItem(text)
    item.setEditable(False)
    if tooltip:
        item.setToolTip(tooltip)
    return item


def build_tree_model(rows, report=None, is_staged=None, human_size=None) -> QStandardItemModel:
    """Build the folder>file>check model.

    rows: list of (path, size_bytes, fmt, original) like _all_file_rows.
    report: DatasetReport or None (pre-run: file nodes only, no checks).
    is_staged: callable(path) -> bool (staged files render ink, others muted).
    """
    model = QStandardItemModel()
    model.setHorizontalHeaderLabels(COLUMNS)
    hs = human_size or _human_size
    by_path = {}
    if report is not None:
        by_path = {f.path: f for f in report.files}

    folders: dict[str, list] = {}
    for row in rows or []:
        path = row[0] if len(row) > 0 else ""
        size = row[1] if len(row) > 1 else 0
        fmt = row[2] if len(row) > 2 else ""
        derivative = row[3] if len(row) > 3 else ""
        parent = path.rpartition("/")[0] if "/" in path else "."
        folders.setdefault(parent, []).append((path, size, fmt, derivative))

    # Dataset root when everything is flat: skip the "." folder node and
    # attach files directly so single-dir datasets don't get a wrapper.
    flat = set(folders) == {"."}
    parents = ["."] if flat else sorted(folders)

    for parent in parents:
        parent_item = None
        if not flat:
            label = "Files" if parent == "." else parent + "/"
            parent_item = _new_item(label, label)
            try:
                parent_item.setIcon(icon("folder"))
            except Exception:
                pass
            parent_item.setData(
                {"kind": "folder", "dir": parent, "base": label}, _KIND_ROLE
            )
            size_item = _new_item("")
            fmt_item = _new_item("")
            scan_item = _new_item("")
            model.appendRow([parent_item, size_item, fmt_item, scan_item])
        for path, size, fmt, derivative in sorted(folders[parent]):
            staged = bool(is_staged(path)) if is_staged else False
            # Tabular originals: name the server derivative behind the file.
            note = (
                f"\nTabular ingest — server derivative: {derivative}"
                if derivative and derivative != path
                else ""
            )
            entry = by_path.get(path)
            checks = list(entry.checks) if entry else []
            if report is None:
                scan = "— run checks after download" if not staged else "Not checked"
                tip = path
            elif entry is None:
                scan = "Not in report"
                tip = f"{path}\nNot present in the check report."
            elif not checks:
                scan = "No automated check — manual review"
                tip = f"{path}\nNo automated check for this format."
            else:
                scan = status_label(checks)
                tip = path + "\n" + "\n".join(
                    f"[{c.level}] {c.check_id}: {c.message}" for c in checks
                )[:2000]
            base = path.split("/")[-1]
            name_item = _new_item(base, tip + note)
            try:
                name_item.setIcon(file_icon(path, staged=staged))
            except Exception:
                pass
            name_item.setData({"kind": "file", "path": path, "base": base}, _KIND_ROLE)
            size_item = _new_item(hs(size), f"{size} bytes")
            fmt_item = _new_item(fmt, fmt)
            scan_item = _new_item(scan, tip)
            file_row = [name_item, size_item, fmt_item, scan_item]
            for check in checks:
                badge = check_badge_text(check)
                kind = {"passed": "pass", "failed-warning": "warn",
                        "failed-error": "fail", "skipped": "skip"}.get(
                            classify(check), "pass")
                c_name = _new_item(
                    check.check_id,
                    format_details_tooltip(check),
                )
                try:
                    c_name.setIcon(status_icon(kind))
                except Exception:
                    pass
                c_name.setData(
                    {"kind": "check", "path": path, "check_id": check.check_id},
                    _KIND_ROLE,
                )
                c_size = _new_item("")
                c_fmt = _new_item("")
                c_scan = _new_item(f"{badge} — {check.message}", format_details_tooltip(check))
                name_item.appendRow([c_name, c_size, c_fmt, c_scan])
            if parent_item is not None:
                parent_item.appendRow(file_row)
            else:
                model.appendRow(file_row)

    if not flat:
        # Folder aggregate scan: worst child rank wins.
        for r in range(model.rowCount()):
            folder = model.item(r, 0)
            worst = 0
            counts = {"error": 0, "warning": 0, "skipped": 0, "clean": 0, "unchecked": 0}
            for i in range(folder.rowCount()):
                scan_text = folder.child(i, 3).text() if folder.child(i, 3) else ""
                if scan_text.startswith("Error"):
                    worst = max(worst, 4)
                    counts["error"] += 1
                elif scan_text.startswith("Warning"):
                    worst = max(worst, 3)
                    counts["warning"] += 1
                elif scan_text.startswith("Skipped"):
                    worst = max(worst, 2)
                    counts["skipped"] += 1
                elif scan_text.startswith("Clean"):
                    counts["clean"] += 1
                else:
                    counts["unchecked"] += 1
            label = {4: "Error", 3: "Warning", 2: "Skipped"}.get(worst, "")
            total = folder.rowCount()
            if label:
                model.item(r, 3).setText(
                    f"{label} · {counts['error']} err, {counts['warning']} warn, "
                    f"{counts['skipped']} skipped, {counts['clean']} clean ({total} files)"
                )
            else:
                model.item(r, 3).setText(f"{total} file(s)")
    return model


def node_kind(index) -> dict:
    try:
        from PySide6.QtCore import QModelIndex

        if not isinstance(index, QModelIndex) or not index.isValid():
            return {}
        model = index.model()
        item = model.itemFromIndex(model.index(index.row(), 0, index.parent()))
        data = item.data(_KIND_ROLE) if item else None
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def matches_status_filter(scan_text: str, check_rows: list[str], filt: str) -> bool:
    """File-level predicate for the status combo (applied with text filter)."""
    f = (filt or "all").lower()
    if f in ("all", ""):
        return True
    kinds = set()
    for badge in check_rows:
        kinds.add(badge)
    if f == "issues":
        return scan_text.startswith(("Error", "Warning"))
    if f == "errors":
        return scan_text.startswith("Error")
    if f == "warnings":
        return scan_text.startswith("Warning")
    if f == "skipped":
        return "skipped" in kinds or scan_text.startswith("Skipped")
    if f == "clean":
        return scan_text.startswith("Clean")
    if f in ("no check", "unchecked"):
        return scan_text.startswith("No automated")
    return True
