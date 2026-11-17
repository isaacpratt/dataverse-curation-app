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
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidgetItem,
    QSplitter,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from curation.config import Config
from ui.dialogs import show_critical, show_info, show_warning
from ui.i18n import t
from ui.table_layout import TableLayout
from ui.theme import BORDER_SUBTLE, page_background_qss, selectable_labels
from ui.widgets import (
    AppTreeWidget,
    PaneFooter,
    add_info_tip,
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
    transparent_surface_qss,
)

if TYPE_CHECKING:
    from ui.workers import MetadataBlocksWorker

_LEVELS = ["required", "optional", "unchecked"]


class ContentRuleDialog(QDialog):
    """Add/edit one text-search rule (filenames / metadata / file-content)."""

    def __init__(self, parent=None, rule: dict[str, Any] | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("review.rule_dialog.title"))
        self.resize(520, 560)
        rule = rule or {}
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self._label = make_line_edit(t("review.rule_dialog.label_placeholder"))
        self._label.setText(str(rule.get("label") or ""))
        form.addRow(t("review.rule_dialog.label"), self._label)
        self._level = make_combo(
            [
                (t("review.rule_dialog.required"), "required"),
                (t("review.rule_dialog.optional"), "optional"),
            ],
            min_width=160,
        )
        lvl = str(rule.get("level") or "required")
        self._level.setCurrentIndex(0 if lvl != "optional" else 1)
        form.addRow(t("review.rule_dialog.level"), self._level)
        raw_scope = rule.get("scope")
        scope: list[Any] = raw_scope if isinstance(raw_scope, list) else ["filenames"]
        self._cb_files = make_checkbox(t("review.rule_dialog.scope_files"))
        self._cb_meta = make_checkbox(t("review.rule_dialog.scope_metadata"))
        self._cb_content = make_checkbox(t("review.rule_dialog.scope_content"))
        self._cb_files.setChecked("filenames" in scope)
        self._cb_meta.setChecked("metadata" in scope)
        self._cb_content.setChecked("file-content" in scope)
        scope_box = QVBoxLayout()
        scope_box.addWidget(self._cb_files)
        scope_box.addWidget(self._cb_meta)
        scope_box.addWidget(self._cb_content)
        scope_wrap = QWidget()
        scope_wrap.setLayout(scope_box)
        form.addRow(t("review.rule_dialog.scope"), scope_wrap)
        self._match = make_combo(
            [
                (t("review.rule_dialog.match_glob"), "filename-glob"),
                (t("review.rule_dialog.match_substring"), "substring"),
                (t("review.rule_dialog.match_regex"), "regex"),
            ],
            min_width=200,
        )
        m = str(rule.get("match") or "filename-glob")
        idx = {"filename-glob": 0, "substring": 1, "regex": 2}.get(m, 0)
        self._match.setCurrentIndex(idx)
        form.addRow(t("review.rule_dialog.match"), self._match)
        self._pattern = make_line_edit(t("review.rule_dialog.pattern_placeholder"))
        self._pattern.setText(str(rule.get("pattern") or ""))
        form.addRow(t("review.rule_dialog.pattern"), self._pattern)
        self._case = make_checkbox(
            t("review.rule_dialog.case_sensitive"),
            checked=bool(rule.get("case_sensitive")),
        )
        form.addRow("", self._case)
        lay.addLayout(form)
        lay.addWidget(QLabel(t("review.rule_dialog.response_label")))
        self._template = make_multiline_input(fixed=False, min_height=120)
        self._template.setPlainText(str(rule.get("response_template") or ""))
        lay.addWidget(self._template, 1)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
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
        is_required = (self._level.currentData() or "required") == "required"
        return {
            "id": rule_id or base,
            "label": label,
            "level": self._level.currentData() or "required",
            "requirement": t(
                "review.rule_dialog.requirement",
                level=t(
                    "review.rule_dialog.required"
                    if is_required
                    else "review.rule_dialog.recommended"
                ),
                label=label,
            ),
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
        self._worker: MetadataBlocksWorker | None = None
        try:
            from curation import review_rules as _rr

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

        # Shared page-heading contract (HeadlineLG theme token) - same
        # title look as Settings, Log and About.
        title, _subtitle = make_page_heading(t("review.title"))
        outer.addWidget(title)

        outer.addWidget(self._build_topbar())

        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self._build_rules_card())
        split.addWidget(self._build_templates_card())
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        # A 16px gap between the Checks card and the Response text card,
        # matching the page's own spacing (the default 1px handle made the
        # two cards look welded together).
        split.setHandleWidth(16)
        # theme-allow: splitter handle styling is unique to this view
        split.setStyleSheet(
            "QSplitter::handle { background: transparent; } "
            "QSplitter::handle:horizontal { width: 16px; }"
        )
        outer.addWidget(split, 1)

        # Shared Save/Revert footer (same component as Settings): one
        # vocabulary for pages that persist configuration.
        self._footer = PaneFooter(
            self,
            save_tip=t("review.footer.save_tip"),
            revert_tip=t("review.footer.revert_tip"),
        )
        self._footer.saveRequested.connect(self._on_save)
        self._footer.revertRequested.connect(self._on_revert)
        outer.addWidget(self._footer)
        # Compatibility aliases used by the status/dirty helpers.
        self._status = self._footer.status
        self._dirty_chip = self._footer.dirty_chip
        self._save_btn = self._footer.save_btn
        self._footer.set_dirty(False)

        selectable_labels(self)
        self._refresh_all()

    # -- setup ------------------------------------------------------------

    def _pick_initial_key(self) -> str:
        try:
            base = (self._config.dataverse.base_url or "").rstrip("/").lower()
            for key, rs in (self._rulesets or {}).items():
                dvs = {
                    (d or "").rstrip("/").lower()
                    for d in (rs.get("dataverses") or [])
                    if isinstance(d, str)
                }
                if base and base in dvs:
                    return key
        except Exception:
            pass
        if getattr(self, "_current", "") in (self._rulesets or {}):
            return str(self._current)
        if "mcmaster-default" in (self._rulesets or {}):
            return "mcmaster-default"
        try:
            return sorted((self._rulesets or {}).keys())[0]
        except Exception:
            return "mcmaster-default"

    def _load_cached_schema(self) -> list[dict[str, str]] | None:
        try:
            from curation.client import read_metadata_fields_cache

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
        fallback = {
            "label": self._current,
            "dataverses": ["*"],
            "field_rules": [],
            "content_rules": [],
            "filecheck_templates": {},
            "response_header": "",
            "response_footer": "",
        }
        self._rulesets[self._current] = fallback
        return fallback

    # -- builders ----------------------------------------------------------

    def _build_topbar(self) -> QWidget:
        card, body, _t, _h = make_card(t("review.card_ruleset"))
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel(t("review.ruleset_label")))
        self._ruleset_combo = make_combo(min_width=260)
        self._ruleset_combo.currentIndexChanged.connect(self._on_ruleset_changed)
        row.addWidget(self._ruleset_combo, 1)
        for text, slot in [
            (t("review.new"), self._on_new),
            (t("review.duplicate"), self._on_duplicate),
            (t("review.delete"), self._on_delete),
        ]:
            b = make_action_button(text, kind="secondary", size="sm")
            b.clicked.connect(slot)
            row.addWidget(b)
        body.addLayout(row)
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(QLabel(t("review.dataverses_label")))
        self._dataverses_edit = make_line_edit(t("review.dataverses_placeholder"))
        self._dataverses_edit.setToolTip(t("review.dataverses_tip"))
        self._dataverses_edit.editingFinished.connect(self._on_dataverses_edited)
        row2.addWidget(self._dataverses_edit, 1)
        self._fields_btn = make_action_button(t("review.load_fields"), kind="secondary", size="sm")
        self._fields_btn.clicked.connect(self._on_load_fields)
        row2.addWidget(self._fields_btn)
        body.addLayout(row2)
        return card

    def _build_rules_card(self) -> QWidget:
        card, body, _t, header_lay = make_card(t("review.card_checks"))
        # The checks help lives in the header's (i) tooltip, the same
        # pattern the dataset page uses — not a permanent paragraph that
        # pushed the tree down.
        add_info_tip(header_lay, t("review.checks_hint"), name=t("review.card_checks"))
        # The title bar keeps title + (i) only; the filters and actions are
        # tools, so they sit on their own row under it (file-manifest pattern).
        checks_tools = QWidget()
        checks_tools.setObjectName("ChecksTools")
        checks_tools.setStyleSheet(transparent_surface_qss("ChecksTools"))
        tools_lay = QHBoxLayout(checks_tools)
        tools_lay.setContentsMargins(16, 8, 16, 8)
        tools_lay.setSpacing(8)
        self._field_filter = make_search_field(
            t("review.filter_placeholder"), height=36, min_width=160
        )
        # Debounced like the dashboard search: rebuild the tree 200 ms after
        # the last keystroke so typing never loses focus mid-word.
        from PySide6.QtCore import QTimer as _QTimer

        self._filter_timer = _QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(200)
        self._filter_timer.timeout.connect(self._refresh_field_table)
        self._field_filter.textChanged.connect(lambda _t: self._filter_timer.start())
        tools_lay.addWidget(self._field_filter, 1)
        self._level_filter = make_combo(
            [
                (t("review.level_all"), "all"),
                (t("review.level_required"), "required"),
                (t("review.level_optional"), "optional"),
                (t("review.level_unchecked"), "unchecked"),
            ],
            height=36,
            min_width=130,
            tip=t("review.level_filter_tip"),
        )
        self._level_filter.currentIndexChanged.connect(lambda _i: self._refresh_field_table())
        tools_lay.addWidget(self._level_filter)
        self._blocks_btn = make_action_button(t("review.collapse_all"), kind="secondary", size="md")
        self._blocks_btn.setToolTip(t("review.blocks_tip"))
        self._blocks_btn.clicked.connect(self._on_toggle_blocks)
        tools_lay.addWidget(self._blocks_btn)
        self._fields_reset_btn = make_reset_columns_button(
            "",
            tip=t("review.reset_tip"),
            accessible_name=t("review.reset_fields_a11y"),
            fallback_text=t("review.reset"),
        )
        self._fields_reset_btn.clicked.connect(self._on_reset_field_view)
        tools_lay.addWidget(self._fields_reset_btn)
        # Sibling of the body, not inside it: the tree is rebuilt on filter
        # changes and the tools must survive that.
        card.layout().insertWidget(1, checks_tools)
        # Body margins go to zero so the tree bleeds edge-to-edge like
        # every other flush table in the app; the text-rules section
        # below carries its own inset.
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        # Block-grouped tree (replaces the flat table): block parents with
        # native expand/collapse, one child row per field rule with its
        # level combo. Sorting stays OFF on purpose — children are cell
        # *widgets*, which Qt does not move when rows sort.
        self._field_tree = AppTreeWidget(row_height=40, flush=True)
        self._field_tree.setColumnCount(2)
        self._field_tree.setHeaderLabels([t("review.column_field"), t("review.column_check")])
        self._field_tree.setRootIsDecorated(True)
        self._field_tree.setExpandsOnDoubleClick(True)
        self._field_tree.setAnimated(True)
        self._field_tree.setIndentation(18)
        self._field_tree.setMinimumHeight(160)
        # The standard tree chrome comes with the widget (flush: the tree
        # sits edge-to-edge inside the card, header meeting the top bar).
        _fld_header = self._field_tree.header()
        _fld_header.setStretchLastSection(False)
        _fld_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        _fld_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
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
        # The Collapse/Expand button follows manual expand/collapse too:
        # without these, collapsing one block left the button reading
        # "Collapse all" and clicking it expanded everything.
        self._field_tree.itemExpanded.connect(lambda _i: self._update_blocks_btn())
        self._field_tree.itemCollapsed.connect(lambda _i: self._update_blocks_btn())
        body.addWidget(self._field_tree, 1)

        # Text rules: their own section under a divider, inset like a card
        # body, so an expanded metadata block can never run behind them.
        divider = QFrame()
        divider.setObjectName("ReviewSectionDivider")
        divider.setFixedHeight(1)
        # theme-allow: simple divider colour is a one-off
        divider.setStyleSheet(f"background: {BORDER_SUBTLE};")
        body.addWidget(divider)

        rules_section = QWidget()
        rules_lay = QVBoxLayout(rules_section)
        rules_lay.setContentsMargins(16, 12, 16, 12)
        rules_lay.setSpacing(8)
        rules_head = QLabel(t("review.text_rules_label"))
        rules_head.setObjectName("HeadlineMD")
        rules_lay.addWidget(rules_head)
        self._content_list = make_list()
        self._content_list.setMinimumHeight(96)
        self._content_list.itemSelectionChanged.connect(self._on_content_selected)
        rules_lay.addWidget(self._content_list, 1)
        row = QHBoxLayout()
        for text, slot in [
            (t("review.add_rule"), self._on_content_add),
            (t("review.edit_rule"), self._on_content_edit),
            (t("review.delete"), self._on_content_delete),
        ]:
            b = make_action_button(text, kind="secondary", size="sm")
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        rules_lay.addLayout(row)
        body.addWidget(rules_section, 1)
        return card

    def _build_templates_card(self) -> QWidget:
        card, body, _t, _h = make_card(t("review.card_response"))
        self._sel_label = QLabel(t("review.select_template"))
        self._sel_label.setWordWrap(True)
        self._sel_label.setObjectName("LabelStrongSM")
        body.addWidget(self._sel_label)
        self._template_edit = make_multiline_input(
            t("review.template_placeholder"),
            fixed=False,
            min_height=130,
        )
        self._template_edit.textChanged.connect(self._on_template_edited)
        body.addWidget(self._template_edit)
        body.addWidget(QLabel(t("review.draft_header")))
        self._header_edit = make_multiline_input(fixed=False, min_height=70)
        self._header_edit.textChanged.connect(self._on_header_footer_edited)
        body.addWidget(self._header_edit)
        body.addWidget(QLabel(t("review.draft_footer")))
        self._footer_edit = make_multiline_input(fixed=False, min_height=70)
        self._footer_edit.textChanged.connect(self._on_header_footer_edited)
        body.addWidget(self._footer_edit, 1)
        note = QLabel(t("review.filecheck_note"))
        note.setWordWrap(True)
        note.setObjectName("CaptionSM")
        body.addWidget(note)
        return card

    # -- data -> ui --------------------------------------------------------

    def _schema_fields(self) -> list[dict[str, str]]:
        # The live metadatablocks catalog (or a cached copy of its last
        # fetch) wins for the fields it knows — but it may predate our
        # dotted composite-child entries, so the built-in catalog fills the
        # gaps (composite children only). This keeps the review page useful
        # offline and upgrades stale on-disk caches silently.
        if self._schema:
            live = [dict(f) for f in self._schema if isinstance(f, dict) and f.get("field")]
            try:
                from curation.review_rules import FIELD_CATALOG
            except Exception:
                FIELD_CATALOG = []  # noqa: N806 - fallback for the upstream constant import above
            seen_live = {
                (str(f.get("block") or "citation"), str(f.get("field") or "")) for f in live
            }
            fallback = [dict(f) for f in FIELD_CATALOG if isinstance(f, dict) and f.get("field")]
            for f in fallback:
                key = (str(f.get("block") or "citation"), str(f.get("field") or ""))
                if key not in seen_live:
                    seen_live.add(key)
                    live.append(f)
            base = live
        else:
            try:
                from curation.review_rules import FIELD_CATALOG

                base = [dict(f) for f in FIELD_CATALOG]
            except Exception:
                base = []
        # Union with fields referenced by any ruleset so custom fields persist.
        # The key space is the normalized one the loop below builds, so a
        # catalog entry and a rule that name the same field agree (dv-hcg.28).
        seen: set[tuple[str, str]] = {
            (str(f.get("block") or "citation"), str(f.get("field") or "")) for f in base
        }
        for rs in (self._rulesets or {}).values():
            for fr in rs.get("field_rules") or []:
                if not isinstance(fr, dict):
                    continue
                key = (str(fr.get("block") or "citation"), str(fr.get("field") or ""))
                if key[1] and key not in seen:
                    seen.add(key)
                    base.append(
                        {"block": key[0], "field": key[1], "label": str(fr.get("label") or key[1])}
                    )
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
        for fr in self._current_ruleset().get("field_rules") or []:
            if not isinstance(fr, dict) or not fr.get("field"):
                continue
            block = str(fr.get("block") or "citation")
            field = str(fr.get("field") or "")
            handler = str(fr.get("handler") or "nonempty")
            covered.add((block, field, handler))
            parent = field.split(".", 1)[0] if "." in field else ""
            entries.append(
                {
                    "kind": "rule",
                    "label": str(fr.get("label") or field),
                    "block": block,
                    "field": field,
                    "handler": handler,
                    "block_label": schema_labels.get((block, field), ""),
                    "level": fr.get("level")
                    if fr.get("level") in ("required", "optional")
                    else "required",
                    "req": str(fr.get("requirement") or ""),
                    "parent": parent if parent and parent != field else "",
                }
            )
        for f in self._schema_fields():
            block, field = str(f.get("block") or ""), str(f.get("field") or "")
            if not field or any((block, field) == (b, fl) for b, fl, _h in covered):
                continue
            entries.append(
                {
                    "kind": "new",
                    "label": str(f.get("label") or field),
                    "block": block,
                    "field": field,
                    "handler": "nonempty",
                    "block_label": str(f.get("block_label") or ""),
                    "level": "unchecked",
                    "req": "",
                    "parent": str(
                        f.get("parent") or (field.split(".", 1)[0] if "." in field else "")
                    ),
                }
            )
        return entries

    @staticmethod
    def _block_display_name(block: str, label: str = "") -> str:
        """Proper block name: catalog display name, else capitalized id."""
        try:
            b = str(block or "").strip()
            # License / terms rules live under a synthetic "license" block so
            # they group under one heading in the field tree.
            if b == "license" and not str(label or "").strip():
                return t("review.block_license")
            if str(label or "").strip():
                return str(label).strip()
            return (b[:1].upper() + b[1:]) if b else t("review.block_other")
        except Exception:
            return str(block or t("review.block_other"))

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

    def _refresh_field_table(self) -> None:  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
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
            hay = f"{e.get('label', '')} {e.get('block', '')} {e.get('field', '')} {e.get('handler', '')}".lower()
            if filt and filt not in hay:
                continue
            block = str(e.get("block") or "citation")
            groups.setdefault(block, []).append(e)
            if block not in group_labels:
                group_labels[block] = self._block_display_name(
                    block, str(e.get("block_label") or "")
                )
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
            def _group_sort_key(b: str) -> tuple[int, str]:
                # A named function, not a lambda: a lambda parameter is
                # untyped, so the key came back as Any and the lookup
                # lost its type (dv-hcg.28).
                return (
                    0 if str(b or "").lower() == "citation" else 1,
                    group_labels.get(b, b).lower(),
                )

            ordered = sorted(groups, key=_group_sort_key)
            for block in ordered:
                label = group_labels.get(block, block)
                rows = sorted(
                    groups[block], key=lambda e: str(e.get("label") or e.get("field") or "")
                )
                top = QTreeWidgetItem([t("review.block_count", label=label, count=len(rows))])
                try:
                    fnt = top.font(0)
                    fnt.setBold(True)
                    top.setFont(0, fnt)
                except Exception:
                    pass
                top.setData(0, Qt.ItemDataRole.UserRole, {"kind": "block", "block": block})
                top.setToolTip(
                    0,
                    t(
                        "review.block_tip",
                        label=label,
                        count=len(rows),
                    ),
                )
                top.setExpanded(True)
                # Top item joins the tree first: setItemWidget needs the
                # child row present before the combo is attached.
                tree.addTopLevelItem(top)

                # Dotted field paths ("author.authorIdentifier") nest under a
                # synthetic group row named for their parent field (e.g.
                # "Author") — Borealis shows the same shape: the composite is
                # the heading, its children fill it. Composite rule rows
                # (author_affiliation, author_count) join the group too.
                def _grp(e):
                    return str(e.get("field") or "").split(".", 1)[0]

                def _add_field_row(e, parent_item=None, block_item=None):
                    parent_item = parent_item if parent_item is not None else block_item
                    block, field = e["block"], e["field"]
                    child = QTreeWidgetItem([str(e.get("label") or field)])
                    child.setToolTip(
                        0,
                        t(
                            "review.messages.field_rule_tip",
                            block=block,
                            field=field,
                            handler=e["handler"],
                        )
                        + (f"\n{e['req']}" if e["req"] else ""),
                    )
                    child.setData(0, Qt.ItemDataRole.UserRole, {"kind": "field"})
                    combo = make_combo(
                        [
                            (t("review.level_required"), "required"),
                            (t("review.level_optional"), "optional"),
                            (t("review.level_unchecked"), "unchecked"),
                        ],
                        height=32,
                        min_width=110,
                    )
                    combo.setCurrentIndex(
                        {"required": 0, "optional": 1, "unchecked": 2}.get(e["level"], 2)
                    )
                    combo.setProperty("kind", e["kind"])
                    combo.setProperty("block", block)
                    combo.setProperty("field", field)
                    combo.setProperty("handler", e["handler"])
                    combo.currentIndexChanged.connect(self._on_field_level_changed)
                    target = parent_item if parent_item is not None else block_item
                    target.addChild(child)
                    tree.setItemWidget(child, 1, combo)
                    return child

                groups_by_prefix: dict[str, list] = {}
                for e in rows:
                    groups_by_prefix.setdefault(_grp(e), []).append(e)
                for prefix, members in sorted(groups_by_prefix.items(), key=lambda kv: kv[0]):
                    children = [e for e in members if "." in str(e.get("field") or "")]
                    leaders = [e for e in members if "." not in str(e.get("field") or "")]
                    if not children:
                        for e in leaders:
                            _add_field_row(e, block_item=top)
                        n_fields += len(leaders)
                        continue
                    # Group heading: the parent's catalog label if we know
                    # it, else title-cased prefix.
                    parent_label = next(
                        (c.get("parent_label") for c in children if c.get("parent_label")),
                        "",
                    ) or (prefix[:1].upper() + prefix[1:])
                    group = QTreeWidgetItem([parent_label])
                    group.setData(0, Qt.ItemDataRole.UserRole, {"kind": "group"})
                    try:
                        font = group.font(0)
                        font.setBold(True)
                        group.setFont(0, font)
                    except Exception:
                        pass
                    group.setToolTip(
                        0,
                        t(
                            "review.messages.group_tip",
                            label=parent_label,
                            count=len(members),
                        ),
                    )
                    top.addChild(group)
                    for e in leaders:
                        _add_field_row(e, group)
                        n_fields += 1
                    for e in sorted(
                        children, key=lambda x: str(x.get("label") or x.get("field") or "")
                    ):
                        _add_field_row(e, group)
                        n_fields += 1
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
                t(
                    "review.messages.fields_shown",
                    fields=n_fields,
                    blocks=len(groups),
                )
                + (
                    t("review.messages.live_catalog")
                    if self._schema
                    else t("review.messages.builtin_catalog")
                )
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
                if top is None:
                    continue
                for ci in range(top.childCount()):
                    child = top.child(ci)
                    if child is not None and tree.itemWidget(child, 1) is combo:
                        return child
        except Exception:
            pass
        return None

    def _blocks_any_collapsed(self) -> bool:
        try:
            for bi in range(self._field_tree.topLevelItemCount()):
                top = self._field_tree.topLevelItem(bi)
                if top is not None and not top.isExpanded():
                    return True
            return False
        except Exception:
            return False

    def _update_blocks_btn(self) -> None:
        try:
            self._blocks_btn.setText(
                t("review.collapse_all")
                if not self._blocks_any_collapsed()
                else t("review.expand_all")
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
                [
                    (t("review.level_required"), "required"),
                    (t("review.level_optional"), "optional"),
                    (t("review.level_unchecked"), "unchecked"),
                ],
                height=32,
                min_width=110,
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
            for cr in self._current_ruleset().get("content_rules") or []:
                if not isinstance(cr, dict):
                    continue
                scope = ", ".join(cr.get("scope") or [])
                item = QListWidgetItem(
                    t(
                        "review.content_item",
                        label=cr.get("label", "rule"),
                        level=cr.get("level", "required"),
                        scope=scope,
                    )
                )
                item.setData(Qt.ItemDataRole.UserRole, str(cr.get("id") or ""))
                item.setToolTip(
                    t(
                        "review.content_item_tip",
                        pattern=cr.get("pattern", ""),
                        match=cr.get("match", ""),
                        template=cr.get("response_template", "")[:200],
                    )
                )
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
        for fr in self._current_ruleset().get("field_rules") or []:
            if not isinstance(fr, dict):
                continue
            if (
                str(fr.get("block") or "citation") == block
                and str(fr.get("field") or "") == field
                and str(fr.get("handler") or "nonempty") == handler
            ):
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
        self._footer.set_dirty(True)

    def _clear_dirty(self) -> None:
        self._dirty = False
        self._footer.set_dirty(False)

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
                str(combo.property("block") or ""),
                str(combo.property("field") or ""),
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
                    label = next(
                        (
                            f.get("label") or field
                            for f in self._schema_fields()
                            if f.get("block") == block and f.get("field") == field
                        ),
                        field,
                    )
                    found = {
                        "block": block,
                        "field": field,
                        "label": label,
                        "requirement": t(
                            "review.rule_dialog.requirement",
                            level=(
                                t("review.rule_dialog.required")
                                if level == "required"
                                else t("review.rule_dialog.recommended")
                            ),
                            label=label,
                        ),
                        "handler": "nonempty",
                        "response_template": t(
                            "review.messages.missing_field_template",
                            label=label,
                        ),
                    }
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
                    combo.setProperty(
                        "kind", "rule" if found is not None and level != "unchecked" else "new"
                    )
                    if found is not None and level != "unchecked":
                        tip_req = str(found.get("requirement") or "")
                        child.setToolTip(
                            0,
                            t(
                                "review.messages.field_rule_tip",
                                block=block,
                                field=field,
                                handler=handler,
                            )
                            + (f"\n{tip_req}" if tip_req else ""),
                        )
            except Exception:
                pass
            self._show_template_for_selection()
        except Exception:
            pass

    def _selected_content_rule(self) -> dict[str, Any] | None:
        try:
            item = self._content_list.currentItem()
            rid = item.data(Qt.ItemDataRole.UserRole) if item else ""
            for cr in self._current_ruleset().get("content_rules") or []:
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
                cr = next(
                    (
                        c
                        for c in (self._current_ruleset().get("content_rules") or [])
                        if isinstance(c, dict) and str(c.get("id")) == self._sel_key
                    ),
                    None,
                )
                if cr is None:
                    return
                self._sel_label.setText(
                    t(
                        "review.selection.content_rule",
                        label=cr.get("label", ""),
                    )
                )
                self._template_edit.setPlainText(str(cr.get("response_template") or ""))
            else:
                parts = self._sel_key.split("\x1f")
                fr = (
                    self._find_field_rule(parts[0], parts[1], parts[2]) if len(parts) == 3 else None
                )
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
                    self._sel_label.setText(t("review.select_template"))
                    self._template_edit.setPlainText("")
                    return
                self._sel_label.setText(
                    t(
                        "review.selection.field_rule",
                        label=fr.get("label", fr.get("field")),
                    )
                )
                self._template_edit.setPlainText(str(fr.get("response_template") or ""))
        finally:
            self._template_edit.blockSignals(False)

    def _on_template_edited(self) -> None:
        if self._loading:
            return
        try:
            text = self._template_edit.toPlainText()
            if self._sel_kind == "content":
                for cr in self._current_ruleset().get("content_rules") or []:
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
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        rule = dlg.result_rule()
        if rule is None:
            show_warning(
                self,
                t("review.rule_dialog.title"),
                t("review.messages.label_pattern_required"),
            )
            return
        existing = {
            str(c.get("id"))
            for c in (self._current_ruleset().get("content_rules") or [])
            if isinstance(c, dict)
        }
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
            show_info(
                self,
                t("review.rule_dialog.title"),
                t("review.messages.select_rule_first"),
            )
            return
        dlg = ContentRuleDialog(self, cr)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        updated = dlg.result_rule(rule_id=str(cr.get("id") or ""))
        if updated is None:
            show_warning(
                self,
                t("review.rule_dialog.title"),
                t("review.messages.label_pattern_required"),
            )
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

        name, ok = QInputDialog.getText(
            self,
            t("review.dialogs.new_ruleset_title"),
            t("review.dialogs.new_ruleset_label"),
        )
        if not ok or not (name or "").strip():
            return
        key = name.strip()
        if key in (self._rulesets or {}):
            show_warning(
                self,
                t("review.dialogs.ruleset_title"),
                t("review.messages.ruleset_exists", key=key),
            )
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
            show_critical(
                self,
                t("review.dialogs.ruleset_title"),
                t("review.messages.create_failed", exc=exc),
            )

    def _on_duplicate(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(
            self,
            t("review.dialogs.duplicate_ruleset_title"),
            t("review.dialogs.duplicate_ruleset_label"),
            text=f"{self._current}-copy",
        )
        if not ok or not (name or "").strip():
            return
        key = name.strip()
        if key in (self._rulesets or {}):
            show_warning(
                self,
                t("review.dialogs.ruleset_title"),
                t("review.messages.ruleset_exists", key=key),
            )
            return
        self._rulesets[key] = copy.deepcopy(self._current_ruleset())
        self._rulesets[key]["label"] = key
        self._current = key
        self._refresh_all()
        self._mark_dirty()

    def _on_delete(self) -> None:
        if self._current in ("mcmaster-default", "minimal"):
            show_warning(
                self,
                t("review.dialogs.ruleset_title"),
                t("review.messages.built_in_protected"),
            )
            return
        if len(self._rulesets or {}) <= 1:
            show_warning(
                self,
                t("review.dialogs.ruleset_title"),
                t("review.messages.last_ruleset"),
            )
            return
        from ui.dialogs import confirm

        deleted = self._current
        n_rules = len(((self._rulesets.get(self._current) or {}).get("field_rules")) or [])
        if not confirm(
            self,
            t("review.dialogs.delete_ruleset_title"),
            t("review.messages.delete_confirm", name=deleted, count=n_rules),
            confirm_label=t("review.delete"),
        ):
            return
        try:
            del self._rulesets[self._current]
            self._current = (
                "mcmaster-default"
                if "mcmaster-default" in self._rulesets
                else sorted(self._rulesets.keys())[0]
            )
            self._refresh_all()
            self._status.setText(t("review.messages.deleted", name=deleted))
            self._mark_dirty()
        except Exception as exc:
            show_critical(
                self,
                t("review.dialogs.ruleset_title"),
                t("review.messages.delete_failed", exc=exc),
            )

    def _on_revert(self) -> None:
        from ui.dialogs import confirm

        if not confirm(
            self,
            t("review.dialogs.revert_title"),
            t("review.messages.revert_confirm"),
            confirm_label=t("review.revert"),
        ):
            return
        try:
            self._rulesets = copy.deepcopy(self._rr.load_rulesets())
            self._current = self._pick_initial_key()
            self._refresh_all()
            self._status.setText(t("review.messages.reverted"))
            self._clear_dirty()
        except Exception:
            pass

    def _on_save(self) -> None:
        try:
            path = self._rr.save_rulesets(self._rulesets)
        except Exception as exc:
            show_critical(
                self,
                t("review.title"),
                t("review.messages.save_failed", exc=exc),
            )
            return
        try:
            from curation import metadata_check as _mc

            _mc.refresh_profiles_from_rulesets()
        except Exception:
            pass
        self._status.setText(t("review.messages.saved_to", path=path))
        self._clear_dirty()
        show_info(
            self,
            t("review.title"),
            t("review.messages.saved_to", path=Path(path).resolve()),
        )
        try:
            self.saved.emit()
        except Exception:
            pass

    def _on_load_fields(self) -> None:
        if self._worker is not None:
            try:
                if self._worker.isRunning():
                    self._status.setText(t("review.messages.already_loading"))
                    return
            except Exception:
                pass
        if not (self._config.dataverse.api_token or "").strip():
            # Still show the disk cache / built-ins; live fetch needs a token
            # only on protected instances (metadatablocks is usually public,
            # but the worker sends the token when present).
            pass
        self._status.setText(t("review.messages.loading_fields"))
        self._fields_btn.setEnabled(False)
        try:
            from ui.workers import MetadataBlocksWorker

            ws = getattr(getattr(self._config, "app", None), "workspace", Path.home())
            worker = MetadataBlocksWorker(
                self._config.dataverse.base_url, self._config.dataverse.api_token, Path(ws), self
            )
            worker.finished.connect(self._on_fields_finished)
            worker.error.connect(self._on_fields_error)
            worker.finished.connect(worker.deleteLater)
            worker.error.connect(worker.deleteLater)
            self._worker = worker
            worker.start()
        except Exception as exc:
            self._fields_btn.setEnabled(True)
            show_critical(
                self,
                t("review.dialogs.metadata_fields_title"),
                t("review.messages.load_start_failed", exc=exc),
            )

    def _on_fields_finished(self, fields: list) -> None:
        self._fields_btn.setEnabled(True)
        if isinstance(fields, list) and fields:
            self._schema = [dict(f) for f in fields if isinstance(f, dict) and f.get("field")]
            self._refresh_field_table()
            self._status.setText(t("review.messages.loaded_fields", count=len(self._schema)))
        else:
            self._status.setText(t("review.messages.no_fields"))

    def _on_fields_error(self, msg: str) -> None:
        self._fields_btn.setEnabled(True)
        self._status.setText(t("review.messages.load_failed"))
        show_warning(
            self,
            t("review.dialogs.metadata_fields_title"),
            t("review.messages.load_catalog_failed", message=msg[:800]),
        )

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
