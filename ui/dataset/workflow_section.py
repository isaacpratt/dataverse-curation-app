"""The workflow rail and the section cards it navigates to."""

from PySide6.QtWidgets import QFrame

from ui.dataset.helpers import _SECTION_LINKS
from ui.dataset.state import DetailState
from ui.i18n import t
from ui.theme import ACCENT_PRIMARY
from ui.widgets import make_action_button, make_card


class WorkflowSection(DetailState):
    """The workflow rail and the section cards it navigates to."""

    def _build_nav_card(self) -> QFrame:
        """Sidebar section navigation — jumps the main column to each box."""
        from ui.icons import icon as _nav_icon

        card, body, _title, header = make_card(t("detail.sections.title"))
        body.setSpacing(6)
        # Collapse the sidebar. On a narrow window the 280px it holds
        # squeezes the main column (the File Manifest tree) below a
        # usable width, so the sidebar folds away and its links move
        # into the top bar's Sections menu.
        self._sidebar_collapse_btn = make_action_button("", kind="ghost", size="sm")
        try:
            self._sidebar_collapse_btn.setIcon(_nav_icon("chevron-right", color=ACCENT_PRIMARY))
        except Exception:
            pass
        self._sidebar_collapse_btn.setToolTip(t("detail.sidebar.collapse_tip"))
        self._sidebar_collapse_btn.setAccessibleName(t("detail.sidebar.collapse_a11y"))
        self._sidebar_collapse_btn.clicked.connect(self._toggle_sidebar)
        header.addWidget(self._sidebar_collapse_btn)
        self._nav_buttons: list = []
        for key, attr in _SECTION_LINKS:
            label = t(key)
            btn = make_action_button(label, kind="link", size=None)
            try:
                btn.setIcon(_nav_icon("arrow-right", color=ACCENT_PRIMARY))
            except Exception:
                pass
            btn.clicked.connect(lambda _c, a=attr: self._goto_section(a))
            body.addWidget(btn)
            self._nav_buttons.append(btn)
        return card

    def _on_workflow_step(self, key: str) -> None:
        """Navigate the rail only — never run a download, check or export."""
        try:
            if key == "respond":
                self._show_response_page()
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
            from ui.workflow import WorkflowInput, derive_workflow

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
            )
            self._rail.set_workflow(derive_workflow(state))
        except Exception:
            pass
