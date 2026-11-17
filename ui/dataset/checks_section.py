"""The Auto-Checks card: running the checks and reading the result tree."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

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
)
from ui.widgets import (
    add_info_tip,
    make_badge,
    make_caption_label,
    make_card,
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
        )
        # Named pre-run state, never "—" (2026-10-02 P2); refreshed to
        # "N check(s) will run"/counts/"No file checks" as data lands.
        self._auto_summary = make_field_label(t("detail.auto_checks.not_run"))
        header_lay.addWidget(self._auto_summary)
        # Body: scroll of checks (factory body reused directly)
        self._auto_body = _body_host
        self._auto_body.setContentsMargins(16, 12, 16, 12)
        self._auto_body.setSpacing(8)
        # Placeholder
        self._auto_placeholder = make_small_body_label(t("detail.auto_checks.no_file_list"))
        self._auto_body.addWidget(self._auto_placeholder)
        return card

    def _auto_row(
        self, check_id: str, desc: str, passed: bool, level: str, badge: str | None = None
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
        cid = QLabel(check_id)
        cid.setObjectName("LabelStrongSM")
        txt.addWidget(cid)
        d = make_caption_label(desc)
        txt.addWidget(d)
        lay.addLayout(txt, 1)
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
            + t("detail.status.use_export_for_markdown")
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
        self._set_status(t("detail.status.checks_failed", reason=headline))
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
            if not self._report:
                return
            path = info.get("path", "")
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
