"""Review configuration page: rule-driven metadata checks + response templates.

Two columns:
  left  — which metadata fields are required / optional / not checked
          (from the live metadatablocks catalog when available) plus custom
          text-search rules (filenames / metadata / file-content, e.g. README).
  right — standard response text per rule + global header/footer used by the
          per-dataset Response pane.

Rulesets are global by default; each ruleset lists the Dataverse base URLs it
applies to ("*" = all). Stored as requirements_profiles.json v2.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidgetItem,
    QSplitter,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config import Config
from ui.dialogs import show_critical, show_info, show_warning
from ui.table_layout import TableLayout
from ui.theme import page_background_qss, selectable_labels
from ui.widgets import (
    AppTreeWidget,
    make_action_button,
    make_card,
    make_checkbox,
    make_combo,
    make_line_edit,
    make_list,
    make_multiline_input,
    make_page_heading,
    make_reset_columns_button,
    make_search_field,
)

_LEVELS = ["required", "optional", "unchecked"]


class ContentRuleDialog(QDialog):
    """Add/edit one text-search rule (filenames / metadata / file-content)."""

    def __init__(self, parent=None, rule: dict[str, Any] | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Content rule")
        self.resize(520, 560)
        rule = rule or {}
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self._label = make_line_edit("e.g. README file")
        self._label.setText(str(rule.get("label") or ""))
        form.addRow("Label:", self._label)
        self._level = make_combo([("Required", "required"), ("Optional", "optional")], min_width=160)
        lvl = str(rule.get("level") or "required")
        self._level.setCurrentIndex(0 if lvl != "optional" else 1)
        form.addRow("Level:", self._level)
        scope = rule.get("scope") if isinstance(rule.get("scope"), list) else ["filenames"]
        self._cb_files = make_checkbox("Filenames / inventory paths (no download needed)")
        self._cb_meta = make_checkbox("Metadata values")
        self._cb_content = make_checkbox("Text inside staged files (needs download)")
        self._cb_files.setChecked("filenames" in scope)
        self._cb_meta.setChecked("metadata" in scope)
        self._cb_content.setChecked("file-content" in scope)
        scope_box = QVBoxLayout()
        scope_box.addWidget(self._cb_files)
        scope_box.addWidget(self._cb_meta)
        scope_box.addWidget(self._cb_content)
        scope_wrap = QWidget()
        scope_wrap.setLayout(scope_box)
        form.addRow("Search in:", scope_wrap)
        self._match = make_combo(
            [("Filename pattern (readme*)", "filename-glob"),
             ("Text contains", "substring"), ("Regular expression", "regex")],
            min_width=200,
        )
        m = str(rule.get("match") or "filename-glob")
        idx = {"filename-glob": 0, "substring": 1, "regex": 2}.get(m, 0)
        self._match.setCurrentIndex(idx)
        form.addRow("Match:", self._match)
        self._pattern = make_line_edit("readme*  or  funding acknowledgement  or  \\bCC-BY\\b")
        self._pattern.setText(str(rule.get("pattern") or ""))
        form.addRow("Pattern:", self._pattern)
        self._case = make_checkbox(
            "Case sensitive", checked=bool(rule.get("case_sensitive"))
        )
        form.addRow("", self._case)
        lay.addLayout(form)
        lay.addWidget(QLabel("Response text when this rule fails:"))
        self._template = make_multiline_input(fixed=False, min_height=120)
        self._template.setPlainText(str(rule.get("response_template") or ""))
        lay.addWidget(self._template, 1)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def result_rule(self, rule_id: str = "") -> dict[str, Any] | None:
        label = self._label.text().strip()
        pattern = self._pattern.text().strip()
        if not label or not pattern:
            return None
        scope = []
        if self._cb_files.isChecked():
            scope.append("filenames")
        if self._cb_meta.isChecked():
            scope.append("metadata")
        if self._cb_content.isChecked():
            scope.append("file-content")
        if not scope:
            scope = ["filenames"]
        import re as _re

        base = _re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "rule"
        return {
            "id": rule_id or base,
            "label": label,
            "level": self._level.currentData() or "required",
            "requirement": f"Custom — {'Required' if (self._level.currentData() or 'required') == 'required' else 'Recommended'} ({label})",
            "scope": scope,
            "match": self._match.currentData() or "filename-glob",
            "pattern": pattern,
            "case_sensitive": self._case.isChecked(),
            "response_template": self._template.toPlainText().strip(),
        }


class ReviewConfigView(QWidget):
    """Full-page replacement for the old Requirements JSON dialog."""

    saved = Signal()

    def __init__(self, config: Config, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self._worker = None
        try:
            import review_rules as _rr

            self._rr = _rr
            self._rulesets: dict[str, dict[str, Any]] = copy.deepcopy(_rr.load_rulesets())
        except Exception:
            self._rr = None  # type: ignore[assignment]
            self._rulesets = {}
        self._current = self._pick_initial_key()
        self._schema: list[dict[str, str]] | None = self._load_cached_schema()
        # selection for the right-hand template editor
        self._sel_kind: str = "field"  # field | content | header | footer
        self._sel_key: str = ""
        self._loading = False
        # Unsaved-chip: any in-memory ruleset edit sets it, Save/Revert clear
        # it. Guards against losing edits by navigating away unnoticed.
        self._dirty = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(16)
        # Scoped to self: a bare `background` rule would act subtree-wide
        # and override app-level backgrounds below this view.
        self.setObjectName("ReviewConfigView")
        self.setStyleSheet(page_background_qss("ReviewConfigView"))

        # Shared page-heading contract (HeadlineLG theme token) — same
        # title look as Settings, Log, and About.
        title, _subtitle = make_page_heading("Review configuration")
        outer.addWidget(title)

        outer.addWidget(self._build_topbar())

        split = QSplitter(Qt.Horizontal)
        split.addWidget(self._build_rules_card())
        split.addWidget(self._build_templates_card())
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        outer.addWidget(split, 1)

        self._status = QLabel("")
        self._status.setObjectName("CaptionSM")
        outer.addWidget(self._status)

        selectable_labels(self)
        self._refresh_all()

    # -- setup ------------------------------------------------------------

    def _pick_initial_key(self) -> str:
        try:
            base = (self._config.dataverse.base_url or "").rstrip("/").lower()
            for key, rs in (self._rulesets or {}).items():
                dvs = {(d or "").rstrip("/").lower() for d in (rs.get("dataverses") or []) if isinstance(d, str)}
                if base and base in dvs:
                    return key
        except Exception:
            pass
        if getattr(self, "_current", "") in (self._rulesets or {}):
            return self._current  # type: ignore[no-any-return]
        if "mcmaster-default" in (self._rulesets or {}):
            return "mcmaster-default"
        try:
            return sorted((self._rulesets or {}).keys())[0]
        except Exception:
            return "mcmaster-default"

    def _load_cached_schema(self) -> list[dict[str, str]] | None:
        try:
            from dataverse_client import read_metadata_fields_cache

            ws = Path(getattr(getattr(self._config, "app", None), "workspace", Path.home()))
            hit = read_metadata_fields_cache(Path(ws), self._config.dataverse.base_url)
            if hit:
                return hit
        except Exception:
            pass
        return None

    def _current_ruleset(self) -> dict[str, Any]:
        rs = (self._rulesets or {}).get(self._current)
        if isinstance(rs, dict):
            return rs
        # Defensive: never edit a missing ruleset.
        fallback = {"label": self._current, "dataverses": ["*"], "field_rules": [],
                    "content_rules": [], "filecheck_templates": {},
                    "response_header": "", "response_footer": ""}
        self._rulesets[self._current] = fallback
        return fallback

    # -- builders ----------------------------------------------------------

    def _build_topbar(self) -> QWidget:
        card, body, _t, _h = make_card("Ruleset")
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("Ruleset:"))
        self._ruleset_combo = make_combo(min_width=260)
        self._ruleset_combo.currentIndexChanged.connect(self._on_ruleset_changed)
        row.addWidget(self._ruleset_combo, 1)
        self._dirty_chip = QLabel("● unsaved")
        # The unsaved marker is a caution: it wears the theme's warning
        # token rather than painting its own amber.
        self._dirty_chip.setObjectName("WarningSM")
        self._dirty_chip.hide()
        row.addWidget(self._dirty_chip)
        for text, slot in [("New…", self._on_new), ("Duplicate", self._on_duplicate), ("Delete", self._on_delete)]:
            b = make_action_button(text, kind="secondary", size="sm")
            b.clicked.connect(slot)
            row.addWidget(b)
        body.addLayout(row)
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(QLabel("Use for Dataverse(s):"))
        self._dataverses_edit = make_line_edit(
            "*  or  https://demo.borealisdata.ca, https://…"
        )
        self._dataverses_edit.setToolTip("Comma-separated base URLs, or * for every Dataverse")
        self._dataverses_edit.editingFinished.connect(self._on_dataverses_edited)
        row2.addWidget(self._dataverses_edit, 1)
        self._fields_btn = make_action_button(
            "Load fields from Dataverse", kind="secondary", size="sm"
        )
        self._fields_btn.clicked.connect(self._on_load_fields)
        row2.addWidget(self._fields_btn)
        self._save_btn = make_action_button("Save", kind="primary", size="sm")
        self._save_btn.clicked.connect(self._on_save)
        row2.addWidget(self._save_btn)
        revert = make_action_button("Revert", kind="secondary", size="sm")
        revert.clicked.connect(self._on_revert)
        row2.addWidget(revert)
        body.addLayout(row2)
        return card

    def _build_rules_card(self) -> QWidget:
        card, body, _t, header_lay = make_card("Checks")
        # Filters live in the card header (file-manifest pattern): text
        # search + required-status dropdown + expand/collapse toggle.
        self._field_filter = make_search_field("Filter fields...", height=36, min_width=160)
        # Debounced like the dashboard search: rebuild the tree 200 ms after
        # the last keystroke so typing never loses focus mid-word.
        from PySide6.QtCore import QTimer as _QTimer

        self._filter_timer = _QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(200)
        self._filter_timer.timeout.connect(self._refresh_field_table)
        self._field_filter.textChanged.connect(lambda _t: self._filter_timer.start())
        header_lay.addWidget(self._field_filter)
        self._level_filter = make_combo(
            [("All statuses", "all"), ("Required", "required"),
             ("Optional", "optional"), ("Not checked", "unchecked")],
            height=36,
            min_width=130,
            tip="Show only fields with this required status",
        )
        self._level_filter.currentIndexChanged.connect(lambda _i: self._refresh_field_table())
        header_lay.addWidget(self._level_filter)
        self._blocks_btn = make_action_button("Collapse all", kind="secondary", size="md")
        self._blocks_btn.setToolTip("Expand or collapse every metadata block")
        self._blocks_btn.clicked.connect(self._on_toggle_blocks)
        header_lay.addWidget(self._blocks_btn)
        self._fields_reset_btn = make_reset_columns_button(
            "metadata fields", tip="Reset columns and widths to default"
        )
        self._fields_reset_btn.clicked.connect(self._on_reset_field_view)
        header_lay.addWidget(self._fields_reset_btn)
        hint = QLabel("Required / Optional / Not checked — per metadata field broadcast by the Dataverse, grouped by block.")
        hint.setWordWrap(True)
        hint.setObjectName("CaptionSM")
        body.addWidget(hint)
        # Block-grouped tree (replaces the flat table): block parents with
        # native expand/collapse, one child row per field rule with its
        # level combo. Sorting stays OFF on purpose — children are cell
        # *widgets*, which Qt does not move when rows sort.
        self._field_tree = AppTreeWidget(row_height=None, flush=False)
        self._field_tree.setColumnCount(2)
        self._field_tree.setHeaderLabels(["Field", "Check"])
        self._field_tree.setRootIsDecorated(True)
        self._field_tree.setExpandsOnDoubleClick(True)
        self._field_tree.setAnimated(True)
        self._field_tree.setIndentation(18)
        self._field_tree.setMinimumHeight(260)
        # The standard tree chrome comes with the widget (framed: this
        # tree lives inside a card body).
        _fld_header = self._field_tree.header()
        _fld_header.setStretchLastSection(False)
        _fld_header.setSectionResizeMode(0, QHeaderView.Stretch)
        _fld_header.setSectionResizeMode(1, QHeaderView.Interactive)
        self._field_tree.setColumnWidth(1, 150)
        # Remember the user's column widths/order across sessions. The
        # controller owns the persistence: it saves user gestures only.
        try:
            self._fields_layout = TableLayout(
                self._config.app.workspace,
                "review_fields",
                _fld_header,
                view=self._field_tree,
            )
            self._fields_layout.restore()
        except Exception:
            pass
        self._floor_check_column()
        self._field_tree.itemSelectionChanged.connect(self._on_field_selected)
        body.addWidget(self._field_tree, 1)
        body.addWidget(QLabel("Text rules (e.g. README — search filenames, metadata, file contents):"))
        self._content_list = make_list()
        self._content_list.setMinimumHeight(110)
        self._content_list.itemSelectionChanged.connect(self._on_content_selected)
        body.addWidget(self._content_list)
        row = QHBoxLayout()
        for text, slot in [("Add rule…", self._on_content_add), ("Edit…", self._on_content_edit), ("Delete", self._on_content_delete)]:
            b = make_action_button(text, kind="secondary", size="sm")
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        body.addLayout(row)
        return card

    def _build_templates_card(self) -> QWidget:
        card, body, _t, _h = make_card("Response text")
        self._sel_label = QLabel("Select a field or text rule to edit its response text.")
        self._sel_label.setWordWrap(True)
        self._sel_label.setObjectName("LabelStrongSM")
        body.addWidget(self._sel_label)
        self._template_edit = make_multiline_input(
            "Standard sentence inserted into the Response draft when this check fails…\n"
            "Placeholders: {field} {value} {dataset_title} {persistent_id} {path} {message}",
            fixed=False,
            min_height=130,
        )
        self._template_edit.textChanged.connect(self._on_template_edited)
        body.addWidget(self._template_edit)
        body.addWidget(QLabel("Draft header (opening paragraph):"))
        self._header_edit = make_multiline_input(fixed=False, min_height=70)
        self._header_edit.textChanged.connect(self._on_header_footer_edited)
        body.addWidget(self._header_edit)
        body.addWidget(QLabel("Draft footer (closing paragraph):"))
        self._footer_edit = make_multiline_input(fixed=False, min_height=70)
        self._footer_edit.textChanged.connect(self._on_header_footer_edited)
        body.addWidget(self._footer_edit, 1)
        note = QLabel("File-check findings (warnings/errors) use these templates too — edit per-check text under the ruleset JSON for now; the common cases are covered by the default “{check_id}: {message}” template.")
        note.setWordWrap(True)
        note.setObjectName("CaptionSM")
        body.addWidget(note)
        return card

    # -- data -> ui --------------------------------------------------------

    def _schema_fields(self) -> list[dict[str, str]]:
        if self._schema:
            return [dict(f) for f in self._schema if isinstance(f, dict) and f.get("field")]
        try:
            from review_rules import FIELD_CATALOG

            base = [dict(f) for f in FIELD_CATALOG]
        except Exception:
            base = []
        # Union with fields referenced by any ruleset so custom fields persist.
        seen = {(f.get("block"), f.get("field")) for f in base}
        for rs in (self._rulesets or {}).values():
            for fr in (rs.get("field_rules") or []):
                if not isinstance(fr, dict):
                    continue
                key = (str(fr.get("block") or "citation"), str(fr.get("field") or ""))
                if key[1] and key not in seen:
                    seen.add(key)
                    base.append({"block": key[0], "field": key[1], "label": str(fr.get("label") or key[1])})
        return sorted(base, key=lambda f: (f.get("block") or "", f.get("field") or ""))

    def _rule_entries(self) -> list[dict[str, Any]]:
        """One row per field rule plus unchecked schema leftovers.

        Rows are keyed by (block, field, handler): several rules may share
        one field (e.g. Author names vs ORCiDs both live on citation.author),
        so a plain (block, field) key would collide and edit the wrong rule.
        """
        entries: list[dict[str, Any]] = []
        covered: set = set()
        schema_labels = {
            (str(f.get("block") or ""), str(f.get("field") or "")): str(f.get("block_label") or "")
            for f in self._schema_fields()
        }
        for fr in (self._current_ruleset().get("field_rules") or []):
            if not isinstance(fr, dict) or not fr.get("field"):
                continue
            block = str(fr.get("block") or "citation")
            field = str(fr.get("field") or "")
            handler = str(fr.get("handler") or "nonempty")
            covered.add((block, field, handler))
            entries.append({
                "kind": "rule", "label": str(fr.get("label") or field),
                "block": block, "field": field, "handler": handler,
                "block_label": schema_labels.get((block, field), ""),
                "level": fr.get("level") if fr.get("level") in ("required", "optional") else "required",
                "req": str(fr.get("requirement") or ""),
            })
        for f in self._schema_fields():
            block, field = str(f.get("block") or ""), str(f.get("field") or "")
            if not field or any((block, field) == (b, fl) for b, fl, _h in covered):
                continue
            entries.append({
                "kind": "new", "label": str(f.get("label") or field),
                "block": block, "field": field, "handler": "nonempty",
                "block_label": str(f.get("block_label") or ""),
                "level": "unchecked", "req": "",
            })
        return entries

    @staticmethod
    def _block_display_name(block: str, label: str = "") -> str:
        """Proper block name: catalog display name, else capitalized id."""
        try:
            b = str(block or "").strip()
            # License / terms rules live under a synthetic "license" block so
            # they group under one heading in the field tree.
            if b == "license" and not str(label or "").strip():
                return "License and Terms of Use"
            if str(label or "").strip():
                return str(label).strip()
            return (b[:1].upper() + b[1:]) if b else "Other"
        except Exception:
            return str(block or "Other")

    def _refresh_all(self) -> None:
        self._loading = True
        try:
            self._ruleset_combo.blockSignals(True)
            self._ruleset_combo.clear()
            for key, rs in (self._rulesets or {}).items():
                self._ruleset_combo.addItem(f"{rs.get('label', key)}", key)
            idx = self._ruleset_combo.findData(self._current)
            self._ruleset_combo.setCurrentIndex(idx if idx >= 0 else 0)
            if self._ruleset_combo.currentData() and self._current not in (self._rulesets or {}):
                self._current = str(self._ruleset_combo.currentData())
        finally:
            self._ruleset_combo.blockSignals(False)
        rs = self._current_ruleset()
        self._dataverses_edit.setText(", ".join(rs.get("dataverses") or ["*"]))
        self._header_edit.blockSignals(True)
        self._footer_edit.blockSignals(True)
        try:
            self._header_edit.setPlainText(str(rs.get("response_header") or ""))
            self._footer_edit.setPlainText(str(rs.get("response_footer") or ""))
        finally:
            self._header_edit.blockSignals(False)
            self._footer_edit.blockSignals(False)
        self._refresh_field_table()
        self._refresh_content_list()
        self._loading = False

    def _refresh_field_table(self) -> None:
        """Rebuild the block-grouped field tree (text + status filters apply)."""
        try:
            filt = (self._field_filter.text() or "").strip().lower()
        except Exception:
            filt = ""
        try:
            status = self._level_filter.currentData() or "all"
        except Exception:
            status = "all"
        groups: dict[str, list] = {}
        group_labels: dict[str, str] = {}
        for e in self._rule_entries():
            if status != "all" and str(e.get("level") or "") != status:
                continue
            hay = f"{e.get('label','')} {e.get('block','')} {e.get('field','')} {e.get('handler','')}".lower()
            if filt and filt not in hay:
                continue
            block = str(e.get("block") or "citation")
            groups.setdefault(block, []).append(e)
            if block not in group_labels:
                group_labels[block] = self._block_display_name(block, str(e.get("block_label") or ""))
        tree = self._field_tree
        try:
            # Block the header too (not just the tree): adding/clearing rows
            # toggles the vertical scrollbar, which recomputes the stretch
            # column and would otherwise persist a mid-rebuild width.
            tree.blockSignals(True)
            tree.header().blockSignals(True)
            tree.clear()
            n_fields = 0
            # Citation block always first; the rest alphabetical by
            # display name (group key match is case-insensitive).
            ordered = sorted(
                groups,
                key=lambda b: (
                    0 if str(b or "").lower() == "citation" else 1,
                    group_labels.get(b, b).lower(),
                ),
            )
            for block in ordered:
                label = group_labels.get(block, block)
                rows = sorted(groups[block], key=lambda e: str(e.get("label") or e.get("field") or ""))
                top = QTreeWidgetItem([f"{label} ({len(rows)})"])
                try:
                    fnt = top.font(0)
                    fnt.setBold(True)
                    top.setFont(0, fnt)
                except Exception:
                    pass
                top.setData(0, Qt.UserRole, {"kind": "block", "block": block})
                top.setToolTip(0, f"Metadata block “{label}” — {len(rows)} field(s)")
                top.setExpanded(True)
                # Top item joins the tree first: setItemWidget needs the
                # child row present before the combo is attached.
                tree.addTopLevelItem(top)
                for e in rows:
                    block, field = e["block"], e["field"]
                    child = QTreeWidgetItem([str(e.get("label") or field)])
                    child.setToolTip(0, f"{block}.{field} — {e['handler']}" + (f"\n{e['req']}" if e["req"] else ""))
                    child.setData(0, Qt.UserRole, {"kind": "field"})
                    # Compact 32px combos: the standard 36px face makes
                    # 35-row blocks (citation) scroll forever; 32px still
                    # clears the 12px text + theme padding without clipping.
                    combo = make_combo([("Required", "required"), ("Optional", "optional"), ("Not checked", "unchecked")],
                                       height=32, min_width=110)
                    combo.setCurrentIndex({"required": 0, "optional": 1, "unchecked": 2}.get(e["level"], 2))
                    combo.setProperty("kind", e["kind"])
                    combo.setProperty("block", block)
                    combo.setProperty("field", field)
                    combo.setProperty("handler", e["handler"])
                    combo.currentIndexChanged.connect(self._on_field_level_changed)
                    top.addChild(child)
                    n_fields += 1
                    tree.setItemWidget(child, 1, combo)
            tree.expandAll()
            self._update_blocks_btn()
        finally:
            try:
                tree.header().blockSignals(False)
            except Exception:
                pass
            try:
                tree.blockSignals(False)
            except Exception:
                pass
        try:
            self._status.setText(
                f"{n_fields} field(s) in {len(groups)} block(s) shown"
                + (" — live Dataverse catalog" if self._schema else " — built-in catalog (press “Load fields from Dataverse”)")
            )
        except Exception:
            pass

    def _selected_field_combo(self):
        """Level combo of the selected field row (None for block rows)."""
        try:
            items = self._field_tree.selectedItems()
            if not items:
                return None
            combo = self._field_tree.itemWidget(items[0], 1)
            return combo if isinstance(combo, QComboBox) else None
        except Exception:
            return None

    def _find_combo_item(self, combo):
        """Tree child item hosting a level combo (for in-place updates)."""
        try:
            tree = self._field_tree
            for bi in range(tree.topLevelItemCount()):
                top = tree.topLevelItem(bi)
                for ci in range(top.childCount()):
                    child = top.child(ci)
                    if tree.itemWidget(child, 1) is combo:
                        return child
        except Exception:
            pass
        return None

    def _blocks_any_collapsed(self) -> bool:
        try:
            for bi in range(self._field_tree.topLevelItemCount()):
                if not self._field_tree.topLevelItem(bi).isExpanded():
                    return True
            return False
        except Exception:
            return False

    def _update_blocks_btn(self) -> None:
        try:
            self._blocks_btn.setText(
                "Collapse all" if not self._blocks_any_collapsed() else "Expand all"
            )
        except Exception:
            pass

    def _on_toggle_blocks(self) -> None:
        try:
            if self._blocks_any_collapsed():
                self._field_tree.expandAll()
            else:
                self._field_tree.collapseAll()
            self._update_blocks_btn()
        except Exception:
            pass

    def _floor_check_column(self) -> None:
        """Floor the Check column at the combos' measured need.

        Narrower squeezes "Not checked" + chevron. Also repairs stale
        110px restores from the old 3-column table era. Signals stay
        blocked: the floor is a correction, not a user edit, so it must
        not re-save (reset would otherwise immediately re-persist).
        """
        try:
            header = self._field_tree.header()
            _probe = make_combo(
                [("Required", "required"), ("Optional", "optional"),
                 ("Not checked", "unchecked")],
                height=32, min_width=110,
            )
            _need = _probe.sizeHint().width() + 8
            if header.sectionSize(1) < _need:
                try:
                    header.blockSignals(True)
                    header.resizeSection(1, _need)
                finally:
                    try:
                        header.blockSignals(False)
                    except Exception:
                        pass
        except Exception:
            pass

    def _on_reset_field_view(self) -> None:
        """Reset the field tree to its construction view, then rebuild."""
        try:
            layout = getattr(self, "_fields_layout", None)
            if layout is not None:
                layout.reset()
            self._floor_check_column()
            self._refresh_field_table()
        except Exception:
            pass

    def _refresh_content_list(self) -> None:
        try:
            self._content_list.blockSignals(True)
            self._content_list.clear()
            for cr in (self._current_ruleset().get("content_rules") or []):
                if not isinstance(cr, dict):
                    continue
                scope = ", ".join(cr.get("scope") or [])
                item = QListWidgetItem(f"{cr.get('label','rule')}  [{cr.get('level','required')}]  ({scope})")
                item.setData(Qt.UserRole, str(cr.get("id") or ""))
                item.setToolTip(f"Pattern: {cr.get('pattern','')}\nMatch: {cr.get('match','')}\n{cr.get('response_template','')[:200]}")
                self._content_list.addItem(item)
        finally:
            try:
                self._content_list.blockSignals(False)
            except Exception:
                pass

    # -- slots --------------------------------------------------------------

    def _on_ruleset_changed(self, _i: int) -> None:
        try:
            key = self._ruleset_combo.currentData()
            if isinstance(key, str) and key in (self._rulesets or {}):
                self._current = key
                self._sel_kind, self._sel_key = "field", ""
                self._refresh_all()
        except Exception:
            pass

    def _find_field_rule(self, block: str, field: str, handler: str) -> dict[str, Any] | None:
        for fr in (self._current_ruleset().get("field_rules") or []):
            if not isinstance(fr, dict):
                continue
            if (str(fr.get("block") or "citation") == block
                    and str(fr.get("field") or "") == field
                    and str(fr.get("handler") or "nonempty") == handler):
                return fr
        return None

    @staticmethod
    def _rule_sel_key(block: str, field: str, handler: str) -> str:
        return f"{block}\x1ffield\x1f{handler}"

    def _mark_dirty(self) -> None:
        """Surface that an edit landed in memory but not on disk."""
        if self._loading or self._dirty:
            return
        self._dirty = True
        self._dirty_chip.show()

    def _clear_dirty(self) -> None:
        if not self._dirty:
            return
        self._dirty = False
        self._dirty_chip.hide()

    def _on_field_selected(self) -> None:
        """Point the template editor at the selected field row."""
        if self._loading:
            return
        try:
            combo = self._selected_field_combo()
            if combo is None:
                return
            self._sel_kind = "field"
            self._sel_key = self._rule_sel_key(
                str(combo.property("block") or ""), str(combo.property("field") or ""),
                str(combo.property("handler") or "nonempty"),
            )
            self._show_template_for_selection()
        except Exception:
            pass

    def _on_field_level_changed(self, _i: int) -> None:
        if self._loading:
            return
        try:
            combo = self.sender()
            if not isinstance(combo, QComboBox):
                return
            kind = str(combo.property("kind") or "new")
            block, field = str(combo.property("block") or ""), str(combo.property("field") or "")
            handler = str(combo.property("handler") or "nonempty")
            level = combo.currentData() or "required"
            rs = self._current_ruleset()
            rules = [r for r in (rs.get("field_rules") or []) if isinstance(r, dict)]
            found = self._find_field_rule(block, field, handler)
            if level == "unchecked":
                if found is not None and kind == "rule":
                    rules.remove(found)
            else:
                if found is None:
                    label = next((f.get("label") or field for f in self._schema_fields()
                                  if f.get("block") == block and f.get("field") == field), field)
                    found = {"block": block, "field": field, "label": label,
                             "requirement": f"Custom — {'Required' if level == 'required' else 'Recommended'} ({label})",
                             "handler": "nonempty",
                             "response_template": f"The dataset is missing {label}. Please provide it."}
                    rules.append(found)
                    handler = "nonempty"
                found["level"] = level
            rs["field_rules"] = rules
            self._mark_dirty()
            self._sel_kind = "field"
            self._sel_key = self._rule_sel_key(block, field, handler)
            # Update this row in place (never rebuild the tree here: the
            # emitting combo would be destroyed mid-signal).
            try:
                child = self._find_combo_item(combo)
                if child is not None:
                    combo.setProperty("kind", "rule" if found is not None and level != "unchecked" else "new")
                    if found is not None and level != "unchecked":
                        tip_req = str(found.get("requirement") or "")
                        child.setToolTip(0, f"{block}.{field} — {handler}" + (f"\n{tip_req}" if tip_req else ""))
            except Exception:
                pass
            self._show_template_for_selection()
        except Exception:
            pass

    def _selected_content_rule(self) -> dict[str, Any] | None:
        try:
            item = self._content_list.currentItem()
            rid = item.data(Qt.UserRole) if item else ""
            for cr in (self._current_ruleset().get("content_rules") or []):
                if isinstance(cr, dict) and str(cr.get("id")) == str(rid):
                    return cr
        except Exception:
            pass
        return None

    def _on_content_selected(self) -> None:
        cr = self._selected_content_rule()
        if cr is not None:
            self._sel_kind, self._sel_key = "content", str(cr.get("id") or "")
            self._show_template_for_selection()

    def _show_template_for_selection(self) -> None:
        self._template_edit.blockSignals(True)
        try:
            if self._sel_kind == "content":
                cr = next((c for c in (self._current_ruleset().get("content_rules") or [])
                           if isinstance(c, dict) and str(c.get("id")) == self._sel_key), None)
                if cr is None:
                    return
                self._sel_label.setText(f"Response text — text rule “{cr.get('label','')}”")
                self._template_edit.setPlainText(str(cr.get("response_template") or ""))
            else:
                parts = self._sel_key.split("\x1f")
                fr = self._find_field_rule(parts[0], parts[1], parts[2]) if len(parts) == 3 else None
                # Fall back to the tree's current row when nothing chosen yet.
                if fr is None:
                    try:
                        combo = self._selected_field_combo()
                        if combo is not None:
                            fr = self._find_field_rule(
                                str(combo.property("block") or ""),
                                str(combo.property("field") or ""),
                                str(combo.property("handler") or "nonempty"),
                            )
                            if fr is not None:
                                self._sel_key = self._rule_sel_key(
                                    str(combo.property("block") or ""),
                                    str(combo.property("field") or ""),
                                    str(combo.property("handler") or "nonempty"),
                                )
                    except Exception:
                        fr = None
                if fr is None:
                    self._sel_label.setText("Select a field or text rule to edit its response text.")
                    self._template_edit.setPlainText("")
                    return
                self._sel_label.setText(f"Response text — “{fr.get('label', fr.get('field'))}”")
                self._template_edit.setPlainText(str(fr.get("response_template") or ""))
        finally:
            self._template_edit.blockSignals(False)

    def _on_template_edited(self) -> None:
        if self._loading:
            return
        try:
            text = self._template_edit.toPlainText()
            if self._sel_kind == "content":
                for cr in (self._current_ruleset().get("content_rules") or []):
                    if isinstance(cr, dict) and str(cr.get("id")) == self._sel_key:
                        cr["response_template"] = text
                        break
            elif self._sel_key:
                parts = self._sel_key.split("\x1f")
                if len(parts) == 3:
                    fr = self._find_field_rule(parts[0], parts[1], parts[2])
                    if fr is not None:
                        fr["response_template"] = text
            self._mark_dirty()
        except Exception:
            pass

    def _on_header_footer_edited(self) -> None:
        if self._loading:
            return
        try:
            self._current_ruleset()["response_header"] = self._header_edit.toPlainText()
            self._current_ruleset()["response_footer"] = self._footer_edit.toPlainText()
            self._mark_dirty()
        except Exception:
            pass

    def _on_dataverses_edited(self) -> None:
        try:
            raw = self._dataverses_edit.text() or "*"
            dvs = [d.strip().rstrip("/") for d in raw.split(",") if d.strip()]
            self._current_ruleset()["dataverses"] = dvs or ["*"]
            self._mark_dirty()
        except Exception:
            pass

    def _on_content_add(self) -> None:
        dlg = ContentRuleDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        rule = dlg.result_rule()
        if rule is None:
            show_warning(self, "Content rule", "Label and pattern are required.")
            return
        existing = {str(c.get("id")) for c in (self._current_ruleset().get("content_rules") or []) if isinstance(c, dict)}
        base, n = rule["id"], 2
        while rule["id"] in existing:
            rule["id"] = f"{base}-{n}"
            n += 1
        self._current_ruleset().setdefault("content_rules", []).append(rule)
        self._sel_kind, self._sel_key = "content", rule["id"]
        self._mark_dirty()
        self._refresh_content_list()
        self._show_template_for_selection()

    def _on_content_edit(self) -> None:
        cr = self._selected_content_rule()
        if cr is None:
            show_info(self, "Content rule", "Select a text rule first.")
            return
        dlg = ContentRuleDialog(self, cr)
        if dlg.exec() != QDialog.Accepted:
            return
        updated = dlg.result_rule(rule_id=str(cr.get("id") or ""))
        if updated is None:
            show_warning(self, "Content rule", "Label and pattern are required.")
            return
        cr.update(updated)
        self._mark_dirty()
        self._refresh_content_list()
        self._show_template_for_selection()

    def _on_content_delete(self) -> None:
        cr = self._selected_content_rule()
        if cr is None:
            return
        try:
            self._current_ruleset()["content_rules"] = [
                c for c in (self._current_ruleset().get("content_rules") or []) if c is not cr
            ]
        except Exception:
            pass
        self._refresh_content_list()
        self._mark_dirty()

    def _on_new(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(self, "New ruleset", "Ruleset key (e.g. mylab):")
        if not ok or not (name or "").strip():
            return
        key = name.strip()
        if key in (self._rulesets or {}):
            show_warning(self, "Ruleset", f"Ruleset '{key}' already exists.")
            return
        try:
            src = copy.deepcopy(self._current_ruleset())
            src["label"] = key
            src["dataverses"] = ["*"]
            self._rulesets[key] = src
            self._current = key
            self._refresh_all()
            self._mark_dirty()
        except Exception as exc:
            show_critical(self, "Ruleset", f"Could not create ruleset:\n{exc}")

    def _on_duplicate(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(self, "Duplicate ruleset", "New key:", text=f"{self._current}-copy")
        if not ok or not (name or "").strip():
            return
        key = name.strip()
        if key in (self._rulesets or {}):
            show_warning(self, "Ruleset", f"Ruleset '{key}' already exists.")
            return
        self._rulesets[key] = copy.deepcopy(self._current_ruleset())
        self._rulesets[key]["label"] = key
        self._current = key
        self._refresh_all()
        self._mark_dirty()

    def _on_delete(self) -> None:
        if self._current in ("mcmaster-default", "minimal"):
            show_warning(self, "Ruleset", "The built-in rulesets cannot be deleted (duplicate one to customize).")
            return
        if len(self._rulesets or {}) <= 1:
            show_warning(self, "Ruleset", "Cannot delete the last ruleset.")
            return
        from ui.dialogs import confirm
        deleted = self._current
        n_rules = len(((self._rulesets.get(self._current) or {}).get("field_rules")) or [])
        if not confirm(
            self,
            "Delete ruleset",
            f"Delete '{deleted}' and its {n_rules} field rule(s)? "
            "This cannot be undone.",
            confirm_label="Delete",
        ):
            return
        try:
            del self._rulesets[self._current]
            self._current = "mcmaster-default" if "mcmaster-default" in self._rulesets else sorted(self._rulesets.keys())[0]
            self._refresh_all()
            self._status.setText(f"Deleted '{deleted}'.")
            self._mark_dirty()
        except Exception as exc:
            show_critical(self, "Ruleset", f"Could not delete ruleset:\n{exc}")

    def _on_revert(self) -> None:
        from ui.dialogs import confirm
        if not confirm(
            self,
            "Revert changes",
            "Discard every unsaved edit and reload the last saved rules? "
            "This cannot be undone.",
            confirm_label="Revert",
        ):
            return
        try:
            self._rulesets = copy.deepcopy(self._rr.load_rulesets())
            self._current = self._pick_initial_key()
            self._refresh_all()
            self._status.setText("Reverted to saved rules.")
            self._clear_dirty()
        except Exception:
            pass

    def _on_save(self) -> None:
        try:
            path = self._rr.save_rulesets(self._rulesets)
        except Exception as exc:
            show_critical(self, "Review configuration", f"Could not save:\n{exc}")
            return
        try:
            import metadata_check as _mc

            _mc.refresh_profiles_from_rulesets()
        except Exception:
            pass
        self._status.setText(f"Saved to {path}")
        self._clear_dirty()
        show_info(self, "Review configuration", f"Saved to {Path(path).resolve()}")
        try:
            self.saved.emit()
        except Exception:
            pass

    def _on_load_fields(self) -> None:
        if self._worker is not None:
            try:
                if self._worker.isRunning():
                    self._status.setText("Already loading fields — please wait…")
                    return
            except Exception:
                pass
        if not (self._config.dataverse.api_token or "").strip():
            # Still show the disk cache / built-ins; live fetch needs a token
            # only on protected instances (metadatablocks is usually public,
            # but the worker sends the token when present).
            pass
        self._status.setText("Loading metadata fields from Dataverse…")
        self._fields_btn.setEnabled(False)
        try:
            from ui.workers import MetadataBlocksWorker

            ws = getattr(getattr(self._config, "app", None), "workspace", Path.home())
            self._worker = MetadataBlocksWorker(
                self._config.dataverse.base_url, self._config.dataverse.api_token, Path(ws), self
            )
            self._worker.finished.connect(self._on_fields_finished)
            self._worker.error.connect(self._on_fields_error)
            self._worker.finished.connect(self._worker.deleteLater)
            self._worker.error.connect(self._worker.deleteLater)
            self._worker.start()
        except Exception as exc:
            self._fields_btn.setEnabled(True)
            show_critical(self, "Metadata fields", f"Could not start field load:\n{exc}")

    def _on_fields_finished(self, fields: list) -> None:
        self._fields_btn.setEnabled(True)
        if isinstance(fields, list) and fields:
            self._schema = [dict(f) for f in fields if isinstance(f, dict) and f.get("field")]
            self._refresh_field_table()
            self._status.setText(f"Loaded {len(self._schema)} field(s) from Dataverse.")
        else:
            self._status.setText("Dataverse returned no metadata fields — using the built-in catalog.")

    def _on_fields_error(self, msg: str) -> None:
        self._fields_btn.setEnabled(True)
        self._status.setText("Could not load fields — using the built-in catalog.")
        show_warning(self, "Metadata fields", f"Could not load field catalog:\n{msg[:800]}")

    # -- host integration ----------------------------------------------------

    def refresh_for_dataverse(self) -> None:
        """Reselect the ruleset matching the active Dataverse (on show)."""
        try:
            want = self._pick_initial_key()
            if want != self._current and want in (self._rulesets or {}):
                self._current = want
                self._refresh_all()
        except Exception:
            pass
