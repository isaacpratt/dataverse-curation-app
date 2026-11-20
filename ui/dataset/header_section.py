"""The page header: the title link, the status pill, the ring and the curation preview."""

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
)

from curation.storage import finding_key
from ui.check_titles import (
    check_summary,
    check_title,
)
from ui.dataset.helpers import _pill_state
from ui.dataset.state import DetailState
from ui.i18n import t
from ui.theme import (
    ACCENT_PRIMARY,
    BORDER_SUBTLE,
    FONT_BODY,
    STATE_ERROR_BG,
    STATE_ERROR_BORDER,
    STATE_SUCCESS_GRAPHIC,
    STATE_WARNING_GRAPHIC,
    SURFACE_CARD,
    SURFACE_SUBTLE,
    SURFACE_TINT,
    TEXT_AMBER,
    TEXT_DANGER,
    TEXT_MUTED,
    TEXT_SUCCESS,
    selectable_labels,
    status_strip_qss,
    surface_frame_qss,
)
from ui.widgets import (
    make_action_button,
    make_small_body_label,
    set_badge_label,
)


class HeaderSection(DetailState):
    """The page header: the title link, the status pill, the ring and the curation preview."""

    def _update_header_link(self, metadata: dict[str, Any] | None = None) -> None:  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
        # Defensive: runs mid-__init__ before all header widgets exist, and
        # again on every metadata load (cached metadata makes `meta` truthy
        # on the very first call — see the reopen crash this guards).
        meta = metadata if metadata is not None else self._metadata
        version_state = ""
        if isinstance(meta, dict):
            latest = meta.get("latestVersion") or {}
            version_state = (latest.get("versionState") or "").upper()
        # Badge (words match the dashboard status column; color is per
        # label via the kit's badge face, DOI-badge chrome)
        _pill_name, pill_text = _pill_state(version_state, getattr(self, "_in_review", False))
        status_pill = getattr(self, "_status_pill", None)
        if status_pill is not None:
            self._dress_pill(status_pill, pill_text, pill_text)
        # Contact/date
        if meta and isinstance(meta, dict):
            latest = meta.get("latestVersion") or {}
            blocks = latest.get("metadataBlocks") or {}
            cite = blocks.get("citation", {}) if isinstance(blocks, dict) else {}
            fields = cite.get("fields", []) if isinstance(cite, dict) else []
            depositor = ""
            for f in fields:
                if f.get("typeName") == "datasetContact":
                    v = f.get("value", [])
                    if isinstance(v, list) and v:
                        first = v[0]
                        name = (
                            first.get("datasetContactName", {}).get("value", "")
                            if isinstance(first.get("datasetContactName"), dict)
                            else ""
                        )
                        depositor = name or t("common.em_dash")
                    break
            # Prefer the real Dataverse title when metadata arrives (TopNav chips use it)
            try:
                from curation.client import extract_title

                real_title = extract_title(latest) if isinstance(latest, dict) else ""
                if real_title and real_title != self._title:
                    self._title = real_title
                    try:
                        self.titleChanged.emit(self._pid, self._title)
                    except Exception:
                        pass
            except Exception:
                pass
            depositor_lbl = getattr(self, "_depositor_lbl", None)
            if depositor_lbl is None:
                return
            depositor_lbl.setText(
                t("detail.header.submitted_by", depositor=depositor)
                if depositor
                else f"{self._pid}"
            )
            date = (latest.get("createTime") or latest.get("lastUpdateTime") or "")[:10]
            if date:
                depositor_lbl.setText(
                    depositor_lbl.text() + t("detail.header.depositor_date", date=date)
                )
        url = f"{self._config.dataverse.base_url}/dataset.xhtml?persistentId={self._pid}" + (
            "&version=DRAFT" if version_state == "DRAFT" else ""
        )
        id_badge = getattr(self, "_id_badge", None)
        if id_badge is not None:
            id_badge.setText(
                f"<a href='{url}' style='color:{ACCENT_PRIMARY}; text-decoration:none;'>"
                f"{self._pid}</a>"
            )
            id_badge.setToolTip(
                (
                    t("detail.header.open_link_draft")
                    if version_state == "DRAFT"
                    else t("detail.header.open_link")
                )
                + f"\n{url}"
            )
        title_lbl = getattr(self, "_title_lbl", None)
        if title_lbl is not None:
            title_lbl.setText(self._title)

    def _refresh_metadata_button(self) -> None:
        """Load vs Reload Metadata — cached metadata means a re-fetch is possible."""
        btn = getattr(self, "_load_meta_btn", None)
        if btn is None:
            return
        if self._metadata is not None or getattr(self, "_changes_loaded", False):
            btn.setText(t("detail.header.reload_metadata"))
            btn.setToolTip(t("detail.header.reload_metadata_tip"))
        else:
            btn.setText(t("detail.header.load_metadata"))
            btn.setToolTip(t("detail.header.load_metadata_tip"))

    def _check_button_text(self) -> str:
        """Primary action label — driven by how far the check run has got (dv-gs5).

        fresh: stage the dataset and run everything; dataset-only: the file
        pass is still missing; both: the whole run can be repeated.
        """
        report = getattr(self, "_report", None)
        if report is None:
            return t("detail.header.run_automatic_checks")
        dataset_results = list(getattr(report, "dataset_checks", []) or [])
        file_results = [c for f in (getattr(report, "files", []) or []) for c in (f.checks or [])]
        if dataset_results and not file_results:
            return t("detail.header.run_file_checks")
        return t("detail.header.rerun_automatic_checks")

    def _refresh_check_button(self) -> None:
        """Keep the primary button's label in step with the current report."""
        btn = getattr(self, "_check_btn", None)
        if btn is not None:
            btn.setText(self._check_button_text())

    def _refresh_header_actions(self) -> None:
        """Repaint both section-header buttons and the primary label (dv-gs5)."""
        self._refresh_metadata_button()
        self._refresh_check_button()

    def _update_curation_pill(self) -> None:
        """Show the Dataverse curation label (if any) next to the status pill."""
        label = ""
        tip = t("detail.header.curation_label_tooltip")
        try:
            label = str((self._curation or {}).get("label") or "").strip()
            when = str((self._curation or {}).get("time") or "")[:16].replace("T", " ")
            who = str((self._curation or {}).get("assigner") or "").strip()
            if label and (when or who):
                tip = t(
                    "detail.header.curation_label_set_by",
                    label=label,
                    when=when,
                    who=who,
                ).strip()
        except Exception:
            label = ""
        try:
            if label:
                self._dress_pill(self._curation_pill, label, label)
                self._curation_pill.setToolTip(tip)
                self._curation_pill.setVisible(True)
            else:
                self._curation_pill.setVisible(False)
        except Exception:
            pass

    def _refresh_curation_preview(self) -> None:  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
        """Populate Dataset-checks card: dataset-level results + summary.

        Per-file results live in the File Manifest tree (folder > file >
        check) to avoid duplicating 80+ rows here. This card shows dataset
        checks (inventory.*) with full messages, plus aggregate counts.
        """
        try:
            from engine.runner import list_planned_checks
            from engine.status import summarize

            staged = self._dl_mgr.files_dir(self._pid)
            if staged.exists():
                files = sorted(p for p in staged.rglob("*") if p.is_file())
            elif self._inventory:
                files = [Path(e.get("path", "")) for e in self._inventory]
            else:
                files = []
            planned = list_planned_checks(files)
            # Clear existing rows; the header summary is updated below.
            for i in reversed(range(self._auto_body.count())):
                item = self._auto_body.takeAt(i)
                w = item.widget() if item is not None else None
                if w is not None:
                    w.deleteLater()
            if not files:
                self._finding_keys = []
                if (
                    self._inventory is not None
                    and len(self._inventory) == 0
                    and self._metadata is not None
                ):
                    ph = make_small_body_label(t("detail.auto_checks.no_files_in_dataverse"))
                    # A measured zero, not a placeholder — name it (2026-10-02 P2).
                    self._set_auto_summary(t("detail.auto_checks.no_file_checks"))
                else:
                    ph = make_small_body_label(t("detail.auto_checks.no_file_list"))
                    self._set_auto_summary(t("detail.auto_checks.not_run"))
                self._auto_body.addWidget(ph)
                return
            # Count will_run
            will = sum(1 for p in planned if p.get("will_run"))
            if self._report is not None:
                # Dataset-level results with FULL messages (no truncation);
                # per-file results are in the manifest tree.
                all_results = list(self._report.dataset_checks) + [
                    c for f in self._report.files for c in f.checks
                ]
                summary = summarize(all_results)
                self._set_auto_summary(
                    t(
                        "detail.auto_checks.summary_counts",
                        passed=summary["passed"],
                        warnings=summary["failed-warning"],
                        errors=summary["failed-error"],
                        skipped=summary["skipped"],
                    )
                )
                from engine.status import classify

                # Findings carry a stable disposition key (dv-32x): failed
                # rows get an inline disposition combo; passes/skips don't.
                finding_keys: list[str] = []
                for c in self._report.dataset_checks:
                    kind = classify(c)
                    key = (
                        finding_key(c.check_id, "", c.message)
                        if kind in ("failed-error", "failed-warning")
                        else ""
                    )
                    if key:
                        finding_keys.append(key)
                    detail_lines = None
                    if c.check_id == "metadata.readme_sections":
                        secs = (c.details or {}).get("sections")
                        if isinstance(secs, list):
                            detail_lines = [
                                (
                                    str(s.get("label") or s.get("id") or ""),
                                    bool(s.get("found")),
                                )
                                for s in secs
                                if isinstance(s, dict)
                            ]
                    row = self._auto_row(
                        check_title(c.check_id),
                        check_summary(c),
                        c.passed,
                        c.level,
                        disposition_key=key,
                        detail_lines=detail_lines,
                    )
                    row.setProperty("auto_class", classify(c))
                    try:
                        from ui.checks_tree import format_details_tooltip

                        row.setToolTip(format_details_tooltip(c))
                    except Exception:
                        pass
                    self._auto_body.addWidget(row)
                self._finding_keys = finding_keys
                self._refresh_finding_summary()
                if not self._report.dataset_checks:
                    ok = QLabel(t("detail.auto_checks.all_passed"))
                    ok.setObjectName("AccentSM")
                    self._auto_body.addWidget(ok)
            else:
                # Only checks that will actually run for this dataset's
                # files (checks with no matching files are not listed).
                self._finding_keys = []
                self._set_auto_summary(t("detail.auto_checks.will_run", count=will))
                if not will:
                    ph = make_small_body_label(t("detail.auto_checks.no_matching_checks"))
                    self._auto_body.addWidget(ph)
                for p in planned:
                    # Only dataset-scoped checks belong to this section;
                    # per-file checks are listed by File checks instead.
                    if p.get("scope", "file") != "dataset":
                        continue
                    if not p.get("will_run"):
                        continue
                    # lib_map check
                    lib_map = {
                        "format.spss": "pyreadstat",
                        "format.stata": "pyreadstat",
                        "format.sas": "pyreadstat",
                        "format.netcdf": "netCDF4",
                        "format.hdf5": "h5py",
                        "format.tiff": "tifffile",
                        "format.images": "Pillow",
                        "format.pdf": "pypdf",
                        "format.xml": "lxml",
                        "format.xlsx": "openpyxl",
                    }
                    pip_pkg = lib_map.get(p["check_id"], "")
                    missing = False
                    if pip_pkg:
                        try:
                            __import__(pip_pkg if pip_pkg != "Pillow" else "PIL")
                        except ImportError:
                            missing = True
                    applies = t(
                        "detail.auto_checks.will_run_applies",
                        file_types=p.get("file_types") or t("common.em_dash"),
                    )
                    # dv-dcd: name the check, explain what it will look at,
                    # and say plainly when its optional library is absent.
                    if missing:
                        row = self._auto_row(
                            check_title(p["check_id"]),
                            t(
                                "detail.auto_checks.missing_detail",
                                applies=applies,
                                package=pip_pkg,
                            ),
                            False,
                            "warning",
                            badge=t("detail.auto_checks.badge_missing"),
                        )
                    else:
                        row = self._auto_row(
                            check_title(p["check_id"]),
                            applies,
                            True,
                            "info",
                            badge=t("detail.auto_checks.will_run_badge"),
                        )
                    row.setToolTip(applies)
                    # A planned row is not a finding yet — a severity
                    # filter folds it away (dv-bph).
                    row.setProperty("auto_class", "planned")
                    self._auto_body.addWidget(row)
        except Exception:
            pass
        self._apply_auto_filter()
        try:
            selectable_labels(self._auto_card)
        except Exception:
            pass

    def _set_status(self, msg: str, tone: str = "info") -> None:
        """Set the status strip. tone: info (quiet) | success | error.

        Success/error wear body-size high-contrast text and an icon so a
        confirmation reads at a glance (dv-3wc); the message persists
        until the next _set_status call (no timers).
        """
        text = str(msg or "")
        visible = bool(text)
        self._status.setText(text)
        try:
            from ui.icons import icon as _icon

            if tone == "success":
                color, name = TEXT_SUCCESS, "check"
            elif tone == "error":
                color, name = TEXT_DANGER, "x"
            else:
                color, name = None, None
            if name is not None:
                self._status_icon.setPixmap(_icon(name, color=color, size=16).pixmap(16, 16))
                self._status_icon.show()
            else:
                self._status_icon.hide()
            self._status.setStyleSheet(
                status_strip_qss(
                    SURFACE_CARD,
                    BORDER_SUBTLE,
                    color or TEXT_MUTED,
                    font_size=FONT_BODY,
                    weight=600 if name is not None else None,
                )
            )
        except Exception:
            pass
        self._status.setVisible(visible)
        # While the compact widget owns progress, its own line is enough —
        # the general message strip would duplicate it (dv-cv3).
        widget = getattr(self, "_status_widget", None)
        self._status_row.setVisible(visible and not (widget is not None and widget.isVisible()))

    @staticmethod
    def _dress_pill(pill: QLabel, text: str, label: str) -> None:
        """Re-dress a status pill in the badge face its label wears.

        The kit builds the badge; when the words change, the face comes
        from the kit too - so the pill cannot end up wearing a
        different face from the one it started with.
        """
        set_badge_label(pill, text, label=label)

    def _status_context(self) -> str:
        """Short count detail for the compact widget, from state in memory."""
        staged = int(getattr(self, "_staged_n", 0) or 0)
        total = int(getattr(self, "_staged_total", 0) or 0)
        return f"{staged}/{total}" if total else ""

    def _refresh_rail_counts(self, summary: Any = None) -> None:
        """Feed the rail's result pills from a check-run summary."""
        rail = getattr(self, "_rail", None)
        if rail is None:
            return
        if summary is None:
            report = getattr(self, "_report", None)
            if report is None:
                rail.set_nav_counts()
                return
            from engine.status import summarize

            summary = summarize(
                list(getattr(report, "dataset_checks", []) or [])
                + [c for f in (getattr(report, "files", []) or []) for c in (f.checks or [])]
            )
        rail.set_nav_counts(
            passed=int(summary.get("passed", 0) or 0),
            warnings=int(summary.get("failed-warning", 0) or 0),
            errors=int(summary.get("failed-error", 0) or 0),
        )

    def _on_status_action(self) -> None:
        """Route the widget's action to the right cancel/retry/dismiss path."""
        widget = getattr(self, "_status_widget", None)
        if widget is None or not widget.isVisible():
            return
        tip = widget._action.toolTip().lower()
        if "retry" in tip:
            self._on_run_checks()
        elif "cancel" in tip:
            if getattr(self, "_check_worker", None) is not None:
                self._on_cancel_checks_click()
            elif getattr(self, "_dl_worker", None) is not None:
                self._on_download_cancel_click()
        widget.clear()

    def _show_status_complete(self, title: str, detail: str = "") -> None:
        widget = getattr(self, "_status_widget", None)
        if widget is not None:
            widget.set_complete(title, detail or self._status_context())
        self._status_row.setVisible(False)

    def _show_status_error(self, title: str, detail: str = "") -> None:
        widget = getattr(self, "_status_widget", None)
        if widget is not None:
            widget.set_error(title, detail)
        self._status_row.setVisible(False)

    def _on_ring_fraction(self, fraction: float) -> None:
        """Drive the compact status widget's progress bar (download / checks)."""
        widget = getattr(self, "_status_widget", None)
        if widget is not None:
            if getattr(self, "_check_worker", None) is not None:
                title = t("detail.statuswidget.running")
            else:
                title = t("detail.statuswidget.downloading")
            widget.set_running(title, self._status_context(), fraction)
            self._status_row.setVisible(False)
        # Keep the retired ring object coherent for any caller that still
        # reaches for it, but it no longer occupies a row.
        try:
            self._ring.setFraction(fraction)
        except Exception:
            pass

    def _hide_ring(self) -> None:
        """Clear the compact status widget when the work it tracked is done."""
        widget = getattr(self, "_status_widget", None)
        if widget is not None:
            widget.clear()
        try:
            self._ring.hide()
        except Exception:
            pass

    def _build_verdict_card(self) -> QFrame:
        """Readiness banner (dv-6nv): one synthesized answer, top of page."""
        from ui.icons import icon as _icon

        card = QFrame()
        card.setObjectName("VerdictCard")
        lay = QHBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(10)
        self._verdict_icon = QLabel()
        try:
            self._verdict_icon.setPixmap(_icon("circle-dashed", color=TEXT_MUTED).pixmap(18, 18))
        except Exception:
            pass
        lay.addWidget(self._verdict_icon)
        self._verdict_label = QLabel(t("detail.verdict.level_unreviewed"))
        self._verdict_label.setObjectName("LabelStrongSM")
        self._verdict_label.setTextFormat(Qt.TextFormat.RichText)
        self._verdict_label.setWordWrap(True)
        lay.addWidget(self._verdict_label)
        lay.addStretch(1)
        self._verdict_chips = QHBoxLayout()
        self._verdict_chips.setSpacing(6)
        lay.addLayout(self._verdict_chips)
        card.setToolTip(t("detail.verdict.banner_tip"))
        return card

    def _refresh_verdict(self) -> None:
        """Recompute + paint the readiness banner from in-memory state."""
        try:
            from engine.verdict import assess
            from ui.icons import icon as _icon

            verdict = assess(
                self._report,
                self._completeness_full,
                self._dispositions_map(),
            )
            faces = {
                "ready": (SURFACE_TINT, STATE_SUCCESS_GRAPHIC, TEXT_SUCCESS, "check"),
                "revisions": (SURFACE_TINT, STATE_WARNING_GRAPHIC, TEXT_AMBER, "octagon-alert"),
                "blocked": (STATE_ERROR_BG, STATE_ERROR_BORDER, TEXT_DANGER, "octagon-x"),
                "unreviewed": (SURFACE_SUBTLE, BORDER_SUBTLE, TEXT_MUTED, "circle-dashed"),
            }
            bg, border, ink, icon_name = faces.get(verdict.level, faces["unreviewed"])
            self._verdict_card.setStyleSheet(
                surface_frame_qss(bg, border, selector="QFrame#VerdictCard")
            )
            try:
                self._verdict_icon.setPixmap(_icon(icon_name, color=ink).pixmap(18, 18))
            except Exception:
                pass
            self._verdict_label.setText(
                f"<span style='color: {ink};'>"
                + t(_VERDICT_LEVEL_KEYS.get(verdict.level, "detail.verdict.level_unreviewed"))
                + "</span>"
            )
            while self._verdict_chips.count():
                item = self._verdict_chips.takeAt(0)
                w = item.widget() if item is not None else None
                if w is not None:
                    w.setParent(None)  # unparent now; deleteLater is async
                    w.deleteLater()
            for reason in verdict.reasons:
                key = _VERDICT_REASON_KEYS.get(reason.key)
                if not key:
                    continue
                chip = make_action_button(t(key, count=reason.count), kind="chip", size="sm")
                chip.setToolTip(t("detail.verdict.banner_tip"))
                chip.clicked.connect(lambda _c=False, tgt=reason.target: self._on_verdict_chip(tgt))
                self._verdict_chips.addWidget(chip)
        except Exception:
            pass

    def _on_verdict_chip(self, target: str) -> None:
        """Navigate to the card that owns a selected reason chip."""
        try:
            if target == "respond":
                self._show_response_page()
            elif target:
                self._goto_section(target)
        except Exception:
            pass


_VERDICT_REASON_KEYS = {
    "required-missing": "detail.verdict.reason_required",
    "optional-missing": "detail.verdict.reason_optional",
    "errors": "detail.verdict.reason_errors",
    "warnings": "detail.verdict.reason_warnings",
    "sensitivity": "detail.verdict.reason_sensitivity",
}

_VERDICT_LEVEL_KEYS = {
    "ready": "detail.verdict.level_ready",
    "revisions": "detail.verdict.level_revisions",
    "blocked": "detail.verdict.level_blocked",
    "unreviewed": "detail.verdict.level_unreviewed",
}
