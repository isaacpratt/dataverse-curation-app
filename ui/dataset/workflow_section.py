"""The workflow rail and the section cards it navigates to."""

from ui.dataset.state import DetailState


class WorkflowSection(DetailState):
    """The workflow rail and the section cards it navigates to."""

    def _on_workflow_step(self, key: str) -> None:
        """Navigate the rail only — never run a download, check or export.

        The rail has exactly three buttons (dv-gs5): Dataset Checks, File
        Checks and Response. The first two jump the Review page to their
        heading; Response switches to the Response page.
        """
        try:
            self._log_action("nav_jump", key, {"step": str(key)})
        except Exception:
            pass
        try:
            if key == "response":
                self._show_response_page()
                return
            self._show_review_page()
            if key == "file_checks":
                self._goto_section("_file_checks_heading")
                if self._dl_btn is not None:
                    self._dl_btn.setFocus()
            else:  # dataset_checks
                self._goto_section("_dataset_checks_heading")
                if self._check_btn is not None:
                    self._check_btn.setFocus()
        except Exception:
            pass

    def _refresh_workflow(self) -> None:
        """Refresh the verdict and follow-up banners (the rail is fixed).

        The rail is three plain navigation buttons (dv-gs5); it no longer
        derives steps from workflow state, so this method only refreshes the
        remaining state-dependent chrome.
        """
        try:
            self._refresh_check_button()
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
        """Retired: the mechanical/curated toggle is gone with the six-step rail."""
