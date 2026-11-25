"""The Metadata card: the profile picker, the metadata tree and the results."""

from typing import Any, ClassVar

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from curation.metadata_check import (
    DEFAULT_PROFILE,
    PROFILES,
)
from curation.storage import finding_key
from ui.dataset.state import DetailState
from ui.i18n import t
from ui.theme import (
    ACCENT_PRIMARY,
    ACTIVE_THEME,
    BORDER_SUBTLE,
    STATE_ERROR_GRAPHIC,
    STATE_WARNING_GRAPHIC,
    TEXT_AMBER,
    TEXT_DANGER,
    TEXT_MUTED,
    TEXT_SUCCESS,
    transparent_surface_qss,
)
from ui.widgets import (
    add_info_tip,
    make_action_button,
    make_badge,
    make_caption_label,
    make_card,
    make_combo,
    make_disposition_combo,
    make_small_body_label,
    set_icon,
    set_sheet,
)


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
    _META_ENTRY_IDENTITY_KEYS: ClassVar[tuple[str, ...]] = (
        "authorName",
        "contributorName",
        "publicationCitation",
        "keywordValue",
    )

    def _build_metadata_card(self) -> QFrame:
        card, body, _title, header_lay = make_card(t("detail.sections.dataset_checks"))
        # The card body adds no padding of its own (dv-3d0.3): the tools
        # row, the metadata rows and the automated section each supply
        # their own 16px inset, so the single card keeps one left edge.
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self._meta_card_body = body
        add_info_tip(
            header_lay,
            t("detail.metadata_check.tip"),
            name=t("detail.sections.dataset_checks"),
            group="Checks",
        )
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
        meta_tools.setStyleSheet(transparent_surface_qss("MetadataCheckTools", theme=ACTIVE_THEME))
        meta_tools_lay = QHBoxLayout(meta_tools)
        meta_tools_lay.setContentsMargins(16, 8, 16, 8)
        meta_tools_lay.setSpacing(8)
        # One filter for the whole card (dv-3d0.3): the metadata rows and
        # the automated results below share this set of status names, so
        # the card can never show two contradictory filter vocabularies.
        self._check_filter = make_combo(
            [
                (t("detail.checks.filter_all"), "all"),
                (t("detail.checks.filter_complete"), "complete"),
                (t("detail.checks.filter_incomplete"), "incomplete"),
                (t("detail.checks.filter_warning"), "warning"),
                (t("detail.checks.filter_error"), "error"),
                (t("detail.checks.filter_skipped"), "skipped"),
            ],
            min_width=130,
            tip=t("detail.checks.filter_tip"),
        )
        self._check_filter.currentIndexChanged.connect(self._on_check_filter_changed)
        meta_tools_lay.addWidget(self._check_filter)
        # Historical handle: tests and older callers reach for _meta_filter.
        self._meta_filter = self._check_filter
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
        meta_tools_lay.addStretch()
        body.addWidget(meta_tools)
        # One card per check (dv-h70), the Auto-Checks idiom: icon + bold
        # title + one-line verdict sentence + right-aligned badge, with an
        # expandable drawer for compound entries and block section headers.
        # The page canvas scrolls — the card itself never scrolls.
        self._meta_body = QWidget()
        self._meta_body_lay = QVBoxLayout(self._meta_body)
        self._meta_body_lay.setContentsMargins(16, 12, 16, 12)
        self._meta_body_lay.setSpacing(8)
        self._meta_row_results: list[dict[str, Any]] = []
        self._meta_row_widgets: list[tuple[QFrame, int]] = []
        self._meta_body_lay.addWidget(self._meta_pending_row())
        body.addWidget(self._meta_body)
        # The rail jumps to this label on the card's own header line; there
        # is no second heading above the card (dv-gfx.5).
        self._dataset_checks_heading = _title
        return card

    def _on_check_filter_changed(self, *_args: Any) -> None:
        """Apply the card-wide status filter to both row families."""
        self._apply_meta_filter()
        try:
            self._apply_auto_filter()
        except Exception:
            pass

    def _apply_meta_filter(self) -> None:
        """Apply the card-wide status filter to the metadata rows.

        The result set is small, so rebuilding is simpler and safer than
        hiding rows. The page canvas scrolls — the card itself never grows
        an inner scrollbar.
        """
        if not hasattr(self, "_meta_body_lay"):
            return
        try:
            mode = self._check_filter.currentData() or "all"
        except Exception:
            mode = "all"
        results = list(getattr(self, "_meta_results", []))
        unchecked = list(getattr(self, "_unchecked_results", []))
        if mode == "complete":
            results = [r for r in results if r.get("status") == "complete"]
        elif mode == "incomplete":
            results = [r for r in results if r.get("status") == "incomplete"]
        elif mode == "warning":
            results = [
                r
                for r in results
                if r.get("status") == "incomplete"
                and not r.get("pending")
                and str(r.get("level") or "required") != "required"
            ]
        elif mode == "error":
            results = [
                r
                for r in results
                if r.get("status") == "incomplete"
                and not r.get("pending")
                and str(r.get("level") or "required") == "required"
            ]
        elif mode == "skipped":
            results = list(unchecked)
        else:  # "all": every row, checked and not checked
            results = results + unchecked
        self._build_meta_rows(results)

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
    def _meta_display(value: Any) -> str:
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
    def _meta_is_compound(value: Any) -> bool:
        """Return True when a dict has real subfields (not just a wrapped ``value``)."""
        if not isinstance(value, dict):
            return False
        keys = [k for k in value if k != "typeName"]
        return any(k != "value" for k in keys)

    def _meta_subfields(self, entry: dict[str, Any], prefix: str = "") -> list[tuple[str, str]]:
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

    def _meta_value_entries(self, result: dict[str, Any]) -> list[tuple[str, str, list[Any]]]:
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
        entries: list[tuple[str, str, list[Any]]] = []
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

    def _entry_identity_summary(self, item: dict[str, Any], subs: list[tuple[str, str]]) -> str:
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
                return str(cache[b])
        except Exception:
            pass
        return b[:1].upper() + b[1:]

    def _populate_completeness(self, metadata: dict[str, Any]) -> None:
        # Rule-driven evaluation (keeps rule_id/level/pending for Response).
        try:
            from curation.metadata_check import check_with_ruleset

            full, ruleset = check_with_ruleset(
                metadata,
                self._profile,
                self._inventory,
                self._staged_dir_or_none(),
                include_unchecked=True,
            )
            self._completeness_full = [r for r in full if r.get("status") != "skipped"]
            self._unchecked_results = [r for r in full if r.get("status") == "skipped"]
            self._ruleset = ruleset
            results = [dict(r) for r in self._completeness_full]
        except Exception:
            from curation.metadata_check import check_metadata_completeness

            results = check_metadata_completeness(
                metadata, profile=self._profile, inventory=self._inventory
            )
            self._unchecked_results = []
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
            self._set_auto_summary(
                t(
                    "detail.metadata_check.fields_complete",
                    complete=complete,
                    total=total,
                )
            )
        self._meta_loaded = True
        self._meta_results = results
        # Apply the active filter; it rebuilds the rows (no inner scroll).
        self._apply_meta_filter()
        # The rail's passed/warning pills include metadata completeness, and
        # they must move as soon as it is known (dv-gfx.14).
        try:
            self._refresh_rail_counts()
        except Exception:
            pass
        # Keep the Response draft in sync (preserves manual edits).
        try:
            self._refresh_response()
        except Exception:
            pass

    def _toggle_raw(self) -> None:

        vis = not self._raw_view.isVisible()
        self._raw_view.setVisible(vis)
        self._raw_btn.setText(
            t("detail.header.hide_raw_metadata") if vis else t("detail.header.show_raw_metadata")
        )
        try:
            set_icon(self._raw_btn, "chevron-up" if vis else "chevron-right")
        except Exception:
            pass

    def _build_meta_rows(self, results: list[dict[str, Any]]) -> None:  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
        """Rebuild the rows; the caller has already applied the filter."""
        lay = self._meta_body_lay
        self._clear_meta_body()
        self._meta_row_results = list(results)

        if not results:
            if getattr(self, "_meta_loaded", False):
                lay.addWidget(make_small_body_label(t("detail.metadata_check.no_results")))
            else:
                lay.addWidget(self._meta_pending_row())
            return

        # Group by block, citation first, then alphabetical by display name.
        groups: dict[str, list[tuple[int, dict[str, Any]]]] = {}
        for idx, r in enumerate(results):
            groups.setdefault(str(r.get("block") or "other"), []).append((idx, r))

        def _group_key(block: str) -> tuple[int, str]:
            return (
                0 if block.lower() == "citation" else 1,
                (self._meta_block_label(block) or block).lower(),
            )

        for block in sorted(groups, key=_group_key):
            rows = groups[block]
            checked = [r for _i, r in rows if r.get("status") != "skipped"]
            complete = sum(1 for r in checked if r.get("status") == "complete")
            # Rows first: the section header's toggle needs the row widgets.
            # Entries carry an is_drawer flag so collapsing the block only
            # hides what the user had open, never forces a drawer shut.
            widgets: list[tuple[QFrame, bool]] = []
            for idx, result in rows:
                row, drawer = self._meta_row(result, idx)
                widgets.append((row, False))
                if drawer is not None:
                    widgets.append((drawer, True))
            label = self._meta_block_label(block) or (block[:1].upper() + block[1:])
            if checked:
                counts_text = t(
                    "detail.metadata_check.block_counts",
                    complete=complete,
                    total=len(checked),
                )
            else:
                counts_text = t("detail.metadata_check.block_unchecked")
            frame, btn, chev = self._meta_section_header(label, counts_text)
            open_state = {"open": True}

            def _toggle(
                _c: bool = False,
                _rows: list[tuple[QFrame, bool]] = widgets,
                _open: dict[str, bool] = open_state,
                _chev: QLabel = chev,
            ) -> None:
                opening = not _open["open"]
                _open["open"] = opening
                for w, is_drawer in _rows:
                    if is_drawer:
                        # Restore the drawer's own open state, not "always
                        # visible" — a collapsed block must not reopen it.
                        w.setVisible(opening and bool(w.property("drawer_open")))
                    else:
                        w.setVisible(opening)
                from PySide6.QtCore import QSize

                from ui.icons import icon as _ic

                _chev.setPixmap(
                    _ic(
                        "chevron-down" if opening else "chevron-right", color=TEXT_MUTED, size=16
                    ).pixmap(QSize(16, 16))
                )

            btn.clicked.connect(_toggle)
            lay.addWidget(frame)
            for w, _is_drawer in widgets:
                lay.addWidget(w)
        lay.addStretch(1)

    def _meta_row(  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
        self, result: dict[str, Any], idx: int
    ) -> tuple[QFrame, QFrame | None]:
        """One rule as an Auto-Checks row; returns (row, drawer_or_None)."""
        dash = t("common.em_dash")
        status = str(result.get("status") or "incomplete")
        rule_id = str(result.get("rule_id") or "")
        requirement = str(result.get("requirement") or "")
        # dv-7w3: a pending row means "no data yet", not a finding — no
        # disposition controls; render it muted so it can't read as one.
        pending = bool(result.get("pending"))
        level_required = str(result.get("level") or "required") == "required"
        label = str(result.get("field") or "")
        value_text = str(result.get("value") or dash)

        frame = QFrame()
        frame.setObjectName("AutoCheckRow")
        frame.setProperty("meta_field", label)
        frame.setProperty("meta_block", str(result.get("block") or ""))
        frame.setProperty("meta_rule_id", str(result.get("rule_id") or ""))
        from ui.icons import icon_label as _icon_label

        if pending:
            # Pending = no data yet: muted row, neutral badge, no bar.
            set_sheet(
                frame,
                "surface_frame",
                "SURFACE_SUBTLE",
                "BORDER_SUBTLE",
                selector="QFrame#AutoCheckRow",
            )
            icon_name, icon_color = "circle-dashed", TEXT_MUTED
            badge_text = t("detail.metadata_check.status_pending")
            badge_bg, badge_fg = "SURFACE_ALT", "TEXT_MUTED"
        elif status == "complete":
            set_sheet(
                frame,
                "surface_frame",
                "SURFACE_TINT",
                "BORDER_SUBTLE",
                selector="QFrame#AutoCheckRow",
            )
            icon_name, icon_color = "check", ACCENT_PRIMARY
            badge_text = t("detail.metadata_check.status_complete")
            badge_bg, badge_fg = "ACCENT_PRIMARY", "TEXT_ON_ACCENT"
        elif status == "skipped":
            set_sheet(
                frame,
                "surface_frame",
                "SURFACE_SUBTLE",
                "BORDER_SUBTLE",
                selector="QFrame#AutoCheckRow",
            )
            icon_name, icon_color = "circle-dashed", TEXT_MUTED
            badge_text = t("detail.metadata_check.status_unchecked")
            badge_bg, badge_fg = "SURFACE_ALT", "TEXT_MUTED"
        elif level_required:
            set_sheet(
                frame,
                "surface_frame",
                "STATE_ERROR_BG",
                "STATE_ERROR_BORDER",
                selector="QFrame#AutoCheckRow",
            )
            icon_name, icon_color = "octagon-x", STATE_ERROR_GRAPHIC
            badge_text = t("detail.metadata_check.status_incomplete")
            badge_bg, badge_fg = "STATE_ERROR_BG", "STATE_ERROR_TEXT"
        else:
            set_sheet(
                frame,
                "surface_frame",
                "STATE_ERROR_SURFACE",
                "STATE_ERROR_BORDER",
                selector="QFrame#AutoCheckRow",
            )
            icon_name, icon_color = "octagon-alert", STATE_WARNING_GRAPHIC
            badge_text = t("detail.metadata_check.status_incomplete")
            badge_bg, badge_fg = "STATE_ERROR_BG", "STATE_ERROR_TEXT"

        lay = QHBoxLayout(frame)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(8)
        if not pending:
            # dv-onk: no coloured bar; the required/optional distinction
            # stays on the tooltip (both levels described).
            frame.setToolTip(t("detail.metadata_check.level_tip"))
        lay.addWidget(_icon_label(icon_name, size=16, color=icon_color))

        txt = QVBoxLayout()
        txt.setSpacing(1)
        title = QLabel(label or dash)
        title.setObjectName("LabelStrongSM")
        txt.addWidget(title)
        txt.addWidget(make_caption_label(value_text))
        lay.addLayout(txt, 1)

        # dv-32x: inline disposition controls on incomplete findings, and
        # the right-click menu as a secondary path (top-level rows only).
        disposition_key = ""
        if status == "incomplete" and not pending:
            disposition_key = finding_key(rule_id or label, "", requirement or label)
            current = self._dispositions_map().get(disposition_key, {})
            token = str(current.get("disposition") or "")
            note = str(current.get("note") or "")
            combo = make_disposition_combo(
                token,
                on_change=lambda tok: self._on_disposition_changed(disposition_key, tok),
            )
            lay.addWidget(combo)
            note_btn = make_action_button(
                t("detail.disposition.note_action"), kind="ghost", size="sm"
            )
            if note:
                note_btn.setToolTip(note)
            note_btn.clicked.connect(
                lambda _c=False, k=disposition_key: self._on_edit_disposition_note(k)
            )
            lay.addWidget(note_btn)
            frame.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

            def _on_context_menu(pos: QPoint, k: str = disposition_key) -> None:
                self._show_disposition_menu(k, frame.mapToGlobal(pos))

            frame.customContextMenuRequested.connect(_on_context_menu)

        # Compound fields (authors, contacts, …) expand into a drawer.
        drawer = None
        try:
            entries = self._meta_value_entries(result)
        except Exception:
            entries = []
        if entries:
            drawer = self._meta_drawer(entries)
            drawer.setProperty("drawer_open", False)
            drawer.hide()
            btn = QToolButton(frame)
            btn.setAutoRaise(True)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            set_icon(btn, "chevron-right", color="TEXT_MUTED", size=14)
            btn.setFixedSize(28, 28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(t("detail.metadata_check.drawer_tip"))

            def _toggle_drawer(
                _c: bool = False, _d: QFrame = drawer, _btn: QToolButton = btn
            ) -> None:
                opening = _d.isHidden()
                _d.setVisible(opening)
                # Section collapse/expand reads this to restore the drawer's
                # own open state instead of forcing it open.
                _d.setProperty("drawer_open", opening)
                set_icon(
                    _btn,
                    "chevron-down" if opening else "chevron-right",
                    color="TEXT_MUTED",
                    size=14,
                )

            btn.clicked.connect(_toggle_drawer)
            lay.addWidget(btn)

        badge = make_badge(
            badge_text,
            background=badge_bg,
            foreground=badge_fg,
            border=BORDER_SUBTLE,
            chip=False,
        )
        # Same badge metrics as the automated rows (dv-3d0.3): one card,
        # one verdict badge size, so the two families line up column to
        # column instead of drifting by a pixel or two.
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedHeight(20)
        badge.setMinimumWidth(56)
        lay.addWidget(badge)

        if requirement:
            frame.setToolTip(
                requirement + t("detail.metadata_check.value_tooltip", value=value_text)
            )
        else:
            frame.setToolTip(value_text)
        self._meta_row_widgets.append((frame, idx))
        return frame, drawer

    def _meta_drawer(self, entries: list[tuple[str, str, list[Any]]]) -> QFrame:
        """Build the inline expansion for a compound field, one block per entry."""
        frame = QFrame()
        frame.setObjectName("AutoCheckRow")
        set_sheet(
            frame,
            "surface_frame",
            "SURFACE_SUBTLE",
            "BORDER_SUBTLE",
            selector="QFrame#AutoCheckRow",
        )
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(38, 6, 12, 8)
        lay.setSpacing(6)
        for label, summary, subs in entries:
            if label:
                entry = QLabel(label)
                entry.setObjectName("LabelStrongSM")
                lay.addWidget(entry)
                if summary:
                    lay.addWidget(make_caption_label(summary))
            for sub_label, sub_value in subs:
                lay.addWidget(
                    make_caption_label(
                        t(
                            "checks.check_text.detail_line",
                            label=sub_label,
                            value=sub_value,
                        )
                    )
                )
        return frame

    def _meta_section_header(self, label: str, counts_text: str) -> tuple[QFrame, Any, QLabel]:
        """Block heading: chevron + bold label + counts; click toggles the block."""
        from PySide6.QtCore import QSize

        from ui.icons import icon as _icon

        frame = QFrame()
        frame.setObjectName("MetaSectionHeader")
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(2, 4, 2, 2)
        lay.setSpacing(6)
        chev = QLabel()
        chev.setFixedSize(20, 20)
        chev.setPixmap(_icon("chevron-down", color=TEXT_MUTED, size=14).pixmap(QSize(16, 16)))
        btn = make_action_button(label, kind="ghost", size="sm")
        counts = make_caption_label(counts_text)
        lay.addWidget(chev)
        lay.addWidget(btn)
        lay.addWidget(counts)
        lay.addStretch(1)
        return frame, btn, chev

    def _clear_meta_body(self) -> None:
        lay = self._meta_body_lay
        while lay.count():
            item = lay.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        self._meta_row_results = []
        self._meta_row_widgets = []

    def _meta_pending_row(self) -> QFrame:
        """Return the placeholder shown until completeness has been evaluated."""
        frame = QFrame()
        frame.setObjectName("AutoCheckRow")
        set_sheet(
            frame, "surface_frame", "SURFACE_TINT", "BORDER_SUBTLE", selector="QFrame#AutoCheckRow"
        )
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(8)
        from ui.icons import icon_label as _icon_label

        lay.addWidget(_icon_label("database", size=16, color=TEXT_MUTED))
        lay.addWidget(make_small_body_label(t("detail.metadata_check.pending_body")), 1)
        btn = make_action_button(t("detail.header.load_metadata"), kind="secondary", size="sm")
        btn.clicked.connect(lambda _c=False: self._on_load_metadata())
        lay.addWidget(btn)
        return frame
