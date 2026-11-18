"""The Auto-Checks card: running the checks and reading the result tree."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QVBoxLayout,
    QWidget,
)

from curation.storage import (
    RESOLVED_DISPOSITIONS,
    finding_key,
)
from ui import dialogs
from ui.dataset.state import DetailState
from ui.i18n import t
from ui.theme import (
    ACCENT_PRIMARY,
    BORDER_SUBTLE,
    STATE_ERROR_BG,
    STATE_ERROR_BORDER,
    STATE_ERROR_GRAPHIC,
    STATE_ERROR_SURFACE,
    STATE_ERROR_TEXT,
    STATE_WARNING_GRAPHIC,
    SURFACE_ALT,
    SURFACE_SUBTLE,
    SURFACE_TINT,
    TEXT_MUTED,
    TEXT_ON_ACCENT,
    surface_frame_qss,
    transparent_surface_qss,
)
from ui.widgets import (
    add_info_tip,
    disposition_label,
    make_action_button,
    make_badge,
    make_caption_label,
    make_card,
    make_combo,
    make_disposition_combo,
    make_field_label,
    make_small_body_label,
)
from ui.workers import CheckWorker


class ChecksSection(DetailState):
    """The Auto-Checks card: running the checks and reading the result tree."""

    def _build_auto_checks_card(self) -> QFrame:
        card, _body_host, _title, header_lay = make_card(t("detail.sections.auto_checks"))
        add_info_tip(
            header_lay,
            t("detail.auto_checks.intro"),
            t("detail.auto_checks.legend"),
            name=t("detail.sections.auto_checks"),
            group="Checks",
        )
        # Named pre-run state, never "—" (2026-10-02 P2); refreshed to
        # "N check(s) will run"/counts/"No file checks" as data lands.
        self._auto_summary = make_field_label(t("detail.auto_checks.not_run"))
        header_lay.addWidget(self._auto_summary)
        # dv-bph (W2): a findings filter like the metadata card's, on its
        # own tools row — narrows the card to one severity per click.
        auto_tools = QWidget()
        auto_tools.setObjectName("AutoChecksTools")
        auto_tools.setStyleSheet(transparent_surface_qss("AutoChecksTools"))
        tools_lay = QHBoxLayout(auto_tools)
        tools_lay.setContentsMargins(16, 8, 16, 8)
        tools_lay.setSpacing(8)
        self._auto_filter = make_combo(
            [
                (t("detail.auto_checks.filter_all"), "all"),
                (t("detail.auto_checks.filter_errors"), "error"),
                (t("detail.auto_checks.filter_warnings"), "warning"),
            ],
            min_width=110,
            tip=t("detail.auto_checks.filter_tip"),
        )
        self._auto_filter.currentIndexChanged.connect(self._apply_auto_filter)
        tools_lay.addWidget(self._auto_filter)
        tools_lay.addStretch(1)
        card.layout().insertWidget(1, auto_tools)
        # Body: scroll of checks (factory body reused directly)
        self._auto_body = _body_host
        self._auto_body.setContentsMargins(16, 12, 16, 12)
        self._auto_body.setSpacing(8)
        # Placeholder
        self._auto_placeholder = make_small_body_label(t("detail.auto_checks.no_file_list"))
        self._auto_body.addWidget(self._auto_placeholder)
        return card

    def _auto_rows(self) -> list[QFrame]:
        """Return the Auto-Checks rows, in card order.

        ``self._auto_body`` is the card body's QVBoxLayout — a layout has
        no findChildren(), so the rows are read from the layout itself.
        """
        rows: list[QFrame] = []
        lay = getattr(self, "_auto_body", None)
        if lay is None:
            return rows
        for i in range(lay.count()):
            item = lay.itemAt(i)
            widget = item.widget() if item is not None else None
            if widget is not None and widget.objectName() == "AutoCheckRow":
                rows.append(widget)
        return rows

    def _apply_auto_filter(self, *_args) -> None:
        """Show only the rows of the chosen severity class (dv-bph, W2).

        Every row carries an ``auto_class`` property when it is built
        (``passed`` / ``failed-error`` / ``failed-warning`` / ``skipped``
        / ``planned``); the filter reads it and hides what does not
        match. "Warnings" keeps the skipped rows — they are warnings the
        curator still has to act on.
        """
        try:
            wanted = self._auto_filter.currentData() or "all"
        except Exception:
            wanted = "all"
        for row in self._auto_rows():
            cls = str(row.property("auto_class") or "passed")
            if wanted == "error":
                visible = cls == "failed-error"
            elif wanted == "warning":
                visible = cls in ("failed-warning", "skipped")
            else:  # "all"
                visible = True
            row.setVisible(visible)

    def _auto_row(
        self,
        title: str,
        desc: str,
        passed: bool,
        level: str,
        badge: str | None = None,
        disposition_key: str = "",
        detail_lines: list[tuple[str, bool]] | None = None,
    ) -> QFrame:
        frame = QFrame()
        # Scope the row face to the row itself. A bare `QFrame` selector
        # would also style every QLabel inside it (QLabel subclasses
        # QFrame), drawing a rounded box around each line of text.
        frame.setObjectName("AutoCheckRow")
        # Explicit SKIPPED (warning+passed with "Missing"/"skipped" wording)
        # renders grey so it is never confused with a real pass.
        from ui.icons import icon_label as _icon_label

        if (
            passed
            and level == "warning"
            and (
                (badge or "").upper() in ("SKIPPED", "MISSING")
                or "skipped" in (badge or desc).lower()
                or "not executed" in desc.lower()
                or "Missing" in (badge or desc)
            )
        ):
            frame.setStyleSheet(
                surface_frame_qss(SURFACE_SUBTLE, BORDER_SUBTLE, selector="QFrame#AutoCheckRow")
            )
            icon_name, icon_color = "circle-dashed", TEXT_MUTED
            badge_text = (
                t("status.badges.skipped")
                if "SKIP" in (badge or "").upper() or "skipped" in desc.lower()
                else (badge or t("status.badges.warning"))
            )
            badge_bg = SURFACE_ALT
            badge_fg = TEXT_MUTED
        elif not passed and level in ("error", "warning"):
            frame.setStyleSheet(
                surface_frame_qss(
                    STATE_ERROR_BG, STATE_ERROR_BORDER, selector="QFrame#AutoCheckRow"
                )
            )
            icon_name, icon_color = (
                ("octagon-x", STATE_ERROR_GRAPHIC)
                if level == "error"
                else ("octagon-alert", STATE_WARNING_GRAPHIC)
            )
            badge_text = badge or t("status.badges.error")
            badge_bg = STATE_ERROR_BG
            badge_fg = STATE_ERROR_TEXT
        elif passed and level == "warning" and "Missing" in (badge or desc):
            frame.setStyleSheet(
                surface_frame_qss(
                    STATE_ERROR_SURFACE, STATE_ERROR_BORDER, selector="QFrame#AutoCheckRow"
                )
            )
            icon_name, icon_color = "octagon-alert", STATE_WARNING_GRAPHIC
            badge_text = badge or t("status.badges.warning")
            badge_bg = STATE_ERROR_BG
            badge_fg = STATE_ERROR_TEXT
        elif passed:
            frame.setStyleSheet(
                surface_frame_qss(SURFACE_TINT, BORDER_SUBTLE, selector="QFrame#AutoCheckRow")
            )
            icon_name, icon_color = "check", ACCENT_PRIMARY
            badge_text = badge or t("status.badges.passed")
            badge_bg = ACCENT_PRIMARY
            badge_fg = TEXT_ON_ACCENT
        else:
            frame.setStyleSheet(
                surface_frame_qss(SURFACE_TINT, BORDER_SUBTLE, selector="QFrame#AutoCheckRow")
            )
            icon_name, icon_color = "minus", TEXT_MUTED
            badge_text = badge or t("common.em_dash")
            badge_bg = SURFACE_ALT
            badge_fg = TEXT_MUTED
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(8)
        lay.addWidget(_icon_label(icon_name, size=16, color=icon_color))
        txt = QVBoxLayout()
        txt.setSpacing(1)
        cid = QLabel(title)
        cid.setObjectName("LabelStrongSM")
        txt.addWidget(cid)
        d = make_caption_label(desc)
        txt.addWidget(d)
        # Per-section checklist (dv-81q): the README depth row lists every
        # standard section with a found/missing mark under its message.
        for label, found in detail_lines or []:
            txt.addWidget(
                make_caption_label(
                    t(
                        "detail.auto_checks.readme_section_found"
                        if found
                        else "detail.auto_checks.readme_section_missing",
                        label=label,
                    )
                )
            )
        lay.addLayout(txt, 1)
        # Inline disposition controls for findings (dv-32x): the combo
        # writes through _on_disposition_changed; Note… edits the stored
        # note (tooltip carries it once one exists).
        if disposition_key:
            current = self._dispositions_map().get(disposition_key, {})
            token = str(current.get("disposition") or "")
            note = str(current.get("note") or "")
            combo = make_disposition_combo(
                token,
                on_change=lambda tok, k=disposition_key: self._on_disposition_changed(k, tok),
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
        badge_lbl = make_badge(
            badge_text,
            background=badge_bg,
            foreground=badge_fg,
            border=BORDER_SUBTLE,
        )
        badge_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge_lbl.setFixedHeight(20)
        badge_lbl.setMinimumWidth(56)
        lay.addWidget(badge_lbl)
        lay.addWidget(
            self._finding_overflow_button(
                t("detail.auto_checks.file_result_format", path=title, message=desc)
            )
        )
        return frame

    def _cached_report_path(self) -> Path:
        """Return the fixed cache path inside the dataset's curation workspace folder."""
        return self._dl_mgr.dataset_dir(self._pid) / "checks-report.json"

    def _load_cached_report(self):
        """Last auto-saved checks report for this dataset, or None."""
        try:
            path = self._cached_report_path()
            if path.is_file():
                from engine.report import DatasetReport

                return DatasetReport.load(path)
        except Exception:
            pass
        return None

    def _on_run_checks(self) -> None:
        staged = self._dl_mgr.files_dir(self._pid)
        if not staged.exists():
            dialogs.show_warning(
                self,
                t("detail.checks.title"),
                t("detail.checks.download_first"),
            )
            self._check_btn.setEnabled(True)
            return
        self._check_btn.setEnabled(False)
        self._checks_cancel_btn.setVisible(True)
        self._set_status(t("detail.status.running_checks"))
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)
        self._check_worker = CheckWorker(
            staged,
            self._pid,
            self._title,
            inventory=self._inventory if isinstance(self._inventory, list) else None,
            metadata=self._metadata if isinstance(self._metadata, dict) else None,
            client=self._client,
            ruleset=self._ruleset if isinstance(self._ruleset, dict) else None,
            parent=self,
        )
        self._check_worker.progress.connect(lambda msg: self._set_status(msg))
        self._check_worker.progressFraction.connect(self._on_ring_fraction)
        self._check_worker.finished.connect(self._on_checks_finished)
        self._check_worker.error.connect(self._on_checks_error)
        self._check_worker.cancelled.connect(self._on_checks_cancelled)
        self._check_worker.finished.connect(self._check_worker.deleteLater)
        self._check_worker.error.connect(self._check_worker.deleteLater)
        self._check_worker.cancelled.connect(self._check_worker.deleteLater)
        self._check_worker.start()

    def _on_cancel_checks_click(self) -> None:
        """Ask the running check pass to stop at the next checkpoint."""
        worker = self._check_worker
        if worker is None:
            return
        try:
            worker.cancel()
        except Exception:
            try:
                worker.requestInterruption()
            except Exception:
                pass
        self._set_status(t("detail.status.cancelling"))
        self._checks_cancel_btn.setEnabled(False)

    def _on_checks_cancelled(self) -> None:
        """Reset the header after a cancelled check pass (no report)."""
        self._progress.setVisible(False)
        self._hide_ring()
        self._check_btn.setEnabled(True)
        self._checks_cancel_btn.setVisible(False)
        self._checks_cancel_btn.setEnabled(True)
        self._set_status(t("detail.status.checks_cancelled"))

    def _on_checks_finished(self, report) -> None:
        from engine.status import summarize

        self._check_worker = None
        self._report = report
        # Auto-cache: always save the JSON report into the dataset's
        # workspace folder (no dialog) so checks survive re-opening the
        # dataset and stay available for the next session.
        cache_path = None
        try:
            cache_path = self._cached_report_path()
            report.save(cache_path)
        except Exception:
            cache_path = None
        self._progress.setVisible(False)
        self._hide_ring()
        self._check_btn.setEnabled(True)
        self._checks_cancel_btn.setVisible(False)
        self._checks_cancel_btn.setEnabled(True)
        self._history_btn.setEnabled(True)
        # Update dataset-checks card + manifest tree
        self._refresh_curation_preview()
        self._apply_file_filter_internal()
        # Sensitivity suggestions can now use real PII/access findings.
        self._refresh_sensitivity_card()
        all_results = list(report.dataset_checks) + [c for f in report.files for c in f.checks]
        summary = summarize(all_results)
        findings = summary["failed"]
        self._set_status(
            t(
                "detail.status.checks_complete",
                findings=findings,
                errors=summary["failed-error"],
                warnings=summary["failed-warning"],
                skipped=summary["skipped"],
                files=len(report.files),
            )
            + " "
            + (
                t("detail.status.report_auto_saved", name=cache_path.parent.name)
                if cache_path is not None
                else t("detail.status.report_auto_save_failed")
            )
            + t("detail.status.use_export_for_markdown"),
            tone="success",
        )
        self._log_action(
            "checks_run",
            t(
                "detail.status.report_summary",
                findings=findings,
                files=len(report.files),
            ),
            {"findings": findings, "files": len(report.files)},
        )
        if cache_path is not None:
            try:
                self._log_action(
                    "checks_saved",
                    t(
                        "detail.status.auto_saved_to",
                        folder=cache_path.parent.name,
                        name=cache_path.name,
                    ),
                    {"path": str(cache_path)},
                )
            except Exception:
                pass
        # File-check findings feed the Response draft — rebuild it.
        try:
            self._refresh_response()
        except Exception:
            pass
        self._refresh_workflow()

    def _on_checks_error(self, msg: str) -> None:
        self._check_worker = None
        self._progress.setVisible(False)
        self._hide_ring()
        self._check_btn.setEnabled(True)
        self._checks_cancel_btn.setVisible(False)
        self._checks_cancel_btn.setEnabled(True)
        headline, details = dialogs.describe_error(msg)
        # The failure stays on the page: an empty status strip read as
        # "nothing happened" once the dialog was closed. The strip now
        # carries the reason and stays until the next run replaces it.
        self._set_status(t("detail.status.checks_failed", reason=headline), tone="error")
        dialogs.show_critical(
            self, t("detail.checks.title"), headline, details=details, retry=self._on_run_checks
        )

    def _on_tree_clicked(self, index) -> None:
        try:
            from ui.checks_tree import node_kind
        except Exception:
            return
        info = node_kind(index)
        kind = info.get("kind", "")
        if kind == "check":
            if not self._report:
                return
            path = info.get("path", "")
            check_id = info.get("check_id", "")
            entry = next((f for f in self._report.files if f.path == path), None)
            if not entry:
                return
            result = next((c for c in entry.checks if c.check_id == check_id), None)
            if result is None:
                return
            import json as _json

            try:
                details = _json.dumps(result.details or {}, indent=1)[:1500]
            except Exception:
                details = str(result.details)[:1500]
            self._set_status(
                t(
                    "detail.checks.result_detail",
                    path=path,
                    level=result.level,
                    check_id=result.check_id,
                    message=result.message,
                    details=details,
                )
            )
        elif kind == "file":
            path = info.get("path", "")
            # In-app preview (dv-koz): set it even without a report.
            try:
                self._show_preview_for_file(path)
            except Exception:
                pass
            if not self._report:
                return
            entry = next((f for f in self._report.files if f.path == path), None)
            if not entry:
                self._set_status(t("detail.status.path_not_in_report", path=path))
            elif not entry.checks:
                self._set_status(t("detail.status.path_no_check", path=path))
            else:
                from engine.status import summarize

                summary = summarize(entry.checks)
                self._set_status(
                    t(
                        "detail.status.path_summary",
                        path=path,
                        passed=summary["passed"],
                        warnings=summary["failed-warning"],
                        errors=summary["failed-error"],
                        skipped=summary["skipped"],
                    )
                )
        else:
            return

    def _build_copy_menu(self, text: str):
        """Build the one-item copy menu for a finding row (dv-18z)."""
        from PySide6.QtWidgets import QApplication, QMenu

        menu = QMenu(self)
        action = menu.addAction(t("detail.copy_finding.action"))

        def _copy():
            QApplication.clipboard().setText(text)
            try:
                self._set_status(t("detail.copy_finding.copied"), tone="success")
            except Exception:
                pass

        action.triggered.connect(_copy)
        return menu

    def _show_copy_menu(self, btn, text: str) -> None:
        self._build_copy_menu(text).exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _finding_overflow_button(self, text: str):
        """⋯ ghost button opening the copy-this-finding menu (dv-18z).

        One item, one job: copy a single line a curator can paste into a
        comment or the depositor letter. No state, no log entry.
        """
        btn = make_action_button("⋯", kind="ghost", size="sm")
        btn.setToolTip(t("detail.copy_finding.action"))
        btn.setAccessibleName(t("detail.copy_finding.action"))
        btn.clicked.connect(lambda _c=False, b=btn, s=text: self._show_copy_menu(b, s))
        return btn

    def _dispositions_map(self) -> dict:
        """{finding_key: {disposition, note}} for this dataset (cached)."""
        cached = getattr(self, "_dispositions_cache", None)
        if isinstance(cached, dict):
            return cached
        out: dict = {}
        try:
            st = self._state()
            if st is not None:
                out = st.list_finding_dispositions(self._pid)
        except Exception:
            out = {}
        self._dispositions_cache = out
        return out

    def _set_disposition(self, key: str, token: str, note: str = "", refresh: bool = False) -> None:
        """Persist one disposition, update the cache, the log, and views."""
        try:
            st = self._state()
            if st is not None:
                st.set_finding_disposition(self._pid, key, token, note or "")
        except Exception:
            return
        cache = getattr(self, "_dispositions_cache", None)
        if isinstance(cache, dict):
            if token:
                cache[key] = {"disposition": token, "note": note or "", "updated_at": ""}
            else:
                cache.pop(key, None)
        self._refresh_finding_summary()
        self._refresh_workflow()
        self._log_action(
            "disposition",
            (disposition_label(token) if token else t("detail.disposition.cleared"))
            + (t("detail.dataset_log.action_notes", notes=(note or "")[:120]) if note else ""),
            {"finding_key": key, "disposition": token},
        )
        if refresh:
            # Reflection surfaces: manifest tint + response exclusion.
            try:
                self._apply_file_filter_internal()
            except Exception:
                pass
            try:
                self._refresh_response(force=False)
            except Exception:
                pass

    def _on_disposition_changed(self, key: str, token: str) -> None:
        """Combo change on an Auto-Checks row: keep the existing note."""
        current = self._dispositions_map().get(key, {})
        self._set_disposition(key, str(token or ""), str(current.get("note") or ""), refresh=True)

    def _on_edit_disposition_note(self, key: str, token: str = "") -> None:
        """Edit (or add) the note stored with one finding's disposition."""
        current = self._dispositions_map().get(key, {})
        existing = str(current.get("note") or "")
        if not token:
            token = str(current.get("disposition") or "")
        if not token:
            # A note implies the curator engaged with the finding; the
            # mildest honest token is acknowledged. (storage issues a DELETE
            # for an empty token, which would silently drop the note.)
            token = "acknowledged"
        text, ok = QInputDialog.getMultiLineText(
            self,
            t("detail.disposition.note_title"),
            t("detail.disposition.note_label"),
            existing,
        )
        if ok:
            self._set_disposition(key, token, text, refresh=True)

    def _show_disposition_menu(self, key: str, global_pos) -> None:
        """Right-click menu for one finding: mark, note, or clear."""
        current = str(self._dispositions_map().get(key, {}).get("disposition") or "")
        menu = QMenu(self)
        for token in ("acknowledged", "fix-requested", "wontfix", "blocked"):
            action = menu.addAction(disposition_label(token))
            action.setCheckable(True)
            action.setChecked(token == current)
            action.triggered.connect(
                lambda _c=False, tok=token: self._set_disposition(key, tok, refresh=True)
            )
        menu.addSeparator()
        note_action = menu.addAction(t("detail.disposition.note_action"))
        note_action.triggered.connect(lambda: self._on_edit_disposition_note(key, current))
        clear_action = menu.addAction(t("detail.disposition.clear"))
        clear_action.triggered.connect(lambda: self._set_disposition(key, "", refresh=True))
        menu.exec(global_pos)

    def _on_file_context_menu(self, pos) -> None:
        """Disposition menu for one check node in the file manifest tree."""
        tree = self._file_tree
        index = tree.indexAt(pos)
        if not index.isValid():
            return
        model = tree.model()
        item = None
        if model is not None:
            from PySide6.QtGui import QStandardItemModel

            if isinstance(model, QStandardItemModel):
                item = model.itemFromIndex(index.siblingAtColumn(0))
        data = item.data(Qt.ItemDataRole.UserRole + 1) if item is not None else None
        if not isinstance(data, dict) or data.get("kind") != "check":
            return
        key = finding_key(
            str(data.get("check_id") or ""),
            str(data.get("path") or ""),
            str(data.get("msg") or ""),
        )
        self._show_disposition_menu(key, tree.viewport().mapToGlobal(pos))

    def _set_auto_summary(self, text: str) -> None:
        """Set the Auto-Checks header text, re-applying the roll-up suffix."""
        self._auto_summary_base = text
        self._auto_summary.setText(text + self._disposition_suffix())

    def _disposition_suffix(self) -> str:
        keys = getattr(self, "_finding_keys", [])
        if not keys:
            return ""
        disp = self._dispositions_map()
        tokens = [str(disp.get(k, {}).get("disposition") or "") for k in keys]
        resolved = sum(1 for tok in tokens if tok in RESOLVED_DISPOSITIONS)
        return t("detail.disposition.summary_suffix", resolved=resolved, total=len(tokens))

    def _refresh_finding_summary(self) -> None:
        base = getattr(self, "_auto_summary_base", None)
        if base is None:
            return
        self._auto_summary.setText(base + self._disposition_suffix())
