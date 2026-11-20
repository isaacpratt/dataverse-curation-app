"""Loading the dataset's metadata: the worker, the profile switch and the errors."""

from typing import Any

from ui import dialogs
from ui.dataset.helpers import _format_metadata
from ui.dataset.state import DetailState
from ui.i18n import t
from ui.workers import MetadataWorker


class MetadataLoadSection(DetailState):
    """Loading the dataset's metadata: the worker, the profile switch and the errors."""

    def _on_metadata_error(self, msg: str) -> None:
        self._meta_worker = None
        self._progress.setVisible(False)
        self._load_meta_btn.setEnabled(True)
        self._set_status("")
        headline, details = dialogs.describe_error(msg)
        dialogs.show_critical(
            self,
            t("detail.metadata_load.title"),
            headline,
            details=details,
            retry=self._on_load_metadata,
        )

    def _on_load_metadata(self) -> None:
        # The worker deletes itself (deleteLater) when it finishes or
        # errors, which can leave a stale Python reference to a dead C++
        # object; calling isRunning() on it raised
        # "Internal C++ object already deleted". Drop the stub instead.
        worker = self._meta_worker
        if worker is not None:
            try:
                if worker.isRunning():
                    self._set_status(t("detail.status.metadata_load_running"))
                    return
            except RuntimeError:
                self._meta_worker = None
        self._load_meta_btn.setEnabled(False)
        self._set_status(t("detail.status.loading_metadata"))
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)
        try:
            _collection = (
                getattr(self._config.dataverse, "collection", "")
                or getattr(self._config.dataverse, "subtree", "")
                or ""
            )
        except Exception:
            _collection = ""
        self._meta_worker = MetadataWorker(
            self._config.dataverse.base_url,
            self._config.dataverse.api_token,
            self._pid,
            self,
            collection=_collection,
            draft_hint=self._draft_hint(),
        )
        self._meta_worker.finished.connect(self._on_metadata_finished)
        self._meta_worker.error.connect(self._on_metadata_error)
        self._meta_worker.finished.connect(self._meta_worker.deleteLater)
        self._meta_worker.error.connect(self._meta_worker.deleteLater)
        self._meta_worker.start()

    def _on_metadata_finished(
        self,
        metadata: dict[str, Any],
        inventory: list[dict[str, Any]],
        curation: dict[str, Any] | None = None,
        version_diff: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        # Drop the reference before the worker's deleteLater runs; a stale
        # reference made the next Load metadata click crash with
        # "Internal C++ object (MetadataWorker) already deleted".
        self._meta_worker = None
        self._progress.setVisible(False)
        self._load_meta_btn.setEnabled(True)
        self._inventory = inventory if isinstance(inventory, list) else []
        self._metadata = metadata
        self._curation = curation if isinstance(curation, dict) else {}
        self._version_diff = version_diff if isinstance(version_diff, dict) else {}
        self._changes_loaded = True
        extra = extra if isinstance(extra, dict) else {}
        guestbook = extra.get("guestbook")
        self._guestbook = guestbook if isinstance(guestbook, dict) else None
        account = extra.get("account")
        self._account = account if isinstance(account, dict) else {}
        self._versions = extra.get("versions") if isinstance(extra.get("versions"), list) else []
        self._timestamps = (
            extra.get("timestamps") if isinstance(extra.get("timestamps"), dict) else {}
        )
        self._review_submissions = (
            extra.get("review_submissions")
            if isinstance(extra.get("review_submissions"), list)
            else []
        )
        self._in_review = bool(extra.get("in_review", False))
        self._update_header_link(metadata)
        self._update_curation_pill()
        self._refresh_header_actions()
        self._populate_version_diff()
        self._refresh_decision_options()
        self._refresh_sensitivity_card()
        self._raw_view.setPlainText(_format_metadata(metadata))
        self._populate_completeness(metadata)
        self._note_follow_up_update()
        self.metadataLoaded.emit(self._pid, metadata, self._inventory)
        self._refresh_curation_preview()
        self._refresh_dataset_log()
        inv_failed = bool(extra.get("inventory_failed", False))
        self._inventory_ok = not inv_failed
        refusal: dict[str, Any] = {}
        try:
            refusals = extra.get("refusals")
            if isinstance(refusals, dict):
                refusal = refusals.get("inventory") or {}
        except Exception:
            refusal = {}
        not_readable = str((refusal or {}).get("reason") or "") == "draft_not_readable"
        if not inv_failed:
            try:
                from curation.storage import write_size_entry

                write_size_entry(
                    self._config.app.workspace,
                    self._pid,
                    sum(int(f.get("size_bytes", 0) or 0) for f in self._inventory),
                    len(self._inventory),
                )
            except Exception:
                pass
            # Persist metadata + manifest beside the downloads for next launch.
            # Skipped on inventory failure so a good cache is never clobbered.
            try:
                self._dl_mgr.save_metadata(self._pid, metadata, self._inventory)
            except Exception:
                pass
        self._log_action(
            "metadata_loaded" if not inv_failed else "metadata_failed",
            t("detail.status.inventory_count", count=len(self._inventory))
            if not inv_failed
            else (
                t("detail.status.file_list_not_readable_short")
                if not_readable
                else t("detail.status.file_list_failed_short")
            ),
            {"file_count": len(self._inventory)},
        )
        if inv_failed:
            # Network/auth failure is not an empty dataset — say so plainly
            # and offer the retry instead of implying zero files.
            from ui.checks_tree import build_tree_model as _btm

            if not_readable:
                # The server refused because this account is not in the
                # dataset's curation scope — an expected answer, not a
                # broken load.
                self._set_status(t("detail.status.file_list_not_readable"))
                self._file_tree.setModel(_btm([], None))
                self._all_file_rows = []
                self._file_footer_left.setText(t("detail.status.file_list_not_readable_footer"))
                self._file_footer_right.setText("")
            else:
                self._set_status(t("detail.status.file_list_failed"), tone="error")
                self._file_tree.setModel(_btm([], None))
                self._all_file_rows = []
                self._file_footer_left.setText(t("detail.status.file_list_failed_footer"))
                self._file_footer_right.setText("")
        elif self._inventory:
            self._populate_from_inventory()
            self._set_status(
                t(
                    "detail.status.metadata_loaded",
                    count=len(self._inventory),
                )
            )
        else:
            # Metadata loaded fine but the version genuinely has zero files —
            # say so plainly instead of implying a fetch failure.
            version_state = ""
            try:
                version_state = (
                    (metadata.get("latestVersion") or {}).get("versionState") or ""
                ).upper()
            except Exception:
                pass
            ver_note = (
                t("detail.status.version_note", version=version_state.title())
                if version_state
                else ""
            )
            self._set_status(t("detail.status.no_files_version", version=ver_note))
            from ui.checks_tree import build_tree_model as _btm2

            self._file_tree.setModel(_btm2([], None))
            self._all_file_rows = []
            self._file_footer_left.setText(t("detail.files.no_files_in_dataverse"))
            self._file_footer_right.setText("")
        self._refresh_workflow()

    def _on_profile_changed(self) -> None:
        key = self._profile_combo.currentData()
        if isinstance(key, str):
            self._profile = key
        if self._metadata is not None:
            self._populate_completeness(self._metadata)

    def _draft_hint(self) -> bool | None:
        """Whether this dataset is under curation, as the queue row knew.

        True/False when the dashboard row says so, None when it does not
        (the detail view then asks for everything). A row whose access the
        account does not have counts as "not under curation" for the
        purpose of skipping reads: those reads would be refused anyway.
        """
        try:
            hint = self._dataset_hint or {}
            if not hint:
                return None
            access = hint.get("access")
            if isinstance(access, dict):
                state = str(access.get("state") or "")
                if state and state != "readable":
                    return False
            if "has_draft" in hint:
                return bool(hint.get("has_draft"))
            state = str(hint.get("state") or "").upper()
            if not state:
                return None
            return state == "DRAFT" or "REVIEW" in state
        except Exception:
            return None
