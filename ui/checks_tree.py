"""Folder > file > check tree model for the File Manifest card.

Carbon Tree View-inspired behavior (caret-left expanders, indented children,
arrow-key navigation via QTreeView) implemented natively in PySide6 with the
app's existing palette — Carbon web components are not available on desktop.

Node kinds (Qt.ItemDataRole.UserRole dict on column-0 item):
  folder: {"kind": "folder", "dir": str, "base": str}
  file:   {"kind": "file", "path": str, "base": str}
  check:  {"kind": "check", "path": str, "check_id": str}

Icons are Lucide (see ui/icons.py), set as item icons — never text glyphs:
folder/folder-open track expanded state, file icons follow the extension
(staged files ink, unstaged muted), check rows carry octagon-x (errors),
octagon-alert (warnings), check (passes) or circle-dashed (skipped).
Expand affordance itself is painted by the tree's own branch pass
(Lucide chevrons via ui.widgets._BranchPainting); update_carets() keeps
folder icons in sync with live expanded state and must run after every
expand/collapse (see dataset_detail).

Columns: Name | Size | Format | Scan. Folder rows aggregate children counts;
file rows show the scan aggregate (engine.status.status_label); check rows
show the full untruncated message with PASS/WARN/FAIL/SKIPPED badge text in
the Scan column and a details tooltip.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel

from curation.storage import finding_key
from engine.status import classify
from ui.check_titles import check_summary, check_title
from ui.i18n import t
from ui.icons import file_icon, icon, status_icon
from ui.status_text import status_text
from ui.widgets import disposition_label

COLUMNS = [
    t("checks.columns.name"),
    t("checks.columns.size"),
    t("checks.columns.format"),
    t("checks.columns.scan"),
]

_KIND_ROLE = Qt.ItemDataRole.UserRole + 1

# Legacy text glyphs (pre-Lucide). Kept so update_carets() can strip them
# from any model built before the icon switch; nothing emits them anymore.
_CARET_PREFIXES = ("▸ ", "▾ ")


def _strip_legacy_caret(text: str) -> str:
    try:
        for prefix in _CARET_PREFIXES:
            if text.startswith(prefix):
                return text[len(prefix) :]
    except Exception:
        pass
    return text


def update_carets(model, is_expanded) -> None:  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
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


def format_details_tooltip(result, path: str = "") -> str:
    """Prose tooltip for a check result (dv-r0z); see ui.check_titles."""
    from ui.check_titles import format_details_tooltip as _tooltip

    if not path:
        path = str(getattr(result, "path", "") or "")
    return _tooltip(result, path)


def _human_size(n: int) -> str:
    # Re-exported from the shared helper (dv-005): labels are decimal (KB/MB).
    from ui.widgets import human_size as _shared

    return _shared(n)


def variable_coverage(report) -> dict[str, dict[str, int]]:
    """Per-file ``{labeled, total}`` from the report's var-coverage check.

    The check (dv-tfy) rides its coverage map on the first result's details;
    returns {} when the check did not run or carried no map.
    """
    if report is None:
        return {}
    try:
        results = list(getattr(report, "dataset_checks", []) or [])
    except Exception:
        return {}
    for result in results:
        if getattr(result, "check_id", "") != "metadata.var_coverage":
            continue
        details = getattr(result, "details", None)
        if not isinstance(details, dict):
            return {}
        coverage = details.get("coverage")
        if isinstance(coverage, dict):
            return {str(path): dict(cov) for path, cov in coverage.items() if isinstance(cov, dict)}
        return {}
    return {}


def _new_item(text: str, tooltip: str = "") -> QStandardItem:
    item = QStandardItem(text)
    item.setEditable(False)
    if tooltip:
        item.setToolTip(tooltip)
    return item


def build_tree_model(  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
    rows, report=None, is_staged=None, human_size=None, inventory=None, dispositions=None
) -> QStandardItemModel:
    """Build the folder>file>check model.

    rows: list of (path, size_bytes, fmt, original) like _all_file_rows.
    report: DatasetReport or None (pre-run: file nodes only, no checks).
    is_staged: callable(path) -> bool (staged files render ink, others muted).
    inventory: optional raw inventory list (adds restricted/embargo/ingest notes).
    dispositions: optional {finding_key: {disposition, note}} (dv-32x) —
    check nodes with a recorded disposition carry its label in the Scan
    column and tooltip, and the context menu in dataset_detail edits them.
    """
    model = QStandardItemModel()
    # Titles stay in sentence case, like every other table in the app.
    # Casing lives in the model (not the style sheet) so Qt measures the
    # text it paints and a narrow column elides instead of clipping.
    model.setHorizontalHeaderLabels([str(c) for c in COLUMNS])
    hs = human_size or _human_size
    coverage = variable_coverage(report)
    by_path = {}
    if report is not None:
        by_path = {f.path: f for f in report.files}
    inv_by_path = {}
    if isinstance(inventory, list):
        for e in inventory:
            if isinstance(e, dict) and e.get("path"):
                inv_by_path[str(e["path"])] = e

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
            label = t("checks.files_folder") if parent == "." else parent + "/"
            parent_item = _new_item(label, label)
            try:
                parent_item.setIcon(icon("folder"))
            except Exception:
                pass
            parent_item.setData({"kind": "folder", "dir": parent, "base": label}, _KIND_ROLE)
            size_item = _new_item("")
            fmt_item = _new_item("")
            scan_item = _new_item("")
            model.appendRow([parent_item, size_item, fmt_item, scan_item])
        for path, size, fmt, derivative in sorted(folders[parent]):
            staged = bool(is_staged(path)) if is_staged else False
            # Tabular originals: name the server derivative behind the file.
            note = (
                "\n" + t("checks.tabular_ingest", derivative=derivative)
                if derivative and derivative != path
                else ""
            )
            # Restricted / embargo / retention / ingest notes from inventory.
            inv_entry = inv_by_path.get(path)
            if isinstance(inv_entry, dict):
                if inv_entry.get("restricted"):
                    note += "\n" + t("checks.access_restricted")
                embargo = str(inv_entry.get("embargo_date") or "").strip()
                if embargo:
                    note += "\n" + t("checks.embargo_until", date=embargo[:10])
                retention = str(inv_entry.get("retention") or "").strip()
                if retention:
                    note += "\n" + t("checks.retention", retention=retention)
                ingest_status = str(inv_entry.get("ingest_status") or "").strip()
                ingest_error = str(inv_entry.get("ingest_error") or "").strip()
                if ingest_status or ingest_error:
                    bits = (
                        [t("checks.ingest_status", status=ingest_status)] if ingest_status else []
                    )
                    if ingest_error:
                        bits.append(t("checks.ingest_error", error=ingest_error))
                    note += "\n" + t("common.separator").join(bits)
            entry = by_path.get(path)
            checks = list(entry.checks) if entry else []
            if report is None:
                scan = t("checks.run_after_download") if not staged else t("common.not_checked")
                tip = path
            elif entry is None:
                scan = t("checks.not_in_report")
                tip = f"{path}\n{t('checks.not_present')}"
            elif not checks:
                scan = t("checks.no_automated")
                tip = f"{path}\n{t('checks.no_auto_format')}"
            else:
                scan = status_text(checks)
                tip = (
                    path
                    + "\n"
                    + "\n".join(f"[{c.level}] {c.check_id}: {c.message}" for c in checks)[:2000]
                )
            # Append restriction/ingest notes to the Scan tooltip too.
            if note:
                tip = tip + note
            # Variable-metadata coverage (dv-tfy): a short suffix on the Scan
            # column plus the exact counts in the tooltip.
            cov = coverage.get(path)
            if isinstance(cov, dict):
                try:
                    labeled = int(cov.get("labeled") or 0)
                    total = int(cov.get("total") or 0)
                except (TypeError, ValueError):
                    # A stale/hand-written report may carry non-numeric
                    # coverage; never take down the manifest-tree build.
                    labeled = total = 0
                if total or labeled:
                    scan = scan + t("checks.var_coverage_suffix", labeled=labeled, total=total)
                    tip = tip + "\n" + t("checks.var_coverage_tip", labeled=labeled, total=total)
            base = path.split("/")[-1]
            name_item = _new_item(base, tip)
            try:
                name_item.setIcon(file_icon(path, staged=staged))
            except Exception:
                pass
            name_item.setData({"kind": "file", "path": path, "base": base}, _KIND_ROLE)
            size_item = _new_item(hs(size), t("checks.size_bytes", size=size))
            fmt_item = _new_item(fmt, fmt)
            scan_item = _new_item(scan, tip)
            file_row = [name_item, size_item, fmt_item, scan_item]
            for check in checks:
                kind = {
                    "passed": "pass",
                    "failed-warning": "warn",
                    "failed-error": "fail",
                    "skipped": "skip",
                }.get(classify(check), "pass")
                # Disposition reflection (dv-32x): the label joins the Scan
                # text so a resolved finding reads as dealt-with at a glance.
                token = ""
                try:
                    token = str(
                        (dispositions or {})
                        .get(finding_key(check.check_id, path, check.message), {})
                        .get("disposition")
                        or ""
                    )
                except Exception:
                    token = ""
                # dv-r0z: the row is named for a person ("CSV Openable"), and
                # the Scan column is a sentence about what was verified — no
                # check_id, no PASS/WARN badge, no filename the row already
                # shows. The status still rides on the name cell's icon.
                scan_text = check_summary(check, path)
                tip = format_details_tooltip(check, path)
                if token:
                    label = disposition_label(token)
                    scan_text += t("common.separator") + label
                    tip += "\n" + t("detail.disposition.tree_note", label=label)
                c_name = _new_item(
                    check_title(check.check_id),
                    tip,
                )
                try:
                    c_name.setIcon(status_icon(kind))
                except Exception:
                    pass
                c_name.setData(
                    {
                        "kind": "check",
                        "path": path,
                        "check_id": check.check_id,
                        "msg": check.message,
                    },
                    _KIND_ROLE,
                )
                c_size = _new_item("")
                c_fmt = _new_item("")
                c_scan = _new_item(
                    scan_text,
                    tip,
                )
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
                if scan_text.startswith(t("status.error")):
                    worst = max(worst, 4)
                    counts["error"] += 1
                elif scan_text.startswith(t("status.warning")):
                    worst = max(worst, 3)
                    counts["warning"] += 1
                elif scan_text.startswith(t("status.skipped")):
                    worst = max(worst, 2)
                    counts["skipped"] += 1
                elif scan_text.startswith(t("status.clean")):
                    counts["clean"] += 1
                else:
                    counts["unchecked"] += 1
            label = {
                4: t("status.error"),
                3: t("status.warning"),
                2: t("status.skipped"),
            }.get(worst, "")
            total = folder.rowCount()
            if label:
                model.item(r, 3).setText(
                    t(
                        "status.folder.label",
                        label=label,
                        errors=counts["error"],
                        warnings=counts["warning"],
                        skipped=counts["skipped"],
                        clean=counts["clean"],
                        total=total,
                    )
                )
            else:
                model.item(r, 3).setText(t("status.folder.count", total=total))
    return model


def node_kind(index) -> dict:
    try:
        from PySide6.QtCore import QModelIndex
        from PySide6.QtGui import QStandardItemModel

        if not isinstance(index, QModelIndex) or not index.isValid():
            return {}
        model = index.model()
        if not isinstance(model, QStandardItemModel):
            return {}
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
        return scan_text.startswith((t("status.error"), t("status.warning")))
    if f == "errors":
        return scan_text.startswith(t("status.error"))
    if f == "warnings":
        return scan_text.startswith(t("status.warning"))
    if f == "skipped":
        return "skipped" in kinds or scan_text.startswith(t("status.skipped"))
    if f == "clean":
        return scan_text.startswith(t("status.clean"))
    if f in ("no check", "unchecked"):
        return scan_text.startswith(t("checks.no_automated_prefix"))
    return True
