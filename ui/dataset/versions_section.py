"""The Version log card: the version list and the compare view."""

from typing import Any

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.dataset.state import DetailState
from ui.i18n import t
from ui.theme import (
    ACCENT_PRIMARY,
    TEXT_DANGER,
    TEXT_SUBTLE,
    TEXT_SUCCESS,
    colour,
    enable_list_copy,
)
from ui.widgets import (
    AppTable,
    add_info_tip,
    make_card,
    make_field_label,
    make_list,
    make_reset_columns_button,
    make_small_body_label,
    set_flush_table_style,
    set_sheet,
)


class VersionsSection(DetailState):
    """The Version log card: the version list and the compare view."""

    def _build_version_card(self) -> QFrame:
        """Version log: every version plus the published→draft diff."""
        card, _body_host, _title, header_lay = make_card(t("detail.sections.version_log"))
        add_info_tip(
            header_lay,
            t("detail.version_log.tip"),
            name=t("detail.sections.version_log"),
            group="General",
        )
        # Flush card (manifest-tree pattern): dynamic children are edge to
        # edge and paint their own corners in _populate_version_diff.
        _body_host.setContentsMargins(0, 0, 0, 0)
        _body_host.setSpacing(0)
        # Named not-loaded state, never "—" (2026-10-02 P2).
        self._version_summary = make_field_label(t("detail.version_log.not_loaded"))
        header_lay.addWidget(self._version_summary)
        # The reset is a table tool: it rides on the card's title bar so
        # there is one header line per card (dv-gfx.5, item 8).
        self._version_reset_btn = make_reset_columns_button(
            "",
            tip=t("detail.version_log.reset_columns_tip"),
            accessible_name=t("detail.version_log.reset_columns_a11y"),
            fallback_text=t("common.reset"),
        )
        self._version_reset_btn.clicked.connect(self._on_reset_version_view)
        header_lay.addStretch(1)
        header_lay.addWidget(self._version_reset_btn)
        self._version_body = _body_host
        return card

    def _version_placeholder(self, text: str) -> None:
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(16, 12, 16, 12)
        ph = make_small_body_label(text)
        lay.addWidget(ph)
        self._version_body.addWidget(wrap)

    @staticmethod
    def _short(value: str, limit: int = 150) -> str:
        s = (value or "").strip()
        return (s[:limit] + "…") if len(s) > limit else (s or t("common.em_dash"))

    def _populate_version_diff(self) -> None:  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
        """Render the version list plus the published→draft diff."""
        from PySide6.QtWidgets import QListWidgetItem

        while self._version_body.count():
            item = self._version_body.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        diff = self._version_diff
        versions = self._versions if isinstance(self._versions, list) else []
        versions = [v for v in versions if isinstance(v, dict)]
        # Flush children in card order: corners are painted by position
        # (first: square top; last: 8px bottom; middle: square both).
        flush_widgets: list[tuple[QWidget, str]] = []

        def _apply_flush_corners() -> None:
            for i, (w, kind) in enumerate(flush_widgets):
                last = i == len(flush_widgets) - 1
                try:
                    if kind == "table" and isinstance(w, QTableWidget):
                        set_flush_table_style(w, last=last)
                    else:
                        set_sheet(w, "list", last, True)
                except Exception:
                    pass

        def _version_line(v: dict[str, Any]) -> tuple[str, str]:
            num = v.get("number", "") or ""
            state = (v.get("state", "") or "").upper()
            ct, rt = v.get("create_time", ""), v.get("release_time", "")
            unknown = t("detail.version_log.date_unknown")
            if state == "DRAFT":
                return (
                    t("detail.version_log.draft_current", date=ct[:10] or unknown),
                    ACCENT_PRIMARY,
                )
            if state == "DEACCESSIONED":
                return (
                    t(
                        "detail.version_log.deaccessioned",
                        num=num,
                        date=(rt or ct)[:10] or unknown,
                    ),
                    TEXT_DANGER,
                )
            if rt:
                return (
                    t("detail.version_log.published", num=num, date=rt[:10]),
                    TEXT_SUCCESS,
                )
            return (
                t("detail.version_log.created", num=num, date=ct[:10] or unknown),
                TEXT_SUBTLE,
            )

        # Version list first (current + all previous)
        if versions:
            vlist = make_list(flush=True, last=True)
            vlist.setMaximumHeight(min(150, 30 + 26 * len(versions)))
            enable_list_copy(vlist)
            for v in versions:
                text, color = _version_line(v)
                entry = QListWidgetItem(text)
                entry.setToolTip(text)
                entry.setForeground(QColor(color))
                vlist.addItem(entry)
            self._version_body.addWidget(vlist)
            flush_widgets.append((vlist, "list"))
        elif self._metadata is None:
            self._version_summary.setText(t("detail.version_log.not_loaded"))
            self._version_placeholder(t("detail.version_log.comparison_placeholder"))
            return
        else:
            # Metadata loaded but no version history came back: first version.
            initial = QListWidgetItem(t("detail.version_log.initial_draft"))
            initial.setToolTip(t("detail.version_log.initial_draft_tip"))
            initial.setForeground(QColor(ACCENT_PRIMARY))
            vlist = make_list(flush=True, last=True)
            vlist.setMaximumHeight(56)
            vlist.addItem(initial)
            self._version_body.addWidget(vlist)
            flush_widgets.append((vlist, "list"))

        n_versions = len(versions) if versions else 1
        if not diff:
            self._version_summary.setText(t("detail.version_log.version_count", count=n_versions))
            _apply_flush_corners()
            return
        old_num = (diff.get("old") or {}).get("number") or "published"
        total = int(diff.get("total_changes") or 0)
        meta = diff.get("metadata_changes") or []
        terms = diff.get("terms_changes") or []
        self._version_summary.setText(
            t(
                "detail.version_log.version_count_changes",
                count=n_versions,
                old=old_num,
                changes=total,
            )
        )
        if total == 0:
            self._version_placeholder(t("detail.version_log.no_changes", num=old_num))
            return
        # Metadata + terms field changes
        rows = [
            (c.get("field", ""), c.get("block", ""), c.get("old", ""), c.get("new", ""))
            for c in meta
        ]
        rows += [
            (
                t("detail.version_log.terms_row", field=c.get("field", "")),
                t("detail.version_log.terms_of_access"),
                c.get("old", ""),
                c.get("new", ""),
            )
            for c in terms
        ]
        if rows:
            table = AppTable(
                [
                    t("detail.version_log.col_field"),
                    t("detail.version_log.col_previous", num=old_num),
                    t("detail.version_log.col_new"),
                ],
                widths={0: 190, 1: 220, 2: 220},
                row_height=30,
            )
            table.setSortingEnabled(False)
            table.setRowCount(len(rows))
            self._track_table_widths("dataset_version", table.horizontalHeader())
            table.setMaximumHeight(260)
            for r, (field, block, old_v, new_v) in enumerate(rows):
                f_item = QTableWidgetItem(field)
                f_item.setToolTip(
                    t("detail.version_log.field_tooltip", block=block, field=field)
                    if block
                    else field
                )
                o_item = QTableWidgetItem(self._short(old_v))
                o_item.setToolTip(old_v or t("common.em_dash"))
                n_item = QTableWidgetItem(self._short(new_v))
                n_item.setToolTip(new_v or t("common.em_dash"))
                n_item.setForeground(QColor(ACCENT_PRIMARY))
                table.setItem(r, 0, f_item)
                table.setItem(r, 1, o_item)
                table.setItem(r, 2, n_item)
            table.setSortingEnabled(True)
            table.fit_columns_to_content()
            self._version_body.addWidget(table)
            flush_widgets.append((table, "table"))

        # File changes
        def _fname(f: dict[str, Any]) -> str:
            path, name = (f.get("path") or "").strip(), (f.get("name") or "").strip()
            if path and name:
                return f"{path}/{name}"
            return name or path or t("detail.dataset_log.unnamed_file")

        from ui.icons import set_item_icon

        entries: list[tuple[str, str, str, str]] = []
        for f in diff.get("files_added") or []:
            entries.append(
                (
                    t("detail.version_log.file_added", file=_fname(f)),
                    "TEXT_SUCCESS",
                    "STATE_SUCCESS_GRAPHIC",
                    "plus",
                )
            )
        for f in diff.get("files_removed") or []:
            entries.append(
                (
                    t("detail.version_log.file_removed", file=_fname(f)),
                    "TEXT_DANGER",
                    "STATE_ERROR_GRAPHIC",
                    "minus",
                )
            )
        for pair in diff.get("files_replaced") or []:
            old_f, new_f = pair.get("old") or {}, pair.get("new") or {}
            entries.append(
                (
                    t(
                        "detail.version_log.file_replaced",
                        old=_fname(old_f),
                        new=_fname(new_f),
                    ),
                    "TEXT_AMBER",
                    "STATE_WARNING_GRAPHIC",
                    "arrow-right-left",
                )
            )
        for fc in diff.get("file_changes") or []:
            for ch in fc.get("changes") or []:
                entries.append(
                    (
                        t(
                            "detail.version_log.file_changed",
                            file=fc.get("file", ""),
                            field=ch.get("field", ""),
                        ),
                        "ACCENT_PRIMARY",
                        "ACCENT_PRIMARY",
                        "pencil",
                    )
                )
        if entries:
            flist = make_list(flush=True, last=True)
            flist.setMaximumHeight(min(140, 28 + 24 * len(entries)))
            for text, color, icon_color, icon_name in entries:
                item = QListWidgetItem(text)
                item.setToolTip(text)
                item.setForeground(QColor(colour(color)))
                try:
                    set_item_icon(item, icon_name, color=icon_color)
                except Exception:
                    pass
                flist.addItem(item)
            self._version_body.addWidget(flist)
            flush_widgets.append((flist, "list"))
        _apply_flush_corners()

    def _on_reset_version_view(self) -> None:
        try:
            from PySide6.QtWidgets import QTableWidget

            table = self._version_body.findChild(QTableWidget)
            if table is not None:
                self._reset_table_view("dataset_version", table.horizontalHeader())
            self._populate_version_diff()
        except Exception:
            pass
