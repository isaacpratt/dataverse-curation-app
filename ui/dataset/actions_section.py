"""The Assessment action: the decision state, the commit, the download and the export."""

from pathlib import Path

from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout

from curation.download_manager import DownloadManager
from ui import dialogs
from ui.dataset.state import DetailState
from ui.download_dialog import DownloadApprovalDialog
from ui.i18n import t
from ui.theme import FONT_SMALL
from ui.widgets import (
    add_info_tip,
    make_action_button,
    make_caption_label,
    make_card,
    make_combo,
    make_field_label,
    make_multiline_input,
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
            self._set_status(t("detail.download.all_verified_skip", count=len(inventory)))
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
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)
        self._dl_worker = DownloadWorker(
            self._client,
            self._config.app.workspace,
            self._pid,
            self,
            guestbook_response=guestbook_response,
        )
        self._dl_worker.progress.connect(
            lambda n: self._progress.setFormat(f"{n / 1024**2:.1f} MB")
        )
        self._dl_worker.progressFraction.connect(self._on_ring_fraction)
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
        self._progress.setVisible(False)
        self._hide_ring()
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
        self._set_status(t("detail.status.downloaded_to", path=staged))
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

    def _on_download_error(self, msg: str) -> None:
        self._dl_worker = None
        self._progress.setVisible(False)
        self._hide_ring()
        self._dl_btn.setEnabled(True)
        self._set_status("")
        headline, details = dialogs.describe_error(msg)
        dialogs.show_critical(
            self, t("detail.download.title"), headline, details=details, retry=self._on_download
        )

    def _on_download_cancel_click(self) -> None:
        """Ask the worker to stop; stay disabled until it acknowledges."""
        if self._dl_worker is None:
            return
        self._dl_cancel_btn.setEnabled(False)
        self._set_status(t("detail.status.cancelling"))
        try:
            self._dl_worker.cancel()
        except Exception:
            pass

    def _on_download_cancelled(self) -> None:
        """Worker acknowledged the cancel: reset the action row quietly."""
        self._dl_worker = None
        self._progress.setVisible(False)
        self._hide_ring()
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
            )
        )
        self._refresh_workflow()
