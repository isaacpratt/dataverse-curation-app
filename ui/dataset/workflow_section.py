"""The workflow rail and the section cards it navigates to."""

from curation.storage import (
    read_ui_pref,
    write_ui_pref,
)
from ui.dataset.state import DetailState
from ui.i18n import t


class WorkflowSection(DetailState):
    """The workflow rail and the section cards it navigates to."""

    def _on_workflow_step(self, key: str) -> None:  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
        """Navigate the rail only — never run a download, check or export."""
        try:
            view = read_ui_pref(self._config.app.workspace, RAIL_VIEW_PREF, "mechanical")
        except Exception:
            view = "mechanical"
        try:
            self._log_action(
                "nav_jump",
                f"{key} ({view})",
                {"step": str(key), "view": str(view)},
            )
        except Exception:
            pass
        try:
            if key == "respond":
                self._show_response_page()
                return

            # CURATE(D) practice view (dv-sce): same navigation contract,
            # mapped onto the card that owns each practice step.
            target = _CURATED_TARGETS.get(key)
            if target is not None:
                if target == "respond":
                    self._show_response_page()
                else:
                    self._show_review_page()
                    self._goto_section(target)
                return

            # Review steps: return to the review page first, then scroll.
            self._show_review_page()
            if key == "metadata":
                self._goto_section("_meta_card")
            elif key == "changes":
                self._goto_section("_version_card")
            elif key == "download":
                self._goto_section("_file_card")
                if self._dl_btn is not None:
                    self._dl_btn.setFocus()
            elif key == "checks":
                self._goto_section("_auto_card")
                if self._check_btn is not None:
                    self._check_btn.setFocus()
            elif key == "export":
                if self._report is None:
                    self._set_status(t("detail.workflow.run_checks_first"))
                else:
                    self._set_status(t("detail.workflow.export_hint"))
                if self._history_btn is not None:
                    self._history_btn.setFocus()
        except Exception:
            pass

    def _refresh_workflow(self) -> None:
        """Repaint the rail from flags/counts already in memory (no I/O)."""
        try:
            from ui.workflow import WorkflowInput, derive_curated, derive_workflow

            curated = (
                read_ui_pref(self._config.app.workspace, RAIL_VIEW_PREF, "mechanical") == "curated"
            )
            # Unresolved review signals from the verdict derivation (the
            # same numbers the banner shows; resolved findings stop counting).
            counts: dict = {}
            try:
                from engine.verdict import assess

                counts = {
                    r.key: r.count
                    for r in assess(
                        self._report,
                        self._completeness_full,
                        self._dispositions_map(),
                    ).reasons
                }
            except Exception:
                counts = {}
            state = WorkflowInput(
                metadata_loaded=self._metadata is not None,
                changes_loaded=bool(getattr(self, "_changes_loaded", False)),
                inventory_ok=bool(getattr(self, "_inventory_ok", True)),
                staged=int(getattr(self, "_staged_n", 0) or 0),
                total_files=int(getattr(self, "_staged_total", 0) or 0),
                report_ready=self._report is not None,
                exported=bool(getattr(self, "_last_export_path", None)),
                response_open=bool(getattr(self, "_in_response", False)),
                decision_committed=bool(getattr(self, "_decision_committed", False))
                or bool((self._curation or {}).get("label")),
                errors=int(counts.get("errors", 0)),
                warnings=int(counts.get("warnings", 0)),
                required_missing=int(counts.get("required-missing", 0)),
                optional_missing=int(counts.get("optional-missing", 0)),
            )
            workflow = derive_curated(state) if curated else derive_workflow(state)
            self._rail.set_workflow(workflow)
            self._rail.set_toggle_label(
                t("workflow.curated.toggle_steps" if curated else "workflow.curated.toggle_curated")
            )
        except Exception:
            pass
        try:
            self._refresh_verdict()
        except Exception:
            pass
        try:
            self._refresh_follow_up()
        except Exception:
            pass

    def _on_rail_view_toggled(self) -> None:
        """Flip the rail between the mechanical and CURATE(D) views."""
        try:
            current = read_ui_pref(self._config.app.workspace, RAIL_VIEW_PREF, "mechanical")
            write_ui_pref(
                self._config.app.workspace,
                RAIL_VIEW_PREF,
                "mechanical" if current == "curated" else "curated",
            )
        except Exception:
            pass
        self._refresh_workflow()


RAIL_VIEW_PREF = "rail_view"

_CURATED_TARGETS = {
    "check": "_file_card",
    "understand": "_auto_card",
    "request": "_meta_card",
    "augment": "_meta_card",
    "transform": "_auto_card",
    "evaluate": "_auto_card",
    "document": "respond",
}
