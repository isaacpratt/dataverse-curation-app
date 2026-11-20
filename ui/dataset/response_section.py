"""The Response page: the findings list, the draft editor and the export."""

from pathlib import Path

from PySide6.QtCore import (
    Qt,
    QTimer,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui import dialogs
from ui.dataset.state import DetailState
from ui.i18n import t
from ui.theme import (
    FONT_BODY,
    TEXT_AMBER,
    TEXT_DANGER,
)
from ui.widgets import (
    add_info_tip,
    make_action_button,
    make_caption_label,
    make_card,
    make_list,
    make_multiline_input,
    make_small_body_label,
)


class ResponseSection(DetailState):
    """The Response page: the findings list, the draft editor and the export."""

    def _build_response_page(self) -> QWidget:
        # Scroll-wrapped so the page's own minimum stays small: the stacked
        # layout takes the max of all page minimums, and the editors below
        # (240 + 280 px) used to force the main window taller on first open.
        outer = QWidget()
        outer.setObjectName("DetailResponsePage")
        outer_lay = QVBoxLayout(outer)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer_lay.addWidget(scroll)
        page = QWidget()
        page.setObjectName("DetailResponseInner")
        scroll.setWidget(page)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 12, 24, 24)
        lay.setSpacing(12)

        intro = make_small_body_label(t("detail.response.intro"))
        lay.addWidget(intro)

        self._response_summary = QLabel(t("detail.response.load_to_build"))
        self._response_summary.setObjectName("StateMD")
        lay.addWidget(self._response_summary)
        # Moved off the old tab row: the response-specific nudge belongs on
        # the Response page, not next to global navigation.
        self._response_hint = QLabel("")
        self._response_hint.setWordWrap(True)
        self._response_hint.setObjectName("HintSM")
        lay.addWidget(self._response_hint)

        # Two columns: findings checklist (left) | editable draft (right).
        cols = QHBoxLayout()
        cols.setSpacing(12)

        findings_card, findings_body, _t, _h = make_card(t("detail.response.findings_card"))
        add_info_tip(
            _h,
            t("detail.response.findings_tip"),
            name=t("detail.response.findings_card"),
            group="Respond",
        )
        self._response_list = make_list()
        self._response_list.setMinimumHeight(240)
        self._response_list.itemChanged.connect(self._on_response_item_changed)
        findings_body.addWidget(self._response_list, 1)
        cols.addWidget(findings_card, 1)

        draft_card, draft_body, _t2, _h2 = make_card(t("detail.response.draft_card"))
        add_info_tip(
            _h2,
            t("detail.response.draft_tip"),
            name=t("detail.response.draft_a11y"),
            group="Respond",
        )
        self._response_edit = make_multiline_input(
            t("detail.response.draft_placeholder"),
            min_height=280,
            font_size=FONT_BODY,
        )
        self._response_edit.textChanged.connect(self._on_response_text_edited)
        draft_body.addWidget(self._response_edit, 1)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        # One primary, the rest ghost — equal-weight secondaries read as
        # three peers with no obvious next step (2026-10-02 minor).
        regen = make_action_button(t("detail.response.regenerate"), kind="ghost", size="sm")
        regen.setToolTip(t("detail.response.regenerate_tip"))
        regen.clicked.connect(lambda: self._refresh_response(force=True))
        btn_row.addWidget(regen)
        copy_btn = make_action_button(t("detail.response.copy"), kind="ghost", size="sm")
        copy_btn.clicked.connect(self._on_response_copy)
        btn_row.addWidget(copy_btn)
        export_btn = make_action_button(t("detail.response.export"), kind="primary", size="sm")
        export_btn.setToolTip(t("detail.response.export_tip"))
        export_btn.clicked.connect(self._on_response_export)
        btn_row.addWidget(export_btn)
        btn_row.addStretch(1)
        self._response_dirty_lbl = make_caption_label("", wrap=False)
        btn_row.addWidget(self._response_dirty_lbl)
        draft_body.addLayout(btn_row)
        cols.addWidget(draft_card, 2)

        lay.addLayout(cols, 1)

        self._sensitivity_card = self._build_sensitivity_card()
        lay.addWidget(self._sensitivity_card)

        # Assessment Action (moved from the review-page sidebar): the
        # response workflow reads left-to-right, top-to-bottom —
        # checklist → draft → decision — so the commit step lives here.
        self._assessment_card = self._build_assessment_card()
        lay.addWidget(self._assessment_card)
        lay.addStretch(1)
        return outer

    def _show_review_page(self) -> None:
        try:
            self._pages.setCurrentIndex(0)
            self._in_response = False
        except Exception:
            pass
        self._refresh_workflow()

    def _show_response_page(self) -> None:
        try:
            self._pages.setCurrentIndex(1)
            self._in_response = True
            self._refresh_response()
        except Exception:
            pass
        self._refresh_workflow()

    def _refresh_response(self, force: bool = False) -> None:  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
        """Rebuild findings + draft (skips overwriting manual edits unless forced)."""
        if getattr(self, "_response_loading", False):
            return
        try:
            from curation.response_draft import build_response
        except Exception:
            return
        if self._metadata is None:
            try:
                self._response_summary.setText(t("detail.response.load_to_build"))
            except Exception:
                pass
            return
        if self._response_dirty and not force:
            # Findings may have changed; keep the editor, nudge to regenerate.
            try:
                n = sum(1 for s in (self._response_sections or []) if s.get("included"))
                self._response_hint.setText(t("detail.response.findings_changed", count=n))
            except Exception:
                pass
            self._rebuild_findings_list(keep_checks=True)
            return
        try:
            ruleset = self._ruleset if isinstance(self._ruleset, dict) and self._ruleset else None
            if ruleset is None:
                from curation import review_rules as _rr

                try:
                    pool = _rr.load_rulesets()
                except Exception:
                    pool = {}
                key = "mcmaster-default"
                try:
                    from curation import metadata_check as _mc

                    key = _mc.PROFILE_TO_RULESET.get(self._profile, self._profile)
                    if key not in pool:
                        key = "mcmaster-default"
                except Exception:
                    pass
                ruleset = _rr.get_ruleset(key, pool)
                self._ruleset = ruleset
            md, sections = build_response(
                ruleset,
                self._completeness_full or [],
                self._report,
                self._title,
                self._pid,
                dispositions=self._dispositions_map(),
            )
            self._response_sections = sections
            self._rebuild_findings_list(keep_checks=False)
            self._response_loading = True
            try:
                self._response_edit.setPlainText(md)
            finally:
                self._response_loading = False
            self._response_dirty = False
            self._update_response_chrome()
            if force:
                # Explicit Regenerate discards manual edits — persist the new
                # draft so a reopen shows it. Automatic refreshes never
                # clobber a previously saved working draft on load.
                self._save_working_draft()
        except Exception:
            pass

    def _rebuild_findings_list(self, keep_checks: bool = False) -> None:
        from PySide6.QtWidgets import QListWidgetItem

        try:
            prev = {}
            if keep_checks:
                for i in range(self._response_list.count()):
                    item = self._response_list.item(i)
                    if item is not None:
                        prev[str(item.data(Qt.ItemDataRole.UserRole) or "")] = (
                            item.checkState() == Qt.CheckState.Checked
                        )
            self._response_list.blockSignals(True)
            self._response_list.clear()
            for s in self._response_sections or []:
                kind = (
                    t("detail.response.kind_metadata")
                    if s.get("kind") == "metadata"
                    else t("detail.response.kind_file_check")
                )
                # Severity raised in the label + colour: errors red,
                # warnings amber (file-check levels from the run, metadata
                # levels from the active ruleset).
                level = str(s.get("level") or "").lower()
                tag = {
                    "error": t("detail.response.level_error"),
                    "warning": t("detail.response.level_warning"),
                    "required": t("detail.response.level_required"),
                    "optional": t("detail.response.level_recommended"),
                }.get(level, level)
                label = t(
                    "detail.response.label_format",
                    kind=kind,
                    tag=t("detail.response.label_tag", tag=tag) if tag else "",
                    label=s.get("label", ""),
                )
                item = QListWidgetItem(label)
                if level == "error":
                    item.setForeground(QColor(TEXT_DANGER))
                elif level == "warning":
                    item.setForeground(QColor(TEXT_AMBER))
                item.setData(Qt.ItemDataRole.UserRole, str(s.get("id") or label))
                item.setToolTip(str(s.get("message") or "")[:400])
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                if keep_checks:
                    checked = prev.get(str(s.get("id") or label), bool(s.get("included")))
                else:
                    checked = bool(s.get("included"))
                s["included"] = checked
                item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
                self._response_list.addItem(item)
        except Exception:
            pass
        finally:
            try:
                self._response_list.blockSignals(False)
            except Exception:
                pass

    def _update_response_chrome(self) -> None:
        try:
            sections = [s for s in (self._response_sections or []) if s.get("included")]
            n = len(sections)
            total = len(self._response_sections or [])
            if total == 0:
                self._response_summary.setText(t("detail.response.no_outstanding"))
                self._response_hint.setText("")
            else:
                errors = sum(1 for s in sections if str(s.get("level") or "").lower() == "error")
                warns = sum(1 for s in sections if str(s.get("level") or "").lower() == "warning")
                severity = (
                    t(
                        "detail.response.severity",
                        warnings=warns,
                        errors=errors,
                    )
                    if warns or errors
                    else ""
                )
                self._response_summary.setText(
                    t(
                        "detail.response.included_count",
                        included=n,
                        total=total,
                        severity=severity,
                    )
                )
                self._response_hint.setText(
                    t("detail.response.in_draft", count=n)
                    if n
                    else t("detail.response.excludes_all")
                )
            self._response_dirty_lbl.setText(
                t("detail.response.edited") if self._response_dirty else ""
            )
        except Exception:
            pass

    def _on_response_item_changed(self, _item: QListWidgetItem | None) -> None:
        if getattr(self, "_response_loading", False):
            return
        try:
            states = {}
            for i in range(self._response_list.count()):
                item = self._response_list.item(i)
                if item is not None:
                    states[str(item.data(Qt.ItemDataRole.UserRole) or "")] = (
                        item.checkState() == Qt.CheckState.Checked
                    )
            for s in self._response_sections or []:
                sid = str(s.get("id") or "")
                if sid in states:
                    s["included"] = states[sid]
            from curation.response_draft import render_response

            md = render_response(
                self._ruleset or {}, self._response_sections or [], self._title, self._pid
            )
            self._response_loading = True
            try:
                self._response_edit.setPlainText(md)
            finally:
                self._response_loading = False
            self._response_dirty = False
            self._update_response_chrome()
            self._save_working_draft()
        except Exception:
            pass

    def _on_response_text_edited(self) -> None:
        if getattr(self, "_response_loading", False):
            return
        try:
            self._response_dirty = True
            self._update_response_chrome()
            # Debounced auto-save of the working draft (per-dataset).
            timer = getattr(self, "_response_save_timer", None)
            if timer is None:
                timer = QTimer(self)
                timer.setSingleShot(True)
                timer.setInterval(1500)
                timer.timeout.connect(self._save_working_draft)
                self._response_save_timer = timer
            timer.start()
        except Exception:
            pass

    def _save_working_draft(self) -> None:
        try:
            path = self._response_draft_path()
            text = self._response_edit.toPlainText() if hasattr(self, "_response_edit") else ""
            if path is None or not text.strip():
                return
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        except Exception:
            pass

    def _load_working_draft(self) -> bool:
        """Restore the saved per-dataset draft once (marks editor dirty)."""
        try:
            path = self._response_draft_path()
            if path is None or not path.exists():
                return False
            text = path.read_text(encoding="utf-8")
            if not text.strip():
                return False
            self._response_loading = True
            try:
                self._response_edit.setPlainText(text)
            finally:
                self._response_loading = False
            self._response_dirty = True
            self._update_response_chrome()
            return True
        except Exception:
            return False

    def _on_response_copy(self) -> None:
        try:
            from PySide6.QtWidgets import QApplication

            QApplication.clipboard().setText(self._response_edit.toPlainText())
            self._set_status(t("detail.status.response_copied"), tone="success")
        except Exception:
            pass

    def _on_response_export(self) -> None:

        text = ""
        try:
            text = self._response_edit.toPlainText()
        except Exception:
            pass
        if not text.strip():
            dialogs.show_warning(
                self,
                t("detail.header.response_tab"),
                t("detail.response.empty_export"),
            )
            return
        try:
            from PySide6.QtWidgets import QFileDialog

            try:
                self._dl_mgr.reports_dir(self._pid).mkdir(parents=True, exist_ok=True)
                start = str(self._dl_mgr.reports_dir(self._pid) / "depositor_response.md")
            except Exception:
                start = "depositor_response.md"
            path, _ = QFileDialog.getSaveFileName(
                self,
                t("detail.response.export_title"),
                start,
                t("detail.response.markdown_filter"),
                options=QFileDialog.Option.DontUseNativeDialog,
            )
        except Exception as exc:
            dialogs.show_critical(
                self,
                t("detail.header.response_tab"),
                t("detail.response.save_dialog_failed", exc=exc),
            )
            return
        if not path:
            return
        try:
            out = Path(path)
            if out.suffix.lower() != ".md":
                out = out.with_suffix(".md")
            out.write_text(text, encoding="utf-8")
        except Exception as exc:
            dialogs.show_critical(
                self,
                t("detail.header.response_tab"),
                t("detail.response.write_failed", exc=exc),
            )
            return
        self._save_working_draft()
        self._log_action(
            "response_exported",
            t("detail.status.response_saved_log", name=out.name),
            {"path": str(out)},
        )
        self._set_status(t("detail.status.response_saved", name=out.name), tone="success")

    def _response_draft_path(self) -> Path | None:
        try:
            return self._dl_mgr.dataset_dir(self._pid) / "response_draft.md"
        except Exception:
            return None

    def _staged_dir_or_none(self) -> Path | None:
        try:
            staged = self._dl_mgr.files_dir(self._pid)
            return staged if staged.exists() else None
        except Exception:
            return None

    def refresh_rules(self) -> None:
        """Reload rule profiles (after Review-config save) and re-evaluate."""
        try:
            from curation import metadata_check as _mc

            _mc.refresh_profiles_from_rulesets()
            combo = getattr(self, "_profile_combo", None)
            if combo is not None:
                current = self._profile
                combo.blockSignals(True)
                try:
                    combo.clear()
                    for key, info in _mc.PROFILES.items():
                        combo.addItem(info.get("label", key), key)
                    idx = combo.findData(current)
                    combo.setCurrentIndex(idx if idx >= 0 else 0)
                    self._profile = combo.currentData() or current
                finally:
                    combo.blockSignals(False)
            if self._metadata is not None:
                self._populate_completeness(self._metadata)
        except Exception:
            pass
