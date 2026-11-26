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
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QMouseEvent
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
    QScrollArea,
    QSplitter,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from curation.config import Config

try:
    from curation.review_rules import FIELD_CATALOG
except Exception:  # the built-in catalog is best-effort at import time
    FIELD_CATALOG = []

from ui.dialogs import show_critical, show_info, show_warning
from ui.i18n import t
from ui.theme import ACTIVE_THEME, selectable_labels, transparent_surface_qss
from ui.widgets import (
    AppTreeWidget,
    PaneFooter,
    add_info_tip,
    fit_tree_height,
    make_action_button,
    make_card,
    make_cell_control,
    make_checkbox,
    make_combo,
    make_line_edit,
    make_list,
    make_multiline_input,
    make_number_field,
    make_page_heading,
    make_search_field,
    make_value_list,
    set_sheet,
)

_LEVELS = ["required", "optional", "unchecked"]

# The Level column's labels, one per stored value.
_LEVEL_LABEL_KEYS = {
    "required": "review.level_required",
    "optional": "review.level_optional",
    "unchecked": "review.level_unchecked",
}

# dv-5id: friendly names for the rule handlers that ship in the ruleset
# JSON. The Check picker only offers nonempty/looks_correct; any other
# handler a curator drops in via JSON is shown through this map.
_HANDLER_LABEL_KEYS = {
    "nonempty": "review.handler_nonempty",
    "looks_correct": "review.handler_looks_correct",
    "orcid": "review.handler_orcid",
    "author_affiliation": "review.handler_author_affiliation",
    "author_count": "review.handler_author_count",
    "license": "review.handler_license",
    "license_terms": "review.handler_license_terms",
    "terms_of_use": "review.handler_terms_of_use",
    "terms_of_access": "review.handler_terms_of_access",
    "access_conditions": "review.handler_access_conditions",
    "related_pub": "review.handler_related_pub",
    "related_pub_id": "review.handler_related_pub_id",
    "time_anyof": "review.handler_time_anyof",
    "geo": "review.handler_geo",
}

# The cell host's margins, matching make_cell_control's defaults in the kit
# (dv-7zv). The column widths are measured with the same numbers, so a
# dropdown always has its 8px either side inside its column.
_CELL_V_MARGIN = 4
_CELL_H_MARGIN = 8


class ContentRuleDialog(QDialog):
    """Add/edit one text-search rule (filenames / metadata / file-content)."""

    def __init__(self, parent: QWidget | None = None, rule: dict[str, Any] | None = None) -> None:
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
        scope_raw = rule.get("scope")
        scope = scope_raw if isinstance(scope_raw, list) else ["filenames"]
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

    # The param-form checkboxes are built in a loop with setattr; declared
    # here so the type checker can see them (runtime behaviour unchanged).
    _p_not_common_placeholders: Any
    _p_not_all_caps: Any
    _p_date: Any
    _p_date_order: Any
    _p_url: Any

    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._worker: Any = None
        try:
            import curation.review_rules as _rr

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
        self._selecting = False  # a programmatic setCurrentItem, not a user act
        # Unsaved-chip: any in-memory ruleset edit sets it, Save/Revert clear
        # it. Guards against losing edits by navigating away unnoticed.
        self._dirty = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(16)
        # Scoped to self: a bare `background` rule would act subtree-wide
        # and override app-level backgrounds below this view.
        self.setObjectName("ReviewConfigView")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        set_sheet(self, "page_background", ("ReviewConfigView",))

        # Shared page-heading contract (HeadlineLG theme token) - same
        # title look as Settings, Log and About.
        title, _subtitle = make_page_heading(t("review.title"))
        outer.addWidget(title)

        outer.addWidget(self._build_topbar())

        split = QSplitter(Qt.Orientation.Horizontal)

        # Two scroll areas: Checks (stretch 3) and Response (stretch 2).
        # Each holds a card that grows to its content, moving the scrollbar
        # to the pane's own right edge — the dataset page's two-column idiom.
        def make_pane(*card_builders: Callable[[], QWidget]) -> QScrollArea:
            """One scroll pane holding a vertical stack of cards (dv-gcn)."""
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            host = QWidget()
            host_lay = QVBoxLayout(host)
            host_lay.setContentsMargins(0, 0, 0, 0)
            host_lay.setSpacing(16)
            for builder in card_builders:
                host_lay.addWidget(builder())
            scroll.setWidget(host)
            return scroll

        left_pane = make_pane(self._build_field_rules_card, self._build_content_rules_card)
        right_pane = make_pane(self._build_templates_card)
        split.addWidget(left_pane)
        split.addWidget(right_pane)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        # A floor per pane: the stacked form controls (a chip field plus its
        # plus button) cannot get narrower than their own content (dv-5nd).
        split.setChildrenCollapsible(False)
        left_pane.setMinimumWidth(360)
        right_pane.setMinimumWidth(384)
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

    def _build_field_rules_card(self) -> QWidget:
        """Build the field table: one card, one tools row, no divider."""
        card, body, _t, header_lay = make_card(t("review.card_field_rules"))
        # The field-rules help lives in the header's (i) tooltip, the same
        # pattern the dataset page uses — not a permanent paragraph that
        # pushed the tree down.
        add_info_tip(
            header_lay,
            t("review.checks_hint"),
            name=t("review.card_field_rules"),
            group=t("review.card_field_rules"),
        )
        # The title bar keeps title + (i) only; the filters and actions are
        # tools, so they sit on their own row under it (file-manifest pattern).
        tools = QWidget()
        tools.setObjectName("FieldRulesTools")
        tools.setStyleSheet(transparent_surface_qss("FieldRulesTools", theme=ACTIVE_THEME))
        lay = QHBoxLayout(tools)
        lay.setContentsMargins(16, 8, 16, 8)
        lay.setSpacing(8)
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
        lay.addWidget(self._field_filter, 1)
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
        lay.addWidget(self._level_filter)
        self._blocks_btn = make_action_button(t("review.collapse_all"), kind="secondary", size="md")
        self._blocks_btn.setToolTip(t("review.blocks_tip"))
        self._blocks_btn.clicked.connect(self._on_toggle_blocks)
        lay.addWidget(self._blocks_btn)
        # Sibling of the body, not inside it: the tree is rebuilt on filter
        # changes and the tools must survive that.
        cast(QVBoxLayout, card.layout()).insertWidget(1, tools)
        # Body margins go to zero so the tree bleeds edge-to-edge like
        # every other flush table in the app; the text-rules section
        # below carries its own inset.
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        # Block-grouped tree (replaces the flat table): block parents with
        # native expand/collapse, one child row per field rule with its level
        # and check dropdowns. Sorting stays OFF on purpose - children are
        # cell *widgets*, which Qt does not move when rows sort.
        self._field_tree = AppTreeWidget(row_height=40, flush=True, hover_tint=False)
        self._field_tree.setColumnCount(3)
        # The three labels stay (a screen reader and any future re-show use
        # them) but the band is not painted: the two dropdown columns say
        # what they hold, and the band cost a row of vertical space (dv-7zv).
        self._field_tree.setHeaderLabels(
            [
                t("review.column_field"),
                t("review.column_level"),
                t("review.column_check"),
            ]
        )
        self._field_tree.setHeaderHidden(True)
        self._field_tree.setRootIsDecorated(True)
        self._field_tree.setExpandsOnDoubleClick(True)
        self._field_tree.setAnimated(True)
        self._field_tree.setIndentation(18)
        # No fixed floor; height is fit to content to move scroll to the pane.
        self._field_tree.setMinimumHeight(0)
        # Field takes the rest; the two dropdown columns are fixed at their
        # measured need, so the row always fits and the tree never needs a
        # horizontal scrollbar (at 1440 or at 960).
        _fld_header = self._field_tree.header()
        _fld_header.setStretchLastSection(False)
        _fld_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        _fld_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        _fld_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._field_tree.setColumnWidth(1, self._column_width(self._level_items(), 110))
        self._field_tree.setColumnWidth(2, self._column_width(self._handler_column_items(), 180))
        self._field_tree.itemPressed.connect(self._on_row_pressed)
        # Keyboard navigation is a deliberate act: arrow keys move the current
        # row and the Response pane follows. A mere pointer move never does.
        self._field_tree.currentItemChanged.connect(self._on_current_item_changed)
        # Cell widgets swallow presses before the tree sees them, so the
        # combos and their hosts have to route a press to the same helper.
        self._field_tree.viewport().installEventFilter(self)

        # The Collapse/Expand button follows manual expand/collapse too:
        # without these, collapsing one block left the button reading
        # "Collapse all" and clicking it expanded everything. The tree is
        # content-fitted, so a manual toggle must refit too.
        def _refit(_i: QTreeWidgetItem) -> None:
            self._update_blocks_btn()
            fit_tree_height(self._field_tree, row_height=40)

        self._field_tree.itemExpanded.connect(_refit)
        self._field_tree.itemCollapsed.connect(_refit)
        # The tree bleeds edge-to-edge in the card body; the content rules
        # live in their own sibling card (dv-gcn).
        body.addWidget(self._field_tree)
        return card

    def _build_content_rules_card(self) -> QWidget:
        """Build the text-search rules: their own card, title and summary."""
        card, body, _t, header_lay = make_card(t("review.card_content_rules"))
        add_info_tip(
            header_lay,
            t("review.content_rules_hint"),
            name=t("review.card_content_rules"),
            group=t("review.card_content_rules"),
        )
        body.setContentsMargins(16, 12, 16, 12)
        body.setSpacing(8)
        self._content_summary = QLabel()
        self._content_summary.setObjectName("CaptionSM")
        body.addWidget(self._content_summary)
        self._content_list = make_list()
        self._content_list.setMinimumHeight(96)
        self._content_list.itemSelectionChanged.connect(self._on_content_selected)
        body.addWidget(self._content_list, 1)
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
        body.addLayout(row)
        return card

    def _build_templates_card(self) -> QWidget:
        card, body, _t, _h = make_card(t("review.card_response"))
        self._sel_label = QLabel(t("review.select_template"))
        self._sel_label.setWordWrap(True)
        self._sel_label.setObjectName("LabelStrongSM")
        body.addWidget(self._sel_label)
        # Entry-check params (dv-5id, moved here by dv-7zv): the Check
        # dropdown itself now lives in the rules table's own column, so this
        # pane holds response text plus the params of a “looks plausibly
        # correct” rule. Shown only while that check is picked; every edit
        # writes straight back into the rule's params dict.
        self._params_panel = QWidget()
        params_lay = QVBoxLayout(self._params_panel)
        params_lay.setContentsMargins(0, 0, 0, 0)
        params_lay.setSpacing(8)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        params_title = QLabel(t("review.params_title"))
        params_title.setObjectName("LabelStrongSM")
        title_row.addWidget(params_title)
        # The fail-closed sentence stays a tooltip, not a painted paragraph.
        add_info_tip(
            title_row,
            t("review.params_title_tip"),
            name=t("review.params_title"),
            group=t("review.params_title"),
        )
        title_row.addStretch(1)
        params_lay.addLayout(title_row)

        def _param_row(label_key: str, help_key: str, control: QWidget) -> None:
            """Put a short label above a full-width control, both with one tip."""
            tip = t(help_key)
            label = self._params_label(t(label_key))
            label.setToolTip(tip)
            label.setWordWrap(False)
            control.setToolTip(tip)
            row = QWidget()
            row_lay = QVBoxLayout(row)
            row_lay.setContentsMargins(0, 0, 0, 0)
            row_lay.setSpacing(4)
            row_lay.addWidget(label)
            row_lay.addWidget(control)
            params_lay.addWidget(row)

        # The kit's number field replaces the raw QSpinBox: the native
        # stepper was clipped at the right edge of a 32px field, and a view
        # may not build a raw spin box at all (dv-6vv). Its API mirrors
        # QSpinBox's, so the loader and the edit slot are unchanged.
        self._p_min = make_number_field(0, minimum=0, maximum=10000)
        self._p_min.changed.connect(self._on_params_edited)
        _param_row("review.params_min_length", "review.params_min_length_help", self._p_min)

        self._p_regex = make_line_edit(height=32)
        self._p_regex.textChanged.connect(self._on_params_edited)
        _param_row("review.params_regex", "review.params_regex_help", self._p_regex)
        self._p_regex_full = make_checkbox(t("review.params_regex_full"))
        self._p_regex_full.setToolTip(t("review.params_regex_full_help"))
        self._p_regex_full.toggled.connect(self._on_params_edited)
        params_lay.addWidget(self._p_regex_full)

        # Two phrase lists: one chip per entry, added one at a time.
        self._p_blocklist = make_value_list([], add_tip=t("review.params_blocklist_help"))
        self._p_blocklist.changed.connect(self._on_params_edited)
        _param_row(
            "review.params_blocklist",
            "review.params_blocklist_help",
            self._p_blocklist,
        )
        self._p_vocab = make_value_list([], add_tip=t("review.params_vocabulary_help"))
        self._p_vocab.changed.connect(self._on_params_edited)
        _param_row(
            "review.params_vocabulary",
            "review.params_vocabulary_help",
            self._p_vocab,
        )

        for key, label_key, help_key in [
            (
                "not_common_placeholders",
                "review.params_placeholders",
                "review.params_placeholders_help",
            ),
            ("not_all_caps", "review.params_all_caps", "review.params_all_caps_help"),
            ("date", "review.params_date", "review.params_date_help"),
            ("date_order", "review.params_date_order", "review.params_date_order_help"),
            ("url", "review.params_url", "review.params_url_help"),
        ]:
            box = make_checkbox(t(label_key))
            box.setToolTip(t(help_key))
            box.toggled.connect(self._on_params_edited)
            box.setProperty("param_key", key)
            setattr(self, f"_p_{key}", box)
            params_lay.addWidget(box)
        self._params_panel.hide()
        body.addWidget(self._params_panel)
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

    # -- check picker + entry-check params (dv-5id) --------------------------

    @staticmethod
    def _params_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("LabelStrongSM")
        label.setWordWrap(True)
        return label

    @staticmethod
    def _handler_label(handler: str) -> str:
        key = _HANDLER_LABEL_KEYS.get(str(handler or ""))
        return t(key) if key else t("review.check_other", handler=handler)

    # -- the two dropdown items (dv-7zv) -------------------------------------
    #
    # One list per column, used both to build the cell combos and to measure
    # the column, so a column can never be narrower than the widest thing it
    # has to show.

    @staticmethod
    def _level_items() -> list[tuple[str, str]]:
        return [(t(_LEVEL_LABEL_KEYS[level]), level) for level in _LEVELS]

    def _handler_items(self, handler: str = "") -> list[tuple[str, str]]:
        """List the Check column's items, plus the rule's own handler if exotic."""
        items = [
            (t("review.handler_nonempty"), "nonempty"),
            (t("review.handler_looks_correct"), "looks_correct"),
        ]
        if handler and handler not in ("nonempty", "looks_correct"):
            items.append((self._handler_label(handler), handler))
        return items

    def _handler_column_items(self) -> list[tuple[str, str]]:
        """Every handler label the Check column can ever show, for measuring.

        A row's own combo lists only the two standard checks plus that row's
        handler, but the column has to fit the widest label any row shows --
        an exotic handler's label is longer than "Looks plausibly correct".
        """
        items = self._handler_items()
        for key in sorted(_HANDLER_LABEL_KEYS):
            if key not in ("nonempty", "looks_correct"):
                items.append((self._handler_label(key), key))
        return items

    @staticmethod
    def _column_width(items: list[tuple[str, str]], min_width: int) -> int:
        """Return the width a dropdown column needs: widest item + the gaps.

        ``QComboBox.sizeHint()`` measures only the *current* item, so each
        item is selected in turn and the widest hint kept — otherwise a
        column sized from "Required" elides "Not checked" (dv-7zv).
        """
        probe = make_combo(items, height=32, min_width=min_width)
        widest = 0
        try:
            # An unpolished combo measures without its themed chrome (127px
            # against 147px once styled), which is how a column sized from it
            # elided its own text (dv-7zv).
            probe.ensurePolished()
            for index in range(probe.count()):
                probe.setCurrentIndex(index)
                widest = max(widest, probe.sizeHint().width())
        finally:
            probe.setCurrentIndex(0)
        return max(widest, min_width) + 2 * _CELL_H_MARGIN

    def _field_rule_for_selection(
        self,
    ) -> tuple[dict[str, Any] | None, str, str, str]:
        """(fr, block, field, handler) for the current field selection."""
        try:
            parts = str(self._sel_key or "").split("\x1f")
            if len(parts) == 3:
                fr = self._find_field_rule(parts[0], parts[1], parts[2])
                if fr is not None:
                    return fr, parts[0], parts[1], str(fr.get("handler") or "nonempty")
        except Exception:
            pass
        return None, "", "", ""

    @staticmethod
    def _params_lines(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(v) for v in value]
        if isinstance(value, str):
            return [line.strip() for line in value.splitlines() if line.strip()]
        return []

    def _sync_field_extras(
        self, fr: dict[str, Any] | None, block: str, field: str, handler: str
    ) -> None:
        """Show the entry-check params panel for a looks_correct field rule.

        The Check picker itself lives in the rules table's own column
        (dv-7zv), so this only owns the params panel below the response
        template.
        """
        try:
            if handler == "looks_correct":
                self._params_panel.show()
                self._load_params(fr)
            else:
                self._params_panel.hide()
        except Exception:
            pass

    def _hide_field_extras(self) -> None:
        try:
            self._params_panel.hide()
        except Exception:
            pass

    def _load_params(self, fr: dict[str, Any] | None) -> None:
        raw = cast(dict[str, Any], fr).get("params")
        p: dict[str, Any] = raw if isinstance(raw, dict) else {}
        widgets = (
            self._p_min,
            self._p_regex,
            self._p_regex_full,
            self._p_blocklist,
            self._p_vocab,
            self._p_not_common_placeholders,
            self._p_not_all_caps,
            self._p_date,
            self._p_date_order,
            self._p_url,
        )
        for w in widgets:
            try:
                w.blockSignals(True)
            except Exception:
                pass
        try:
            try:
                self._p_min.setValue(int(p.get("min_length") or 0))
            except (TypeError, ValueError):
                self._p_min.setValue(0)
            self._p_regex.setText(str(p.get("regex") or ""))
            self._p_regex_full.setChecked(str(p.get("regex_mode") or "").strip().lower() == "full")
            self._p_blocklist.setValues(self._params_lines(p.get("blocklist")))
            self._p_vocab.setValues(self._params_lines(p.get("controlled_vocabulary")))
            for key in ("not_common_placeholders", "not_all_caps", "date", "date_order", "url"):
                getattr(self, f"_p_{key}").setChecked(bool(p.get(key)))
        finally:
            for w in widgets:
                try:
                    w.blockSignals(False)
                except Exception:
                    pass

    def _on_params_edited(self, *_args: Any) -> None:
        if getattr(self, "_loading", False):
            return
        fr, _block, _field, handler = self._field_rule_for_selection()
        if fr is None or handler != "looks_correct":
            return
        p: dict[str, Any] = {}
        if self._p_min.value() > 0:
            p["min_length"] = int(self._p_min.value())
        rx = self._p_regex.text().strip()
        if rx:
            p["regex"] = rx
        if self._p_regex_full.isChecked():
            p["regex_mode"] = "full"
        blocklist = [value for value in self._p_blocklist.values() if value.strip()]
        if blocklist:
            p["blocklist"] = blocklist
        vocab = [value for value in self._p_vocab.values() if value.strip()]
        if vocab:
            p["controlled_vocabulary"] = vocab
        for key in ("not_common_placeholders", "not_all_caps", "date", "date_order", "url"):
            if getattr(self, f"_p_{key}").isChecked():
                p[key] = True
        if p:
            fr["params"] = p
        else:
            fr.pop("params", None)
        self._mark_dirty()

    def _on_handler_changed(self, _i: int) -> None:
        if getattr(self, "_loading", False):
            return
        combo = self.sender()
        if not isinstance(combo, QComboBox):
            return
        new_handler = combo.currentData()
        if not new_handler:
            return
        block = str(combo.property("block") or "")
        field = str(combo.property("field") or "")
        old = str(combo.property("handler") or "nonempty")
        new = str(new_handler)
        if new == old:
            return
        fr = self._find_field_rule(block, field, old)
        if fr is None:
            # No rule exists yet (level is “unchecked”): revert the picker
            # and point the curator at the level combo instead.
            self._revert_combo(combo, old)
            self._set_status("review.messages.set_level_first")
            return
        if self._find_field_rule(block, field, new) is not None:
            # A rule with this check already exists for the field — do not
            # create a duplicate (block, field, handler) triple; the first
            # match would silently win the params panel.
            self._revert_combo(combo, old)
            self._set_status("review.messages.duplicate_rule")
            return
        fr["handler"] = new
        if new == "looks_correct" and not isinstance(fr.get("params"), dict):
            # Sensible default: catch the obvious placeholder entries first.
            fr["params"] = {"not_common_placeholders": True}
        self._sel_kind = "field"
        self._sel_key = self._rule_sel_key(block, field, new)
        item = self._row_for_combo(combo)
        if item is not None:
            if fr.get("level") in ("required", "optional"):
                data = self._row_data(item)
                data["rule_kind"] = "rule"
                item.setData(0, Qt.ItemDataRole.UserRole, data)
            self._update_field_row_handler(item, new, str(fr.get("requirement") or ""))
        self._mark_dirty()
        self._show_template_for_selection()

    def _revert_combo(self, combo: QComboBox, handler: str) -> None:
        """Put a rejected pick back without re-entering the slot."""
        self._loading = True
        try:
            idx = combo.findData(handler)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
        finally:
            self._loading = False

    def _set_status(self, key: str) -> None:
        try:
            self._status.setText(t(key))
        except Exception:
            pass

    def _update_field_row_handler(
        self, item: QTreeWidgetItem, new_handler: str, req: str = ""
    ) -> None:
        """Re-point one row at a handler in place (never rebuild the tree).

        Both dropdowns carry the handler property and the row's data owns
        it, so the level combo keeps editing the same rule after its check
        changes.
        """
        data = self._row_data(item)
        if not data:
            return
        block = str(data.get("block") or "")
        field = str(data.get("field") or "")
        data["handler"] = new_handler
        item.setData(0, Qt.ItemDataRole.UserRole, data)
        for column in (1, 2):
            combo = self._cell_combo(item, column)
            if combo is not None:
                combo.setProperty("handler", new_handler)
        item.setToolTip(
            0,
            t(
                "review.messages.field_rule_tip",
                block=block,
                field=field,
                handler=new_handler,
            )
            + (f"\n{req}" if req else ""),
        )

    # -- data -> ui --------------------------------------------------------

    def _schema_fields(self) -> list[dict[str, str]]:
        # The live metadatablocks catalog (or a cached copy of its last
        # fetch) wins for the fields it knows — but it may predate our
        # dotted composite-child entries, so the built-in catalog fills the
        # gaps (composite children only). This keeps the review page useful
        # offline and upgrades stale on-disk caches silently.
        if self._schema:
            live = [dict(f) for f in self._schema if isinstance(f, dict) and f.get("field")]
            seen = {(str(f.get("block") or "citation"), str(f.get("field") or "")) for f in live}
            fallback = [dict(f) for f in FIELD_CATALOG if isinstance(f, dict) and f.get("field")]
            for f in fallback:
                key = (str(f.get("block") or "citation"), str(f.get("field") or ""))
                if key not in seen:
                    seen.add(key)
                    live.append(f)
            base = live
        else:
            base = [dict(f) for f in FIELD_CATALOG]
        # Union with fields referenced by any ruleset so custom fields persist.
        seen = {(str(f.get("block") or "citation"), str(f.get("field") or "")) for f in base}
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
        covered: set[tuple[str, str, str]] = set()
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
        groups: dict[str, list[dict[str, Any]]] = {}
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
            ordered = sorted(
                groups,
                key=lambda b: (
                    0 if str(b or "").lower() == "citation" else 1,
                    str(group_labels.get(b, b) or "").lower(),
                ),
            )
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
                def _grp(e: dict[str, Any]) -> str:
                    return str(e.get("field") or "").split(".", 1)[0]

                def _add_field_row(
                    e: dict[str, Any],
                    parent_item: QTreeWidgetItem | None = None,
                    block_item: QTreeWidgetItem | None = None,
                ) -> QTreeWidgetItem:
                    parent_item = parent_item if parent_item is not None else block_item
                    block, field = e["block"], e["field"]
                    handler = str(e["handler"] or "nonempty")
                    child = QTreeWidgetItem([str(e.get("label") or field)])
                    child.setToolTip(
                        0,
                        t(
                            "review.messages.field_rule_tip",
                            block=block,
                            field=field,
                            handler=handler,
                        )
                        + (f"\n{e['req']}" if e["req"] else ""),
                    )
                    # The row's data is the one place that says which rule
                    # this row edits: selection and both dropdowns read it,
                    # so they cannot drift apart (dv-7zv).
                    child.setData(
                        0,
                        Qt.ItemDataRole.UserRole,
                        {
                            "kind": "field",
                            "block": block,
                            "field": field,
                            "handler": handler,
                            "rule_kind": e["kind"],
                        },
                    )
                    level = make_combo(self._level_items(), height=32, min_width=110)
                    level.setCurrentIndex(max(0, level.findData(str(e["level"] or "unchecked"))))
                    level.setProperty("kind", e["kind"])
                    level.setProperty("block", block)
                    level.setProperty("field", field)
                    level.setProperty("handler", handler)
                    level.setToolTip(t("review.column_level_tip"))
                    level.currentIndexChanged.connect(self._on_field_level_changed)
                    check = make_combo(self._handler_items(handler), height=32, min_width=180)
                    check.setCurrentIndex(max(0, check.findData(handler)))
                    check.setProperty("block", block)
                    check.setProperty("field", field)
                    check.setProperty("handler", handler)
                    check.setToolTip(t("review.column_check_tip"))
                    check.currentIndexChanged.connect(self._on_handler_changed)
                    target = parent_item if parent_item is not None else block_item
                    cast(QTreeWidgetItem, target).addChild(child)
                    level_host = make_cell_control(level, v_margin=_CELL_V_MARGIN)
                    check_host = make_cell_control(check, v_margin=_CELL_V_MARGIN)
                    tree.setItemWidget(child, 1, level_host)
                    tree.setItemWidget(child, 2, check_host)
                    # A press on a cell widget never reaches the tree: route
                    # it through the view's filter to the row helper (dv-ud0).
                    for widget in (level, check, level_host, check_host):
                        widget.installEventFilter(self)
                    return child

                groups_by_prefix: dict[str, list[dict[str, Any]]] = {}
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
            fit_tree_height(tree, row_height=40)
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

    # -- row lookup (dv-7zv) -------------------------------------------------

    @staticmethod
    def _row_data(item: QTreeWidgetItem | None) -> dict[str, Any]:
        """One field row's own data ({kind: field, block, field, handler})."""
        try:
            data = item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def _iter_rows(self) -> Iterator[QTreeWidgetItem]:
        """Every field row, in tree order (block and group headings skipped)."""
        try:
            tree = self._field_tree
        except Exception:
            return
        stack = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
        while stack:
            item = stack.pop()
            if item is None:
                continue
            if self._row_data(item).get("kind") == "field":
                yield item
            stack.extend(item.child(i) for i in range(item.childCount()))

    def _cell_combo(self, item: QTreeWidgetItem, column: int) -> QComboBox | None:
        """Return the dropdown in one of a row's two cell hosts (None if absent).

        The cell widget is the transparent host ``make_cell_control`` builds,
        not the combo itself, so the lookup goes through the host.
        """
        try:
            host = self._field_tree.itemWidget(item, column)
        except Exception:
            return None
        if isinstance(host, QComboBox):
            return host
        if host is None:
            return None
        return host.findChild(QComboBox)

    def _row_for_combo(self, combo: QComboBox) -> QTreeWidgetItem | None:
        """Return the field row hosting a given dropdown (a signal sender)."""
        for item in self._iter_rows():
            for column in (1, 2):
                if self._cell_combo(item, column) is combo:
                    return item
        return None

    def _selected_field_row(self) -> QTreeWidgetItem | None:
        """Return the selected field row (None while a block heading is selected)."""
        try:
            items = self._field_tree.selectedItems()
        except Exception:
            return None
        for item in items:
            if self._row_data(item).get("kind") == "field":
                return item
        return None

    def _blocks_any_collapsed(self) -> bool:
        try:
            for bi in range(self._field_tree.topLevelItemCount()):
                top = self._field_tree.topLevelItem(bi)
                if top is None:
                    continue
                if not top.isExpanded():
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
            fit_tree_height(self._field_tree, row_height=40)
            self._update_blocks_btn()
        except Exception:
            pass

    def _refresh_content_list(self) -> None:
        try:
            self._content_list.blockSignals(True)
            self._content_list.clear()
            rules = [
                cr
                for cr in (self._current_ruleset().get("content_rules") or [])
                if isinstance(cr, dict)
            ]
            for cr in rules:
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
            self._content_summary.setText(t("review.content_summary", count=len(rules)))
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
        return f"{block}\x1f{field}\x1f{handler}"

    def _mark_dirty(self) -> None:
        """Surface that an edit landed in memory but not on disk."""
        if self._loading or self._dirty:
            return
        self._dirty = True
        self._footer.set_dirty(True)

    def _clear_dirty(self) -> None:
        self._dirty = False
        self._footer.set_dirty(False)

    # -- selecting a row is a deliberate act (dv-ud0) ------------------------

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Route a press on a cell widget to the row it belongs to.

        QComboBox (and the transparent cell host) eat the press before the
        tree sees it, so a click on a dropdown used to leave the Response
        pane pointing at whichever row was edited before. Hover is never a
        selection: only ``MouseButtonPress`` is handled here.
        """
        if event.type() == QEvent.Type.MouseButtonPress:
            event = cast(QMouseEvent, event)
            item = None
            if obj is self._field_tree.viewport():
                try:
                    pos = event.position().toPoint()
                except Exception:
                    pos = event.pos()
                item = self._field_tree.itemAt(pos)
            elif isinstance(obj, QComboBox):
                item = self._row_for_combo(obj)
            elif getattr(obj, "objectName", lambda: "")() == "CellControlHost":
                combo = obj.findChild(QComboBox)
                if combo is not None:
                    item = self._row_for_combo(combo)
            if item is not None and self._row_data(item):
                self._select_row(item)
        return super().eventFilter(obj, event)

    def _on_row_pressed(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        """Make a press on any part of a field row choose it for editing."""
        self._select_row(item)

    def _on_current_item_changed(
        self, current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None
    ) -> None:
        """Arrow keys move the current row; the pane follows. Hover does not."""
        if self._loading or self._selecting or current is None:
            return
        self._select_row(current)

    def _select_row(self, item: QTreeWidgetItem) -> None:
        """Make one field row the edited rule and retarget the Response pane."""
        data = self._row_data(item)
        if not data or data.get("kind") != "field":
            return
        self._selecting = True
        try:
            tree = self._field_tree
            tree.setCurrentItem(item)
            item.setSelected(True)
        finally:
            self._selecting = False
        self._sel_kind = "field"
        self._sel_key = self._rule_sel_key(
            str(data.get("block") or ""),
            str(data.get("field") or ""),
            str(data.get("handler") or "nonempty"),
        )
        self._show_template_for_selection()

    def _on_field_level_changed(self, _i: int) -> None:
        if self._loading:
            return
        try:
            combo = self.sender()
            if not isinstance(combo, QComboBox):
                return
            item = self._row_for_combo(combo)
            if item is None:
                return
            data = self._row_data(item)
            kind = str(data.get("rule_kind") or "new")
            block = str(data.get("block") or "")
            field = str(data.get("field") or "")
            handler = str(data.get("handler") or "nonempty")
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
            data["rule_kind"] = "rule" if found is not None and level != "unchecked" else "new"
            data["handler"] = handler
            item.setData(0, Qt.ItemDataRole.UserRole, data)
            self._update_field_row_handler(
                item, handler, str(found.get("requirement") or "") if found else ""
            )
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
                self._hide_field_extras()
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
                        data = self._row_data(self._selected_field_row())
                        if data:
                            fr = self._find_field_rule(
                                str(data.get("block") or ""),
                                str(data.get("field") or ""),
                                str(data.get("handler") or "nonempty"),
                            )
                            if fr is not None:
                                self._sel_key = self._rule_sel_key(
                                    str(data.get("block") or ""),
                                    str(data.get("field") or ""),
                                    str(data.get("handler") or "nonempty"),
                                )
                    except Exception:
                        fr = None
                if fr is None:
                    self._sel_label.setText(t("review.select_template"))
                    self._template_edit.setPlainText("")
                    self._hide_field_extras()
                    return
                handler = str(fr.get("handler") or "nonempty")
                parts = str(self._sel_key or "").split("\x1f")
                if len(parts) == 3:
                    self._sync_field_extras(fr, parts[0], parts[1], handler)
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
            import curation.metadata_check as _mc

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
            show_critical(
                self,
                t("review.dialogs.metadata_fields_title"),
                t("review.messages.load_start_failed", exc=exc),
            )

    def _on_fields_finished(self, fields: list[Any]) -> None:
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
