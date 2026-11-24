"""The Assessment action: the decision state, the commit, the download and the export."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QWidget,
)

from curation.download_manager import DownloadManager
from curation.sensitivity import (
    QUESTIONS,
    answered_count,
    is_complete,
    ruleset_requires,
    suggested_answers,
)
from ui import dialogs
from ui.dataset.state import DetailState
from ui.download_dialog import DownloadApprovalDialog
from ui.i18n import t
from ui.theme import (
    ACTIVE_THEME,
    BORDER_SUBTLE,
    FONT_SMALL,
    STATE_WARNING_GRAPHIC,
    SURFACE_SUBTLE,
    SURFACE_TINT,
    TEXT_AMBER,
    TEXT_MUTED,
    TEXT_SUCCESS,
    surface_frame_qss,
)
from ui.widgets import (
    add_info_tip,
    make_action_button,
    make_caption_label,
    make_card,
    make_combo,
    make_field_label,
    make_multiline_input,
    make_small_body_label,
)
from ui.workers import DownloadWorker


class ActionsSection(DetailState):
    """The Assessment action: the decision state, the commit, the download and the export."""

    def _build_assessment_card(self) -> QFrame:
        card, body, _title, _header = make_card(t("detail.sections.assessment_action"))
        add_info_tip(
            _header,
            t("detail.assessment.tip"),
            name=t("detail.sections.assessment_action"),
            group="Respond",
        )
        body.setContentsMargins(16, 16, 16, 16)
        body.setSpacing(12)
        # Internal Notes
        lbl = make_field_label(t("detail.assessment.notes_label"))
        body.addWidget(lbl)
        self._notes_edit = make_multiline_input(
            t("detail.assessment.notes_placeholder"),
            height=110,
            font_size=FONT_SMALL,
        )
        body.addWidget(self._notes_edit)
        # Decision State
        lbl2 = make_field_label(t("detail.assessment.decision_label"))
        body.addWidget(lbl2)
        self._decision_combo = make_combo(
            tip=t("detail.assessment.decision_tip"),
        )
        self._refresh_decision_options()
        body.addWidget(self._decision_combo)
        # One-line consequence helper: names what recording the choice will
        # actually do BEFORE the commit, and Commit stays disabled while the
        # combo sits on the non-answer placeholder (2026-10-02 P3 — the
        # widest decision point had neither).
        self._decision_help = make_caption_label("")
        body.addWidget(self._decision_help)
        # Commit button row
        row = QHBoxLayout()
        row.addStretch()
        commit = make_action_button(t("detail.assessment.commit"), kind="primary", size="md")
        commit.setToolTip(t("detail.assessment.commit_tip"))
        commit.setAccessibleName(t("detail.assessment.commit"))
        commit.clicked.connect(self._on_commit)
        self._commit_btn = commit
        row.addWidget(commit)
        body.addLayout(row)
        # Widgets exist now: gate + helper follow the restored choice, and
        # every later combo change re-syncs them.
        self._decision_combo.currentIndexChanged.connect(self._sync_decision_state)
        self._sync_decision_state()
        return card

    def _decision_choices(self) -> tuple[list[str], bool]:
        """(options, from_labels): instance curation labels when known."""
        try:
            allowed = [
                str(lbl).strip()
                for lbl in ((self._curation or {}).get("allowed") or [])
                if str(lbl).strip()
            ]
        except Exception:
            allowed = []
        if allowed:
            seen: list[str] = []
            for label in allowed:
                if label not in seen:
                    seen.append(label)
            return seen, True
        return [
            t("detail.decision.option_approve"),
            t("detail.decision.option_revisions"),
            t("detail.decision.option_reject"),
            t("detail.decision.option_hold"),
        ], False

    def _refresh_decision_options(self) -> None:
        try:
            current = self._decision_combo.currentText()
        except Exception:
            current = ""
        try:
            self._decision_combo.blockSignals(True)
            self._decision_combo.clear()
            options, from_labels = self._decision_choices()
            self._decision_combo.addItem(t("detail.decision.placeholder"), None)
            for opt in options:
                self._decision_combo.addItem(opt, opt)
            idx = self._decision_combo.findText(current)
            self._decision_combo.setCurrentIndex(idx if idx > 0 else 0)
            tip = (
                t("detail.decision.instance_labels_tip")
                if from_labels
                else t("detail.decision.generic_states_tip")
            )
            self._decision_combo.setToolTip(tip)
        finally:
            try:
                self._decision_combo.blockSignals(False)
            except Exception:
                pass
            # Rebuilt list → helper line + commit gate follow the restored
            # choice (no-op before the widgets exist at build time).
            self._sync_decision_state()

    def _decision_consequence(self, choice: str, from_labels: bool) -> str:
        """One line naming what recording this choice actually does.

        The four generic states get real consequence copy; instance curation
        labels (arbitrary server strings) fall back to the shared mechanics
        (dataset log + Dataverse label), so the line never overpromises.
        """
        known = {
            t("detail.decision.option_approve"): t("detail.decision.consequence_approve"),
            t("detail.decision.option_revisions"): t("detail.decision.consequence_revisions"),
            t("detail.decision.option_reject"): t("detail.decision.consequence_reject"),
            t("detail.decision.option_hold"): t("detail.decision.consequence_hold"),
        }
        text = known.get(
            choice,
            t("detail.decision.consequence_generic", choice=choice),
        )
        if from_labels:
            text += t("detail.decision.also_set_label")
        return text

    def _sync_decision_state(self, *_ignored: object) -> None:
        """Gate Commit + refresh the helper line for the current choice.

        Commit is disabled while the combo sits on the "Select decision…"
        non-answer, so the decision can't be skipped past silently — the
        placeholder itself explains why (2026-10-02 P3).
        """
        try:
            choice = self._decision_combo.currentData()
            choice = choice if isinstance(choice, str) and choice else ""
            help_lbl = getattr(self, "_decision_help", None)
            if help_lbl is not None:
                if choice:
                    _options, from_labels = self._decision_choices()
                    help_lbl.setText(self._decision_consequence(choice, from_labels))
                else:
                    help_lbl.setText(t("detail.decision.pick_action"))
            commit = getattr(self, "_commit_btn", None)
            if commit is not None:
                commit.setEnabled(bool(choice))
        except Exception:
            pass

    def _confirm_remote_write(self, decision: str) -> bool:
        """Ask before writing the decision to Dataverse. Defaults to No.

        A decision drawn from the instance's curation labels is not a
        local note: it changes the dataset on the server, for everyone.
        The curator confirms that explicitly before anything is written
        or logged.
        """
        try:
            return dialogs.confirm(
                self,
                t("detail.decision.confirm_remote_title"),
                t(
                    "detail.decision.confirm_remote_body",
                    decision=decision,
                    pid=self._pid,
                ),
                confirm_label=t("detail.decision.confirm_remote_yes"),
            )
        except Exception:
            return False

    def _on_commit(self) -> None:
        decision = self._decision_combo.currentData()
        if not isinstance(decision, str) or not decision:
            dialogs.show_warning(
                self,
                t("detail.decision.title"),
                t("detail.decision.select_state"),
            )
            return
        _options, from_labels = self._decision_choices()
        # Sensitivity gate (dv-3c2): a collection whose ruleset requires
        # the review must complete it before an Approve decision commits.
        if decision == t("detail.decision.option_approve"):
            blocked, gate_msg = self._sensitivity_blocks()
            if blocked:
                dialogs.show_warning(self, t("detail.sensitivity.gate_title"), gate_msg)
                return
        # The gate: a remote write asks first, and the answer decides
        # whether anything at all happens - no log entry, no workflow
        # step, no push.
        if from_labels and not self._confirm_remote_write(decision):
            return
        notes = self._notes_edit.toPlainText().strip()
        msg = t("detail.decision.decision_prefix", decision=decision)
        if notes:
            msg += t("detail.decision.notes", notes=notes)
        if self._report is not None:
            msg += t(
                "detail.decision.report_findings",
                count=len(self._report.files),
            )
        self._log_action(
            "decision",
            f"{decision}" + (t("detail.decision.log_notes", notes=notes[:200]) if notes else ""),
            {"decision": decision, "notes": notes[:2000]},
        )
        # Depositor follow-up (dv-5eg): a revisions decision opens one;
        # any other decision closes it.
        self._sync_follow_up(decision)
        # A recorded decision closes the last workflow step (the Dataverse
        # push may still fail; that is surfaced by the dialog below).
        self._decision_committed = True
        self._refresh_workflow()
        pushed = False
        push_error = ""
        if from_labels:
            # The decision IS a Dataverse curation label — assign it there too.
            try:
                pushed = bool(self._client.set_curation_label(self._pid, decision))
                if pushed:
                    self._curation["label"] = decision
                    try:
                        self._update_curation_pill()
                    except Exception:
                        pass
                else:
                    push_error = t("detail.decision.label_rejected")
            except Exception as exc:
                push_error = str(exc)[:200]
        if from_labels and not pushed:
            dialogs.show_warning(
                self,
                t("detail.decision.committed_local_only"),
                msg
                + "\n\n"
                + (push_error or t("detail.decision.label_not_set"))
                + t("detail.decision.recorded_in_log"),
            )
        else:
            tail = (
                t("detail.decision.label_set_and_logged")
                if pushed
                else t("detail.decision.recorded_in_log_para")
            )
            dialogs.show_info(self, t("detail.decision.committed"), msg + tail)

    def _on_download(self) -> None:
        try:
            inventory = self._dl_mgr.inventory(self._pid)
        except Exception as exc:
            dialogs.show_warning(
                self,
                t("detail.download.title"),
                t("detail.download.inventory_failed", exc=exc),
            )
            return
        quote = DownloadManager.quote_from(inventory, self._pid)
        # Skip the bundle entirely when everything is already staged.
        try:
            missing = self._dl_mgr.missing_files(self._pid, inventory)
        except Exception:
            missing = [t("detail.download.inventory_check_failed")]
        if inventory and not missing:
            _ok, problems, warnings = self._dl_mgr.verify(self._pid)
            self._refresh_files_placeholder()
            self._check_btn.setEnabled(True)
            self._check_btn.setToolTip(t("detail.header.run_checks_tip_staged"))
            self._set_status(
                t("detail.download.all_verified_skip", count=len(inventory)),
                tone="success",
            )
            self._log_action(
                "downloaded",
                t("detail.download.already_staged", count=len(inventory)),
                {"skipped": True},
            )
            if problems or warnings:
                dialogs.show_warning(
                    self,
                    t("detail.download.title"),
                    t(
                        "detail.download.staged_notes",
                        notes="\n".join((problems + warnings)[:10]),
                    ),
                )
            else:
                dialogs.show_info(
                    self,
                    t("detail.download.title"),
                    t("detail.download.all_verified_nothing", count=len(inventory)),
                )
            return
        # A guestbook must be answered inside the approval window. It is
        # normally preloaded with the metadata; fall back to one small GET
        # when this view came from cached metadata or a stale record.
        guestbook = self._guestbook
        if not (isinstance(guestbook, dict) and guestbook.get("id")):
            guestbook = None
            gb_id = self._metadata.get("guestbookId") if isinstance(self._metadata, dict) else None
            if gb_id:
                try:
                    guestbook = self._client.get_guestbook(gb_id)
                    self._guestbook = guestbook
                    if not self._account:
                        self._account = self._client.get_current_user()
                except Exception as exc:
                    dialogs.show_warning(
                        self,
                        t("detail.download.title"),
                        t("detail.download.guestbook_failed", exc=exc),
                    )
                    return
        if isinstance(guestbook, dict) and guestbook.get("enabled") is False:
            guestbook = None
        dlg = DownloadApprovalDialog(quote, self, guestbook=guestbook, account=self._account)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        guestbook_response = dlg.guestbook_response() if guestbook else None
        self._dl_btn.setEnabled(False)
        self._set_status(t("detail.download.downloading"))
        # Progress belongs to the status widget now (dv-gfx.3): the widget
        # starts on the first fraction signal, and the byte counter rides
        # in its detail slot.
        self._dl_worker = DownloadWorker(
            self._client,
            self._config.app.workspace,
            self._pid,
            self,
            guestbook_response=guestbook_response,
        )
        # Progress fraction goes to the status chip (dv-3d0.4).
        self._dl_worker.progressFraction.connect(
            lambda f: self._show_status_running(
                t("detail.statuswidget.downloading"), self._status_context(), f
            )
        )
        self._dl_worker.finished.connect(self._on_download_finished)
        self._dl_worker.error.connect(self._on_download_error)
        self._dl_worker.cancelled.connect(self._on_download_cancelled)
        self._dl_worker.finished.connect(self._dl_worker.deleteLater)
        self._dl_worker.error.connect(self._dl_worker.deleteLater)
        self._dl_worker.cancelled.connect(self._dl_worker.deleteLater)
        self._dl_cancel_btn.setEnabled(True)
        self._dl_cancel_btn.setVisible(True)
        self._dl_worker.start()

    def _on_download_finished(self, staged: Path) -> None:
        self._dl_worker = None
        self._dl_btn.setEnabled(True)
        ok, problems, warnings = self._dl_mgr.verify(self._pid)
        if problems:
            dialogs.show_warning(
                self,
                t("detail.download.title"),
                t("detail.download.checksum_problems", problems="\n".join(problems[:10])),
            )
        elif warnings:
            dialogs.show_info(
                self,
                t("detail.download.title"),
                t("detail.download.downloaded_notes", notes="\n".join(warnings[:10])),
            )
        self._refresh_files_placeholder()
        # Belt-and-braces: staged files exist now, so checks are available.
        self._check_btn.setEnabled(self._dl_mgr.files_dir(self._pid).exists())
        self._check_btn.setToolTip(t("detail.header.run_checks_tip_staged"))
        self._set_status(t("detail.status.downloaded_to", path=staged), tone="success")
        self._show_status_complete(
            t("detail.header.verify_files"),
            t("detail.status.inventory_count", count=int(getattr(self, "_staged_total", 0) or 0)),
        )
        self._log_action(
            "downloaded",
            t("detail.status.staged_to", path=staged),
            {"staged": str(staged), "ok": ok},
        )
        # Staged content may resolve file-content text rules — re-evaluate.
        try:
            if self._metadata is not None:
                self._populate_completeness(self._metadata)
        except Exception:
            pass
        # A primary-button press with nothing staged becomes a download; once
        # the staged set is ready, continue straight into the check pass.
        if getattr(self, "_run_after_download", False):
            self._run_after_download = False
            self._start_checks()

    def _on_download_error(self, msg: str) -> None:
        self._run_after_download = False
        self._dl_worker = None
        self._dl_btn.setEnabled(True)
        self._set_status("")
        headline, details = dialogs.describe_error(msg)
        self._show_status_error(t("detail.statuswidget.error"), headline)
        dialogs.show_critical(
            self, t("detail.download.title"), headline, details=details, retry=self._on_download
        )

    def _on_download_cancel_click(self) -> None:
        """Ask the worker to stop; stay disabled until it acknowledges."""
        if self._dl_worker is None:
            return
        self._dl_cancel_btn.setEnabled(False)
        self._set_status(t("detail.status.cancelling"))
        widget = getattr(self, "_status_widget", None)
        if widget is not None and widget.isVisible():
            widget.set_running(t("detail.statuswidget.cancelling"), "", None, cancelling=True)
        try:
            self._dl_worker.cancel()
        except Exception:
            pass

    def _on_download_cancelled(self) -> None:
        """Worker acknowledged the cancel: reset the action row quietly."""
        self._run_after_download = False
        self._dl_worker = None
        self._dl_btn.setEnabled(True)
        self._dl_cancel_btn.setEnabled(True)
        self._dl_cancel_btn.setVisible(False)
        self._refresh_files_placeholder()
        # Staged files (bundle extract or finished originals) stay valid.
        self._check_btn.setEnabled(self._dl_mgr.files_dir(self._pid).exists())
        self._set_status(t("detail.status.download_cancelled"))
        self._log_action("downloaded", t("detail.download.cancelled_by_user"), {"cancelled": True})

    def _on_export(self) -> None:
        if not self._report:
            dialogs.show_warning(
                self,
                t("detail.export.title"),
                t("detail.export.run_checks_first"),
            )
            return
        from PySide6.QtWidgets import QFileDialog

        try:
            self._dl_mgr.reports_dir(self._pid).mkdir(parents=True, exist_ok=True)
            start_dir = str(
                self._dl_mgr.reports_dir(self._pid)
                / f"{self._pid.replace(':', '_').replace('/', '_')}_report.md"
            )
        except Exception:
            start_dir = f"{self._pid.replace(':', '_').replace('/', '_')}_report.md"
        try:
            path, _ = QFileDialog.getSaveFileName(
                self,
                t("detail.export.reports_title"),
                start_dir,
                t("detail.export.markdown_filter"),
                options=QFileDialog.Option.DontUseNativeDialog,
            )
        except Exception as exc:
            dialogs.show_critical(
                self,
                t("detail.export.title"),
                t("detail.export.save_dialog_failed", exc=exc),
            )
            return
        if not path:
            return
        try:
            md_path = Path(path)
            if md_path.suffix.lower() != ".md":
                md_path = md_path.with_suffix(".md")
            json_path = md_path.with_suffix(".json")
            self._report.save_markdown(md_path)
            self._report.save(json_path)
        except Exception as exc:
            dialogs.show_critical(
                self,
                t("detail.export.title"),
                t("detail.export.write_failed", exc=exc),
            )
            return
        # Success needs no modal — the status line + Dataset log record it.
        # Modals are reserved for failures (above).
        self._last_export_path = str(json_path)
        self._log_action(
            "exported",
            t("detail.export.saved_log", markdown=md_path, json=json_path),
            {"path": str(json_path), "markdown": str(md_path)},
        )
        self._set_status(
            t(
                "detail.status.reports_saved",
                markdown=md_path.name,
                json=json_path.name,
            ),
            tone="success",
        )
        self._refresh_workflow()

    def _build_follow_up_card(self) -> QFrame:
        """Waiting-on-depositor banner (dv-5eg), above the verdict banner."""
        card = QFrame()
        card.setObjectName("FollowUpCard")
        lay = QHBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(10)
        self._follow_up_icon = QLabel()
        lay.addWidget(self._follow_up_icon)
        self._follow_up_label = QLabel("")
        self._follow_up_label.setObjectName("LabelStrongSM")
        self._follow_up_label.setWordWrap(True)
        lay.addWidget(self._follow_up_label, 1)
        self._follow_up_checks_btn = make_action_button(
            t("detail.follow_up.run_checks"), kind="primary", size="sm"
        )
        self._follow_up_checks_btn.clicked.connect(self._on_run_checks)
        self._follow_up_checks_btn.setVisible(False)
        lay.addWidget(self._follow_up_checks_btn)
        self._follow_up_changes_btn = make_action_button(
            t("detail.follow_up.changes"), kind="secondary", size="sm"
        )
        self._follow_up_changes_btn.clicked.connect(lambda: self._on_workflow_step("changes"))
        lay.addWidget(self._follow_up_changes_btn)
        card.setVisible(False)
        return card

    def _refresh_follow_up(self) -> None:
        """Paint the follow-up banner from in-memory + stored state."""
        from ui.icons import icon as _icon

        opened_at = ""
        state = ""
        try:
            st = self._state()
            try:
                row = st.get_follow_up(self._pid)
            finally:
                try:
                    st.close()
                except Exception:
                    pass
            if isinstance(row, dict):
                opened_at = str(row.get("opened_at") or "")
                state = str(row.get("state") or "")
        except Exception:
            pass
        try:
            last_update = str((self._timestamps or {}).get("lastUpdateTime") or "")
        except Exception:
            last_update = ""
        if opened_at and last_update:
            try:
                from curation import follow_ups as _fu

                state = _fu.state_for(opened_at, last_update)
            except Exception:
                pass
        self._follow_up = {"opened_at": opened_at, "state": state} if opened_at else None
        if not opened_at:
            self._follow_up_card.setVisible(False)
            return
        updated = state == "depositor_updated"
        try:
            self._follow_up_icon.setPixmap(
                _icon(
                    "triangle-alert" if updated else "clock",
                    color=TEXT_AMBER if updated else TEXT_MUTED,
                ).pixmap(18, 18)
            )
        except Exception:
            pass
        self._follow_up_card.setStyleSheet(
            surface_frame_qss(
                SURFACE_TINT if updated else SURFACE_SUBTLE,
                STATE_WARNING_GRAPHIC if updated else BORDER_SUBTLE,
                selector="QFrame#FollowUpCard",
                theme=ACTIVE_THEME,
            )
        )
        self._follow_up_label.setText(
            t(
                "detail.follow_up.updated" if updated else "detail.follow_up.awaiting",
                date=opened_at[:10],
            )
        )
        self._follow_up_checks_btn.setVisible(bool(updated))
        self._follow_up_changes_btn.setVisible(bool(updated))
        self._follow_up_card.setVisible(True)

    def _note_follow_up_update(self) -> None:
        """Persist the observed draft lastUpdateTime for an open follow-up."""
        try:
            last_update = str((self._timestamps or {}).get("lastUpdateTime") or "")
            if not last_update:
                return
            st = self._state()
            try:
                if st.get_follow_up(self._pid):
                    st.set_follow_up_last_update(self._pid, last_update)
            finally:
                try:
                    st.close()
                except Exception:
                    pass
        except Exception:
            pass
        self._refresh_follow_up()

    def _sync_follow_up(self, decision: str) -> None:
        """Open/close the follow-up from a committed decision (dv-5eg)."""
        try:
            from curation import follow_ups as _fu

            is_revision = _fu.is_revision_decision(decision, t("detail.decision.option_revisions"))
            st = self._state()
            try:
                if is_revision:
                    st.open_follow_up(self._pid, decision_label=decision)
                else:
                    closed = st.close_follow_up(self._pid)
                    if closed:
                        self._log_action(
                            "follow_up_closed",
                            t("detail.follow_up.log_closed"),
                        )
            finally:
                try:
                    st.close()
                except Exception:
                    pass
            if is_revision:
                self._log_action("follow_up_opened", t("detail.follow_up.log_opened"))
        except Exception:
            pass
        self._refresh_follow_up()

    def _build_sensitivity_card(self) -> QFrame:
        """Questionnaire card on the Response page, above the decision."""
        card, body, _title, header = make_card(t("detail.sensitivity.title"))
        add_info_tip(
            header,
            t("detail.sensitivity.tip"),
            name=t("detail.sensitivity.title"),
            group="General",
        )
        body.setContentsMargins(16, 12, 16, 12)
        body.setSpacing(8)
        self._load_sensitivity_review()
        self._sensitivity_status = QLabel("")
        self._sensitivity_status.setObjectName("StateMD")
        self._sensitivity_status.setTextFormat(Qt.TextFormat.RichText)
        body.addWidget(self._sensitivity_status)
        self._sensitivity_combos: dict[str, QComboBox] = {}
        suggestions = self._sensitivity_suggestions()
        for q in QUESTIONS:
            qid = str(q.get("id") or "")
            prompt = make_small_body_label(str(q.get("prompt") or ""), wrap=True)
            prompt.setToolTip(str(q.get("help") or ""))
            body.addWidget(prompt)
            row = QHBoxLayout()
            row.setSpacing(8)
            combo = make_combo(
                [
                    (t("detail.sensitivity.answer_unset"), ""),
                    (t("detail.sensitivity.answer_yes"), "yes"),
                    (t("detail.sensitivity.answer_no"), "no"),
                ],
                height=28,
                min_width=120,
                tip=str(q.get("help") or ""),
            )
            stored = str((self._sensitivity_answers or {}).get(qid) or "")
            combo.setCurrentIndex({"": 0, "yes": 1, "no": 2}.get(stored, 0))
            combo.currentIndexChanged.connect(lambda _i, qid=qid: self._on_sensitivity_answer(qid))
            self._sensitivity_combos[qid] = combo
            row.addWidget(combo)
            caption = make_caption_label("")
            if stored and stored == suggestions.get(qid):
                word = (
                    t("detail.sensitivity.answer_yes")
                    if stored == "yes"
                    else t("detail.sensitivity.answer_no")
                )
                caption.setText(t("detail.sensitivity.suggested", value=word))
            row.addWidget(caption, 1)
            wrap = QWidget()
            wrap.setLayout(row)
            body.addWidget(wrap)
        self._refresh_sensitivity_status()
        return card

    def _refresh_sensitivity_card(self) -> None:
        """Re-pull stored answers + suggestions after metadata/checks load."""
        combos = getattr(self, "_sensitivity_combos", {})
        if not combos:
            return
        self._load_sensitivity_review()
        for qid, combo in combos.items():
            stored = str((self._sensitivity_answers or {}).get(qid) or "")
            combo.blockSignals(True)
            combo.setCurrentIndex({"": 0, "yes": 1, "no": 2}.get(stored, 0))
            combo.blockSignals(False)
        self._refresh_sensitivity_status()

    def _refresh_sensitivity_status(self) -> None:
        try:
            answered = answered_count(self._sensitivity_answers)
            total = len(QUESTIONS)
            color = TEXT_SUCCESS if is_complete(self._sensitivity_answers) else TEXT_AMBER
            self._sensitivity_status.setText(
                f"<span style='color: {color};'>"
                + t("detail.sensitivity.status_caption", answered=answered, total=total)
                + "</span>"
            )
        except Exception:
            pass

    def _on_sensitivity_answer(self, qid: str) -> None:
        """One answer changed: persist, refresh the caption, log."""
        combo = getattr(self, "_sensitivity_combos", {}).get(qid)
        if combo is None:
            return
        token = str(combo.currentData() or "")
        answers = dict(getattr(self, "_sensitivity_answers", {}) or {})
        if token in ("yes", "no"):
            answers[qid] = token
        else:
            answers.pop(qid, None)
        self._sensitivity_answers = answers
        try:
            st = self._state()
            if st is not None:
                st.set_sensitivity_review(self._pid, answers)
        except Exception:
            return
        self._refresh_sensitivity_status()
        self._log_action(
            "sensitivity_reviewed",
            t(
                "detail.sensitivity.log_note",
                answered=answered_count(answers),
                total=len(QUESTIONS),
            ),
            {"answered": answered_count(answers)},
        )

    def _sensitivity_blocks(self) -> tuple[bool, str]:
        """(blocked, message) for an Approve decision under this ruleset."""
        try:
            if not ruleset_requires(self._ruleset):
                return False, ""
            if is_complete(self._sensitivity_answers):
                return False, ""
            return True, t(
                "detail.sensitivity.gate_body",
                answered=answered_count(self._sensitivity_answers),
                total=len(QUESTIONS),
            )
        except Exception:
            return False, ""

    def _sensitivity_suggestions(self) -> dict[str, str | None]:
        """Machine-suggested answers from the report + inventory."""
        try:
            return suggested_answers(self._report, self._inventory)
        except Exception:
            return {}

    def _load_sensitivity_review(self) -> None:
        """Restore stored answers, plus machine suggestions where nothing is stored."""
        try:
            st = self._state()
            data = st.get_sensitivity_review(self._pid) if st is not None else None
        except Exception:
            data = None
        answers = dict((data or {}).get("answers") or {})
        for qid, suggestion in self._sensitivity_suggestions().items():
            if qid not in answers and suggestion in ("yes", "no"):
                answers[qid] = suggestion
        self._sensitivity_answers = answers

    def _on_export_record(self) -> None:
        """One click: the dated curation-record folder (dv-vwt)."""
        try:
            from curation.curation_record import export_record

            st = self._state()
            actions = st.list_actions(self._pid, limit=500) if st is not None else []
            decision_row = st.last_action(self._pid, "decision") if st is not None else None
            decision = str((decision_row or {}).get("notes") or "")
            dispositions = st.list_finding_dispositions(self._pid) if st is not None else {}
            sensitivity_data = st.get_sensitivity_review(self._pid) if st is not None else None
            try:
                response_text = self._response_edit.toPlainText()
            except Exception:
                response_text = ""
            try:
                staged = self._dl_mgr.files_dir(self._pid)
            except Exception:
                staged = None
            record_dir = export_record(
                self._dl_mgr.dataset_dir(self._pid),
                report=self._report,
                response_text=response_text,
                actions=actions,
                dispositions=dispositions,
                sensitivity=sensitivity_data,
                decision=decision,
                curation_label=str((self._curation or {}).get("label") or ""),
                staged_dir=staged if (staged and staged.exists()) else None,
            )
            self._log_action(
                "curation_record_exported",
                t("detail.status.record_saved_log", name=record_dir.name),
                {"path": str(record_dir)},
            )
            self._set_status(t("detail.status.record_saved", path=record_dir), tone="success")
        except Exception as exc:
            dialogs.show_warning(
                self,
                t("detail.header.export_record"),
                t("detail.status.record_failed", exc=exc),
            )
