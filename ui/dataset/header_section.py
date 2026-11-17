"""The page header: the title link, the status pill, the ring and the curation preview."""

from pathlib import Path

from PySide6.QtWidgets import QLabel

from ui.dataset.helpers import _pill_state
from ui.dataset.state import DetailState
from ui.i18n import t
from ui.theme import ACCENT_PRIMARY, selectable_labels
from ui.widgets import make_small_body_label, set_badge_label


class HeaderSection(DetailState):
    """The page header: the title link, the status pill, the ring and the curation preview."""

    def _update_header_link(self, metadata: dict | None = None) -> None:  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
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
        header_link = getattr(self, "_header_link", None)
        if header_link is not None:
            link_text = (
                t("detail.header.open_link_draft")
                if version_state == "DRAFT"
                else t("detail.header.open_link")
            )
            header_link.setText(
                f"<a href='{url}' style='color:{ACCENT_PRIMARY}; text-decoration:none;'>{link_text}</a>"
            )
        title_lbl = getattr(self, "_title_lbl", None)
        if title_lbl is not None:
            title_lbl.setText(self._title)

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
                if (
                    self._inventory is not None
                    and len(self._inventory) == 0
                    and self._metadata is not None
                ):
                    ph = make_small_body_label(t("detail.auto_checks.no_files_in_dataverse"))
                    # A measured zero, not a placeholder — name it (2026-10-02 P2).
                    self._auto_summary.setText(t("detail.auto_checks.no_file_checks"))
                else:
                    ph = make_small_body_label(t("detail.auto_checks.no_file_list"))
                    self._auto_summary.setText(t("detail.auto_checks.not_run"))
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
                self._auto_summary.setText(
                    t(
                        "detail.auto_checks.summary_counts",
                        passed=summary["passed"],
                        warnings=summary["failed-warning"],
                        errors=summary["failed-error"],
                        skipped=summary["skipped"],
                    )
                )
                for c in self._report.dataset_checks:
                    row = self._auto_row(c.check_id, c.message, c.passed, c.level)
                    try:
                        from ui.checks_tree import format_details_tooltip

                        row.setToolTip(format_details_tooltip(c))
                    except Exception:
                        pass
                    self._auto_body.addWidget(row)
                # Every per-file finding also surfaces here (not just
                # inventory.*): failed checks with their file path, and
                # skipped checks (missing library) that did not run.
                # Passes stay in the manifest tree only — they are the
                # bulk and the tree shows them per file.
                from engine.status import classify

                file_findings = [
                    (f, c)
                    for f in self._report.files
                    for c in f.checks
                    if classify(c) in ("failed-error", "failed-warning", "skipped")
                ]
                for f, c in file_findings:
                    kind = classify(c)
                    desc = t(
                        "detail.auto_checks.file_result_format",
                        path=f.path,
                        message=c.message,
                    )
                    if kind == "skipped":
                        row = self._auto_row(
                            c.check_id,
                            desc,
                            True,
                            "warning",
                            badge=t("status.badges.skipped"),
                        )
                    else:
                        row = self._auto_row(c.check_id, desc, c.passed, c.level)
                    try:
                        from ui.checks_tree import format_details_tooltip

                        row.setToolTip(format_details_tooltip(c))
                    except Exception:
                        pass
                    self._auto_body.addWidget(row)
                if (
                    not self._report.dataset_checks
                    and not file_findings
                    and not any(f.checks for f in self._report.files)
                ):
                    ok = QLabel(t("detail.auto_checks.all_passed"))
                    ok.setObjectName("AccentSM")
                    self._auto_body.addWidget(ok)
            else:
                # Only checks that will actually run for this dataset's
                # files (checks with no matching files are not listed).
                self._auto_summary.setText(t("detail.auto_checks.will_run", count=will))
                if not will:
                    ph = make_small_body_label(t("detail.auto_checks.no_matching_checks"))
                    self._auto_body.addWidget(ph)
                for p in planned:
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
                    missing = ""
                    if pip_pkg:
                        try:
                            __import__(pip_pkg if pip_pkg != "Pillow" else "PIL")
                        except ImportError:
                            missing = t("detail.auto_checks.missing_pip", package=pip_pkg)
                    status = missing or t("detail.auto_checks.will_run_badge")
                    # Interpret for row styling: missing = warn, else pass tone
                    if missing:
                        row = self._auto_row(
                            p["check_id"],
                            p["description"],
                            False,
                            "warning",
                            badge=t("detail.auto_checks.badge_missing"),
                        )
                    else:
                        row = self._auto_row(
                            p["check_id"],
                            p["description"],
                            True,
                            "info",
                            badge=t("detail.auto_checks.badge_pass"),
                        )
                    # Add subtitle with file_types + status
                    row.setToolTip(f"{p['description']}\n\n{status}")
                    self._auto_body.addWidget(row)
        except Exception:
            pass
        try:
            selectable_labels(self._auto_card)
        except Exception:
            pass

    def _set_status(self, msg: str) -> None:
        self._status.setText(msg)
        self._status.setVisible(bool(msg))

    @staticmethod
    def _dress_pill(pill: QLabel, text: str, label: str) -> None:
        """Re-dress a status pill in the badge face its label wears.

        The kit builds the badge; when the words change, the face comes
        from the kit too - so the pill cannot end up wearing a
        different face from the one it started with.
        """
        set_badge_label(pill, text, label=label)

    def _on_ring_fraction(self, fraction: float) -> None:
        """Drive the circular progress ring (download / checks)."""
        try:
            self._ring.show()
            self._ring.setFraction(fraction)
            self._ring.setAccessibleDescription(self._ring.accessibleDescription())
        except Exception:
            pass

    def _hide_ring(self) -> None:
        """Hide the ring when the work it tracks is done."""
        try:
            self._ring.hide()
        except Exception:
            pass
