"""The Metadata card: the profile picker, the metadata tree and the results."""

from typing import ClassVar

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from curation.metadata_check import DEFAULT_PROFILE, PROFILES
from ui.dataset.state import DetailState
from ui.i18n import t
from ui.theme import (
    STATE_ERROR_GRAPHIC,
    STATE_SUCCESS_GRAPHIC,
    TEXT_AMBER,
    TEXT_DANGER,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SUBTLE,
    TEXT_SUCCESS,
    transparent_surface_qss,
)
from ui.widgets import AppTree, add_info_tip, make_card, make_combo, make_reset_columns_button


class MetadataSection(DetailState):
    """The Metadata card: the profile picker, the metadata tree and the results."""

    _META_SINGLE_ENTRY_FIELDS: ClassVar[set[tuple[str, str]]] = {("citation", "dsdescription")}

    _META_ACRONYMS: ClassVar[set[str]] = {"id", "url", "uri", "doi", "orcid", "api", "html", "pdf"}

    _META_KEY_OVERRIDES: ClassVar[dict[str, str]] = {
        "dsDescription": "Description",
        "dsDescriptionValue": "Description",
        "dsDescriptionDate": "Date",
        "keywordValue": "Keyword",
    }

    _META_ENTRY_IDENTITY_KEYS = (
        "authorName",
        "contributorName",
        "publicationCitation",
        "keywordValue",
    )

    def _build_metadata_card(self) -> QFrame:
        card, body, _title, header_lay = make_card(t("detail.sections.metadata_check"))
        add_info_tip(
            header_lay,
            t("detail.metadata_check.tip"),
            name=t("detail.sections.metadata_check"),
        )
        # Flush card (manifest-tree pattern): zero body margins; the table
        # bleeds edge-to-edge.
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        # x/xx summary lives in the header, right next to the title (the
        # old in-body summary line was removed).
        self._meta_summary = QLabel(t("detail.metadata_check.not_loaded"))
        self._meta_summary.setObjectName("StateMD")
        self._meta_summary.setTextFormat(Qt.TextFormat.RichText)
        self._meta_summary.setToolTip(t("detail.metadata_check.not_loaded_tip"))
        header_lay.insertWidget(2, self._meta_summary)
        # The two menus and the reset button live on their own row under
        # the title bar, like the File Manifest's filter row. In the title
        # row the card needed 791px - wider than the column it sits in -
        # so the page scrolled sideways at the app's own minimum width.
        meta_tools = QWidget()
        meta_tools.setObjectName("MetadataCheckTools")
        meta_tools.setStyleSheet(transparent_surface_qss("MetadataCheckTools"))
        meta_tools_lay = QHBoxLayout(meta_tools)
        meta_tools_lay.setContentsMargins(16, 8, 16, 8)
        meta_tools_lay.setSpacing(8)
        # Complete/incomplete filter for the checklist table.
        self._meta_filter = make_combo(
            [
                (t("detail.metadata_check.filter_all"), "all"),
                (t("detail.metadata_check.filter_complete"), "complete"),
                (t("detail.metadata_check.filter_incomplete"), "incomplete"),
            ],
            min_width=110,
            tip=t("detail.metadata_check.filter_tip"),
        )
        self._meta_filter.currentIndexChanged.connect(lambda _i: self._apply_meta_filter())
        meta_tools_lay.addWidget(self._meta_filter)
        # Standard 36px field like every other combo (a shorter button here
        # made this menu's rows read differently-sized vs the rest).
        self._profile_combo = make_combo(
            [(info["label"], key) for key, info in PROFILES.items()],
            min_width=140,
        )
        idx = list(PROFILES.keys()).index(DEFAULT_PROFILE) if DEFAULT_PROFILE in PROFILES else 0
        self._profile_combo.setCurrentIndex(idx)
        self._profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        meta_tools_lay.addWidget(self._profile_combo)
        self._meta_reset_btn = make_reset_columns_button(
            "",
            tip=t("detail.metadata_check.reset_columns_tip"),
            accessible_name=t("detail.metadata_check.reset_columns_a11y"),
            fallback_text=t("common.reset"),
        )
        self._meta_reset_btn.clicked.connect(self._on_reset_meta_view)
        meta_tools_lay.addWidget(self._meta_reset_btn)
        meta_tools_lay.addStretch()
        body.addWidget(meta_tools)
        # Every check with its status — an expandable tree
        # (Check | Level | Block | Value | Status). Requirement text lives in the
        # Check cell's tooltip. A repeatable field expands into one child
        # per entry (Author 1, Author 2, …) and one grandchild per
        # subfield (Name, Affiliation, Identifier, …), so a compound value
        # is readable instead of being flattened into one line.
        from PySide6.QtGui import QStandardItemModel as _QStandardItemModel
        from PySide6.QtWidgets import QHeaderView

        self._meta_check_tree = AppTree(row_height=30, flush=True)
        self._meta_model = _QStandardItemModel(0, 5, self)
        self._meta_model.setHorizontalHeaderLabels(
            ["Check", t("detail.metadata_check.level_header"), "Block", "Value", "Status"]
        )
        self._meta_check_tree.setModel(self._meta_model)
        _meta_hdr = self._meta_check_tree.header()
        # Every column is Interactive so each boundary drags - including
        # Value|Status, whose Stretch/ResizeToContents pair used to ignore
        # the mouse (dv-dmv). Value still absorbs the slack and elides
        # long text, but it does so through _fit_meta_value_column, not a
        # Stretch mode (a Stretch section cannot be resized by hand).
        _meta_hdr.setStretchLastSection(False)
        for col in range(5):
            _meta_hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        self._meta_check_tree.setColumnWidth(0, 170)
        self._meta_check_tree.setColumnWidth(1, 110)
        self._meta_check_tree.setColumnWidth(2, 120)
        self._meta_check_tree.setColumnWidth(3, 260)
        self._meta_check_tree.setColumnWidth(4, 120)
        self._meta_check_tree.expanded.connect(self._on_meta_tree_expansion_changed)
        self._meta_check_tree.collapsed.connect(self._on_meta_tree_expansion_changed)
        self._track_table_widths("dataset_meta", _meta_hdr)
        # No internal scrollbars: the card always fits every row; the page
        # canvas scrolls instead. Height is fitted in _fit_meta_tree_height.
        self._meta_check_tree.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._meta_check_tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._meta_check_tree.setFixedHeight(80)
        body.addWidget(self._meta_check_tree)
        return card

    def _apply_meta_filter(self) -> None:
        """Apply the Complete/Incomplete filter by rebuilding the tree.

        The tree is small and model-driven, so rebuilding is simpler and
        safer than hiding rows: a hidden parent would keep its children
        orphaned in the model. The card then refits its height.
        """
        if not hasattr(self, "_meta_check_tree"):
            return
        try:
            mode = self._meta_filter.currentData() or "all"
        except Exception:
            mode = "all"
        results = list(getattr(self, "_meta_results", []))
        if mode == "complete":
            results = [r for r in results if r.get("status") == "complete"]
        elif mode == "incomplete":
            results = [r for r in results if r.get("status") != "complete"]
        self._build_meta_tree(results)

    def _pretty_meta_key(self, key: str) -> str:
        """Human label for a metadata key (``authorAffiliation`` → Affiliation)."""
        raw = str(key or "").strip()
        if not raw:
            return ""
        mapped = self._META_KEY_OVERRIDES.get(raw)
        if mapped:
            return mapped
        import re as _re

        words = _re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", raw).split()
        cleaned = [w.upper() if w.lower() in self._META_ACRONYMS else w.lower() for w in words]
        text = " ".join(cleaned).strip()
        return text[:1].upper() + text[1:] if text else raw

    @staticmethod
    def _meta_display(value) -> str:
        """Compact display text for any metadata value (never raises)."""
        try:
            from curation.metadata_check import _display_value as _dv

            return _dv(value, max_len=1000)
        except Exception:
            try:
                return str(value)
            except Exception:
                return t("common.em_dash")

    @staticmethod
    def _meta_is_compound(value) -> bool:
        """Return True when a dict has real subfields (not just a wrapped ``value``)."""
        if not isinstance(value, dict):
            return False
        keys = [k for k in value if k != "typeName"]
        return any(k != "value" for k in keys)

    def _meta_subfields(self, entry: dict, prefix: str = "") -> list[tuple[str, str]]:
        """(label, display) pairs for one compound metadata entry.

        The entry's own noun is stripped from each subfield label, so an
        author entry reads Name / Affiliation / Identifier rather than
        Author name / Author affiliation / …
        """
        rows: list[tuple[str, str]] = []
        for key, value in entry.items():
            if key == "typeName":
                continue
            if isinstance(value, dict) and "value" in value and not self._meta_is_compound(value):
                shown = self._meta_display(value.get("value"))
            else:
                shown = self._meta_display(value)
            label = self._pretty_meta_key(key)
            if prefix and label.lower().startswith(prefix.lower() + " "):
                trimmed = label[len(prefix) + 1 :]
                if trimmed:
                    label = trimmed[:1].upper() + trimmed[1:]
            rows.append((label, shown))
        return rows

    def _meta_value_entries(self, result: dict) -> list[tuple[str, str, list]]:
        """Child entries for a check: [(label, summary, subfields)]."""
        block = str(result.get("block") or "")
        name = str(result.get("name") or "")
        if not block or not name or self._metadata is None:
            return []
        # The ORCID rule (author.authorIdentifier, handler "orcid") is a
        # list of per-author identifier verdicts, not a second copy of the
        # Author rule's tree. Its per-author list already lives in the
        # Value cell; expanding an author tree here duplicated it.
        rule_id = str(result.get("rule_id") or "")
        if rule_id.endswith("orcid"):
            return []
        try:
            from curation.metadata_check import _field

            meta = self._metadata or {}
            latest = meta.get("latestVersion") or {}
            blocks = latest.get("metadataBlocks") or meta.get("metadataBlocks") or {}
            raw = _field(blocks, block, name)
        except Exception:
            return []
        if isinstance(raw, list):
            seq = raw
        elif self._meta_is_compound(raw):
            seq = [raw]
        else:
            return []
        if not seq:
            return []
        noun = self._pretty_meta_key(name) or str(result.get("field") or "Entry")
        single_entry = (str(block).lower(), str(name).lower()) in self._META_SINGLE_ENTRY_FIELDS
        entries: list[tuple[str, str, list]] = []
        if single_entry and len(seq) == 1 and isinstance(seq[0], dict):
            # Single-entry compound (dsDescription): no "Description 1"
            # entry row — its children attach directly to the check row.
            return [("", "", self._meta_subfields(seq[0], noun))]
        for i, item in enumerate(seq):
            label = f"{noun} {i + 1}"
            if isinstance(item, dict):
                subs = self._meta_subfields(item, noun)
                summary = self._entry_identity_summary(item, subs)
                entries.append((label, summary, subs))
            else:
                entries.append((label, self._meta_display(item), []))
        return entries

    def _entry_identity_summary(self, item: dict, subs: list[tuple[str, str]]) -> str:
        dash = t("common.em_dash")
        for key in self._META_ENTRY_IDENTITY_KEYS:
            raw_sub = item.get(key)
            if raw_sub is None:
                continue
            text = self._meta_display(raw_sub)
            if text and text != dash:
                return text
        return next(
            (text for _lbl, text in subs if text and text != dash),
            dash,
        )

    def _build_meta_tree(self, results: list[dict]) -> None:  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
        """Rebuild the Check | Level | Block | Value | Status tree from results."""
        from PySide6.QtGui import QBrush, QStandardItem

        tree = self._meta_check_tree
        model = self._meta_model
        model.removeRows(0, model.rowCount())

        def _item(
            text: str,
            *,
            tooltip: str = "",
            bold: bool = False,
            color: str | None = None,
            italic: bool = False,
        ) -> QStandardItem:
            item = QStandardItem(str(text))
            item.setEditable(False)
            if tooltip:
                item.setToolTip(tooltip)
            if color:
                item.setForeground(QBrush(QColor(color)))
            font = item.font()
            if bold:
                font.setBold(True)
            if italic:
                font.setItalic(True)
            item.setFont(font)
            return item

        from ui.icons import icon as _icon

        for result in results:
            ok = result.get("status") == "complete"
            status_text = (
                t("detail.metadata_check.status_complete")
                if ok
                else t("detail.metadata_check.status_incomplete")
            )
            requirement = str(result.get("requirement") or "")
            value_text = str(result.get("value", t("common.em_dash")))
            required = str(result.get("level") or "required") == "required"
            level_text = (
                t("detail.metadata_check.level_required")
                if required
                else t("detail.metadata_check.level_optional")
            )
            field_item = _item(
                str(result.get("field") or ""),
                tooltip=requirement,
                bold=True,
                color=TEXT_PRIMARY if ok else TEXT_DANGER,
            )
            level_item = _item(
                level_text,
                tooltip=t("detail.metadata_check.level_tip"),
                bold=required,
                color=TEXT_PRIMARY if required else TEXT_MUTED,
            )
            block_item = _item(
                self._meta_block_label(str(result.get("block") or "")),
                tooltip=(
                    self._meta_block_label(str(result.get("block") or ""))
                    + (f"\n\n{requirement}" if requirement else "")
                ),
            )
            value_item = _item(
                value_text,
                tooltip=requirement + t("detail.metadata_check.value_tooltip", value=value_text),
            )
            status_item = _item(
                status_text,
                tooltip=requirement,
                bold=True,
                color=TEXT_SUCCESS if ok else TEXT_DANGER,
            )
            try:
                status_item.setIcon(
                    _icon("check", color=STATE_SUCCESS_GRAPHIC)
                    if ok
                    else _icon("x", color=STATE_ERROR_GRAPHIC)
                )
            except Exception:
                pass
            parent = [field_item, level_item, block_item, value_item, status_item]

            def _sub_row(sub_label, sub_value):
                return [
                    _item(sub_label, color=TEXT_MUTED),
                    _item(""),
                    _item(""),
                    _item(
                        sub_value,
                        tooltip=sub_value,
                        italic=sub_value == t("common.em_dash"),
                        color=TEXT_SUBTLE if sub_value == t("common.em_dash") else None,
                    ),
                    _item(""),
                ]

            for label, summary, subs in self._meta_value_entries(result):
                if label:
                    child = [
                        _item(label, color=TEXT_MUTED, bold=True),
                        _item(""),
                        _item(""),
                        _item(summary, tooltip=summary),
                        _item(""),
                    ]
                    parent[0].appendRow(child)
                    for sub_label, sub_value in subs:
                        child[0].appendRow(_sub_row(sub_label, sub_value))
                else:
                    # Single-compound children attach directly to the parent
                    # row; a child equal to the parent Value is dropped.
                    for sub_label, sub_value in subs:
                        if sub_value and str(sub_value) == value_text:
                            continue
                        parent[0].appendRow(_sub_row(sub_label, sub_value))
            model.appendRow(parent)

        try:
            tree.blockSignals(True)
            tree.expandAll()
        finally:
            tree.blockSignals(False)
        self._fit_meta_tree_height()
        # Size the fixed columns to their content (with sane caps), then
        # hand the leftover width to Value. Programmatic: wrapped in the
        # layout's suppressed scope so a rebuild never overwrites the
        # widths the user dragged (only their own gestures persist).
        try:
            layout = self._layout_for("dataset_meta", tree.header())
            with layout.suppressed():
                for col, floor, ceiling in (
                    (0, 170, 320),
                    (1, 88, 130),
                    (2, 100, 220),
                    (4, 90, 160),
                ):
                    tree.resizeColumnToContents(col)
                    tree.setColumnWidth(col, max(floor, min(ceiling, tree.columnWidth(col))))
        except Exception:
            pass
        self._fit_meta_value_column()

    def _on_meta_tree_expansion_changed(self, _index=None) -> None:
        self._fit_meta_tree_height()

    def _fit_meta_value_column(self) -> None:
        """Give the metadata table's Value column the leftover width.

        With every column Interactive (so the Value|Status boundary
        drags - dv-dmv) no section stretches; this keeps the (scrollbar
        -less) table filling its card instead of leaving a gap after
        Status. Programmatic, so it never persists over a user's drag.
        """
        try:
            tree = self._meta_check_tree
        except AttributeError:
            return
        hdr = tree.header()
        if hdr is None or hdr.count() < 5:
            return
        # Value column is at index 3 (Check | Level | Block | Value | Status).
        others = sum(hdr.sectionSize(i) for i in range(hdr.count()) if i != 3)
        target = max(48, tree.viewport().width() - others)
        if hdr.sectionSize(3) == target:
            return
        try:
            layout = self._layout_for("dataset_meta", hdr)
            with layout.suppressed():
                hdr.resizeSection(3, target)
        except Exception:
            try:
                hdr.resizeSection(3, target)
            except Exception:
                pass

    def _fit_meta_tree_height(self) -> None:
        """Grow the checks tree to its visible rows (no inner scrollbar)."""
        try:
            tree = self._meta_check_tree
            model = tree.model()
            visible_rows = 0
            if model is not None:
                stack = [tree.rootIndex()]
                while stack:
                    parent = stack.pop()
                    count = model.rowCount(parent)
                    visible_rows += count
                    for r in range(count):
                        idx = model.index(r, 0, parent)
                        if model.hasChildren(idx) and tree.isExpanded(idx):
                            stack.append(idx)
            header_h = tree.header().height() or 30
            tree.setFixedHeight(max(80, header_h + visible_rows * 30 + 2))
        except Exception:
            pass

    def _meta_block_label(self, block: str) -> str:
        """Display name for a metadata block id (catalog label, else capitalized)."""
        try:
            b = str(block or "").strip()
        except Exception:
            b = ""
        if not b:
            return "—"
        try:
            cache = getattr(self, "_block_labels", None)
            if cache is None:
                cache = {}
                try:
                    from curation.client import read_metadata_fields_cache

                    for f in (
                        read_metadata_fields_cache(
                            self._config.app.workspace, self._config.dataverse.base_url
                        )
                        or []
                    ):
                        if isinstance(f, dict) and f.get("block") and f.get("block_label"):
                            cache.setdefault(str(f["block"]), str(f["block_label"]))
                except Exception:
                    pass
                self._block_labels = cache
            if b in cache:
                return cache[b]
        except Exception:
            pass
        return b[:1].upper() + b[1:]

    def _populate_completeness(self, metadata: dict) -> None:
        # Rule-driven evaluation (keeps rule_id/level/pending for Response).
        try:
            from curation.metadata_check import check_with_ruleset

            full, ruleset = check_with_ruleset(
                metadata, self._profile, self._inventory, self._staged_dir_or_none()
            )
            self._completeness_full = full
            self._ruleset = ruleset
            results = [dict(r) for r in full]
        except Exception:
            from curation.metadata_check import check_metadata_completeness

            results = check_metadata_completeness(
                metadata, profile=self._profile, inventory=self._inventory
            )
            self._completeness_full = [
                {
                    **r,
                    "rule_id": r.get("field", ""),
                    "level": "required",
                    "pending": False,
                    "response_template": "",
                }
                for r in results
            ]
        complete = sum(1 for r in results if r["status"] == "complete")
        total = len(results)
        color = (
            TEXT_SUCCESS
            if complete == total
            else TEXT_AMBER
            if complete > total / 2
            else TEXT_DANGER
        )
        # Header carries just the count (profile name is already visible in
        # the header combo; the old in-body summary line was removed).
        self._meta_summary.setText(
            t(
                "detail.metadata_check.fields_complete_html",
                color=color,
                complete=complete,
                total=total,
            )
        )
        # Auto-checks header belongs to the checks summary (see
        # _refresh_curation_preview); leave it alone once a report exists.
        if self._report is None:
            self._auto_summary.setText(
                t(
                    "detail.metadata_check.fields_complete",
                    complete=complete,
                    total=total,
                )
            )
        # Full per-check tree: Check | Level | Block | Value | Status
        # (requirement in the Check cell's tooltip). Repeatable fields grow child rows
        # per entry and grandchild rows per subfield.
        self._meta_results = results
        # Apply the active Complete/Incomplete filter; it rebuilds the tree
        # and refits the card height to the visible rows (no inner scroll).
        self._apply_meta_filter()
        # Keep the Response draft in sync (preserves manual edits).
        try:
            self._refresh_response()
        except Exception:
            pass

    def _toggle_raw(self) -> None:
        from ui.icons import icon as _icon

        vis = not self._raw_view.isVisible()
        self._raw_view.setVisible(vis)
        self._raw_btn.setText(
            t("detail.header.hide_raw_metadata") if vis else t("detail.header.show_raw_metadata")
        )
        try:
            self._raw_btn.setIcon(_icon("chevron-up" if vis else "chevron-right"))
        except Exception:
            pass
