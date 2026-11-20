"""The File Manifest card: the files, the tree, the filters and the download state."""

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QVBoxLayout,
    QWidget,
)

from ui import dialogs
from ui.dataset.helpers import (
    _human_size,
    _manifest_display_for_entry,
)
from ui.dataset.state import DetailState
from ui.i18n import t

if TYPE_CHECKING:
    from ui.preview import PreviewCard

from ui.status_text import status_text
from ui.theme import (
    SURFACE_PAGE,
    SURFACE_SUBTLE,
    band_qss,
    transparent_surface_qss,
)
from ui.widgets import (
    AppTree,
    add_info_tip,
    fit_tree_height,
    make_action_button,
    make_card,
    make_combo,
    make_elided_label,
    make_reset_columns_button,
    make_search_field,
    make_small_body_label,
)


class FilesSection(DetailState):
    """The File Manifest card: the files, the tree, the filters and the download state."""

    def _build_file_manifest_card(self) -> QFrame:
        card, _body_unused, _title, header_lay = make_card(t("detail.sections.file_manifest"))
        add_info_tip(
            header_lay,
            t("detail.files.tip"),
            name=t("detail.sections.file_manifest"),
            group="Queue",
        )
        _body_unused.setContentsMargins(0, 0, 0, 0)
        _body_unused.setSpacing(0)
        # Actions are tools: they live on the tools row under the title bar,
        # never in the title bar (title + tooltip + summary only).
        self._open_folder_btn = make_action_button(
            t("detail.files.open_folder"), kind="secondary", size="md"
        )
        self._open_folder_btn.setToolTip(t("detail.files.open_folder_tip"))
        self._open_folder_btn.clicked.connect(self._on_open_folder)
        # Expand/Collapse all toggle for the folder > file > check tree.
        self._expand_btn = make_action_button(
            t("detail.files.expand_all"), kind="secondary", size="md"
        )
        self._expand_btn.setToolTip(t("detail.files.expand_tip"))
        self._expand_btn.clicked.connect(self._on_toggle_expand_all)
        lay = QVBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # The title bar carries title + (i) only; every tool - search,
        # status filter, reset, Open folder, Expand all - sits on this row.
        tools = QWidget()
        tools.setObjectName("FileManifestTools")
        tools.setStyleSheet(transparent_surface_qss("FileManifestTools"))
        tools_lay = QHBoxLayout(tools)
        tools_lay.setContentsMargins(16, 8, 16, 8)
        tools_lay.setSpacing(8)
        self._file_filter = make_search_field(
            t("detail.files.filter_placeholder"), height=36, min_width=140
        )
        self._file_filter.setAccessibleName(t("detail.files.filter_placeholder"))
        self._file_filter.textChanged.connect(self._on_file_filter)
        tools_lay.addWidget(self._file_filter, 1)
        self._scan_filter = make_combo(
            [
                (label, key)
                for label, key in [
                    (t("detail.files.filter_all"), "all"),
                    (t("detail.files.filter_issues"), "issues"),
                    (t("detail.files.filter_errors"), "errors"),
                    (t("detail.files.filter_warnings"), "warnings"),
                    (t("detail.files.filter_skipped"), "skipped"),
                    (t("detail.files.filter_clean"), "clean"),
                    (t("detail.files.filter_no_check"), "unchecked"),
                ]
            ],
            height=36,
            min_width=130,
        )
        self._scan_filter.currentIndexChanged.connect(lambda _i: self._apply_file_filter_internal())
        tools_lay.addWidget(self._scan_filter)
        # Variable-dictionary draft (dv-tfy): one CSV per tabular file from
        # the variable metadata the coverage check fetched.
        self._dictionary_btn = make_action_button(
            t("detail.dictionary.action"), kind="secondary", size="md"
        )
        self._dictionary_btn.setToolTip(t("detail.dictionary.tip"))
        self._dictionary_btn.clicked.connect(self._on_draft_dictionary)
        tools_lay.addWidget(self._dictionary_btn)
        # Reset columns button - restores default widths/order
        self._file_reset_btn = make_reset_columns_button(
            "",
            tip=t("detail.files.reset_columns_tip"),
            accessible_name=t("detail.files.reset_columns_a11y"),
            fallback_text=t("common.reset"),
        )
        self._file_reset_btn.clicked.connect(self._on_reset_file_view)
        tools_lay.addWidget(self._file_reset_btn)
        tools_lay.addWidget(self._open_folder_btn)
        tools_lay.addWidget(self._expand_btn)
        lay.addWidget(tools)
        # NOTE: tree + footer live in a flush sub-layout so the header keeps
        # its top radius and the footer keeps its bottom radius.
        cast(QVBoxLayout, card.layout()).addLayout(lay)

        # Tree: folder > file > check hierarchy (Carbon-inspired, native QTreeView).
        # Column 0 carries the tree (caret + indent + icons); Size/Format/Scan
        # mirror the old table columns. Check nodes show the full untruncated
        # message; details live in the tooltip.
        # AppTree: the standard header chrome (square top-left flush with the
        # card's top bar, transparent scrollbar lanes so the vertical
        # scrollbar starts below the header row, themed header sections).
        self._file_tree = AppTree(row_height=30, flush=True)
        self._file_tree.clicked.connect(self._on_tree_clicked)
        self._file_tree.expanded.connect(self._on_tree_expansion_changed)
        self._file_tree.collapsed.connect(self._on_tree_expansion_changed)
        # Right-click a check node to set its disposition (dv-32x).
        self._file_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._file_tree.customContextMenuRequested.connect(self._on_file_context_menu)
        # No internal scrollbars: the manifest card grows to fit every
        # visible row and the page canvas scrolls instead.
        self._file_tree.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._file_tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lay.addWidget(self._file_tree, 1)
        # Compat alias: old code paths referenced _file_table; keep a None
        # placeholder so stray attribute access fails loudly, not silently.
        self._file_table = None

        # Footer: showing X of Y + total size
        footer = QFrame()
        footer.setStyleSheet(band_qss(SURFACE_PAGE, SURFACE_SUBTLE, edge="top"))
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(16, 10, 16, 10)
        # Both footer labels elide: "No files yet - load metadata to see
        # the Dataverse file list." is a long sentence, and a label that
        # cannot wrap would set the card's minimum width for the whole
        # card (the page then scrolls sideways).
        self._file_footer_left = make_elided_label(t("detail.files.no_files"), object_name="BodySM")
        fl.addWidget(self._file_footer_left, 1)
        fl.addStretch()
        # The file section's own summary: checks across report.files[], not
        # the dataset-level totals in the Automated checks card (dv-yg6).
        self._file_checks_summary = make_small_body_label("", wrap=False)
        fl.addWidget(self._file_checks_summary, 0)
        self._file_footer_right = make_small_body_label("", wrap=False)
        fl.addWidget(self._file_footer_right, 0)
        lay.addWidget(footer)

        # Hidden checks list for compatibility (was QListWidget; now we show inline)
        # Keep _file_checks as simple list for optional advanced view
        self._file_checks_data: dict[str, list[Any]] = {}
        return card

    def _update_file_checks_summary(self) -> None:
        """Return a file-checks summary built from per-file results only."""
        try:
            from engine.status import summarize

            report = getattr(self, "_report", None)
            checks = [c for f in report.files for c in f.checks] if report is not None else []
            if not checks:
                self._file_checks_summary.setText("")
                return
            summary = summarize(checks)
            self._file_checks_summary.setText(
                t(
                    "detail.auto_checks.summary_counts",
                    passed=summary["passed"],
                    warnings=summary["failed-warning"],
                    errors=summary["failed-error"],
                    skipped=summary["skipped"],
                )
            )
        except Exception:
            self._file_checks_summary.setText("")

    def _refresh_files_placeholder(self) -> None:
        # Note: Run checks / Export stay enabled at all times — without
        # staged files or a report they explain themselves via dialogs.
        # Prefer the inventory view whenever we have one: canonical
        # Dataverse paths plus a per-file staged checkmark. The raw staged
        # listing is only a fallback when no inventory was ever loaded
        # (its basenames can differ from directoryLabel paths).
        staged = self._dl_mgr.files_dir(self._pid)
        if self._inventory:
            self._populate_from_inventory()
            try:
                n_staged = sum(
                    1 for _r in getattr(self, "_all_file_rows", []) if self._is_staged(_r[0])
                )
                if staged.exists():
                    self._set_status(
                        t(
                            "detail.status.inventory_summary",
                            count=len(self._all_file_rows),
                            staged=n_staged,
                            path=staged,
                        )
                    )
            except Exception:
                pass
        elif staged.exists():
            files = sorted(p for p in staged.rglob("*") if p.is_file())
            self._populate_file_table_staged(files)
            self._set_status(t("detail.status.staged", count=len(files), path=staged))
        else:
            from ui.checks_tree import build_tree_model

            self._file_tree.setModel(build_tree_model([], None))
            self._file_footer_left.setText(t("detail.files.no_files_hint"))
            self._file_checks_summary.setText("")
            self._file_footer_right.setText("")
        self._refresh_curation_preview()
        self._refresh_workflow()

    def _populate_file_table_staged(self, files: list[Path]) -> None:
        import mimetypes

        self._all_file_rows = []
        for path in files:
            try:
                rel = (
                    path.relative_to(self._dl_mgr.files_dir(self._pid)).as_posix()
                    if path.is_relative_to(self._dl_mgr.files_dir(self._pid))
                    else path.name
                )
            except (ValueError, OSError):
                rel = path.name
            mime = mimetypes.guess_type(path.name)[0] or ""
            try:
                size = path.stat().st_size
            except OSError:
                continue
            ext = (
                Path(rel).suffix.lower().lstrip(".").upper()
                or mime.split("/")[-1].upper()
                or "FILE"
            )
            self._all_file_rows.append((rel, size, ext, rel))
        self._staged_files = files
        self._apply_file_filter_internal()
        # Staged fallback: every listed file is on disk by construction, so
        # the File checks action reads "Verify Files" (dv-gs5).
        try:
            self._dl_btn.setText(t("detail.header.verify_files"))
            self._dl_btn.setToolTip(t("detail.header.verify_files_tip"))
        except Exception:
            pass

    def _populate_from_inventory(self) -> None:
        total = 0
        for e in self._inventory if isinstance(self._inventory, list) else []:
            if not isinstance(e, dict):
                continue
            inv_path = str(e.get("path", "") or "")
            if not inv_path:
                continue
            display, size, fmt = _manifest_display_for_entry(e)
            total += size
            # Row 4th element keeps the inventory (.tab) path so tooltips can
            # name the server derivative behind a displayed original.
            self._all_file_rows.append((display, size, fmt, inv_path))
        self._apply_file_filter_internal()

    def _set_file_row(
        self, row: int, path: str, size: int, fmt: str, scan: str, downloaded: bool = False
    ) -> None:
        # Legacy table API removed with the tree view; kept as a no-op guard
        # so any external callers fail gracefully during migration.
        return None

    def _is_staged(self, path: str) -> bool:  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
        """Check whether the inventory path is staged locally.

        Checks the exact directoryLabel path first, then falls back to a
        basename match anywhere under files_dir: server bundles have not
        always preserved subfolders, and without the fallback every file
        reads as "not downloaded" (and Download All re-prompts forever).
        Uses a cached name set (no per-row tree walk, glob-safe).
        """
        try:
            root = self._dl_mgr.files_dir(self._pid)
            if not path:
                return False
            try:
                direct = self._dl_mgr._contained(root, path)
            except Exception:
                direct = None
            try:
                if direct is not None and direct.is_file():
                    return True
            except OSError:
                pass
            base = Path(path).name
            if not base:
                return False
            # Cached staged-name set built by _refresh_download_state /
            # _populate_* (avoids O(files × walk) rglob(base) which also
            # misbehaves on names with *?[] glob chars).
            cached = getattr(self, "_staged_names_cache", None)
            if isinstance(cached, set):
                return base in cached
            try:
                if not root.exists():
                    return False
                for candidate in root.rglob("*"):
                    try:
                        if candidate.is_file() and candidate.name == base:
                            return True
                    except OSError:
                        continue
            except OSError:
                return False
            return False
        except Exception:
            return False

    def _refresh_download_state(self) -> None:
        """Reflect staged state on the File checks action button (dv-gs5).

        Nothing (or only part of the inventory) staged → "Download Dataset";
        every file staged → "Verify Files". The count stays in the tooltip
        so the button label never changes width with the inventory size.
        """
        # Rail inputs: counts are captured here (the single place that
        # already walks the staged folder) so _refresh_workflow never stats.
        self._staged_n = 0
        self._staged_total = 0
        try:
            btn = getattr(self, "_dl_btn", None)
            if btn is None:
                self._refresh_workflow()
                return
            rows = getattr(self, "_all_file_rows", []) or []
            if not rows:
                btn.setText(t("detail.header.download_all"))
                btn.setToolTip(t("detail.header.download_dataset_tip"))
                self._refresh_workflow()
                return
            root = self._dl_mgr.files_dir(self._pid)
            staged_paths: set[str] = set()
            staged_names: set[str] = set()
            try:
                if root.exists():
                    for p in root.rglob("*"):
                        try:
                            if p.is_file():
                                staged_names.add(p.name)
                                try:
                                    staged_paths.add(p.relative_to(root).as_posix())
                                except (ValueError, OSError):
                                    pass
                        except OSError:
                            continue
            except OSError:
                pass
            # Cache for _is_staged fast path (avoids per-row walks).
            try:
                self._staged_names_cache = set(staged_names)
                self._staged_paths_cache = set(staged_paths)
            except Exception:
                pass
            n_staged = sum(
                1
                for (path, _s, _f, _o) in rows
                if (path in staged_paths) or (Path(path).name in staged_names)
            )
            total = len(rows)
            self._staged_n = n_staged
            self._staged_total = total
            # Header grammar: text-only major action in every state; the
            # count in the label ("Downloaded (N)") is the status cue.
            if total and n_staged >= total:
                btn.setText(t("detail.header.verify_files"))
                btn.setToolTip(t("detail.header.verify_files_tip"))
            else:
                btn.setText(t("detail.header.download_all"))
                btn.setToolTip(
                    t(
                        "detail.files.staged_tip",
                        staged=n_staged,
                        total=total,
                    )
                    if n_staged
                    else t("detail.header.download_dataset_tip")
                )
        except Exception:
            pass
        self._refresh_workflow()

    def _on_open_folder(self) -> None:
        """Open the staged download folder in the desktop file explorer."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        staged = self._dl_mgr.files_dir(self._pid)
        target = staged if staged.exists() else self._dl_mgr.dataset_dir(self._pid)
        if not target.exists():
            dialogs.show_info(
                self,
                t("detail.files.open_folder"),
                t("detail.files.open_folder_nothing"),
            )
            return
        try:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target.resolve())))
        except Exception as exc:
            dialogs.show_warning(
                self,
                t("detail.files.open_folder"),
                t("detail.files.could_not_open", path=target, exc=exc),
            )

    def _on_file_filter(self, text: str) -> None:
        self._apply_file_filter_internal()

    def _apply_file_filter_internal(self) -> None:  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
        from engine.status import classify
        from ui.checks_tree import build_tree_model, matches_status_filter

        filt = (self._file_filter.text() or "").lower().strip()
        try:
            status_filt = self._scan_filter.currentData() or "all"
        except Exception:
            status_filt = "all"
        all_rows = list(getattr(self, "_all_file_rows", []))
        by_path = {}
        if self._report is not None:
            by_path = {f.path: f for f in self._report.files}

        def _row_badges(path: str) -> list[str]:
            entry = by_path.get(path)
            if not entry or not entry.checks:
                return []
            return [classify(c) for c in entry.checks]

        def _scan_text(path: str) -> str:
            entry = by_path.get(path)
            if self._report is None:
                return ""
            if entry is None:
                return t("detail.files.not_in_report")
            if not entry.checks:
                return t("detail.files.no_automated_check")

            return status_text(entry.checks)

        rows = []
        for r in all_rows:
            path = r[0]
            if filt and filt not in path.lower():
                # Keep a file if one of its check messages matches.
                entry = by_path.get(path)
                hay = " ".join(
                    (c.check_id + " " + c.message).lower() for c in (entry.checks if entry else [])
                )
                if filt not in hay:
                    continue
            if not matches_status_filter(_scan_text(path), _row_badges(path), status_filt):
                continue
            rows.append(r)
        model = build_tree_model(
            rows,
            self._report,
            self._is_staged,
            _human_size,
            inventory=self._inventory if isinstance(self._inventory, list) else None,
            dispositions=self._dispositions_map(),
        )
        # The header's signals are blocked while the tree is rebuilt and
        # the columns are fitted to their content: sectionResized persists
        # the layout, so an auto-fit would overwrite the widths the user
        # saved before the restore below can apply them.
        layout = self._layout_for("dataset_files", self._file_tree.header())
        with layout.suppressed():
            try:
                self._file_tree.setModel(model)
                self._file_tree.expandToDepth(0)
                # Auto-expand files with issues so findings are visible.
                issue_prefixes = (t("status.error"), t("status.warning"))
                for r in range(model.rowCount()):
                    folder = model.item(r, 0)
                    if folder is not None and folder.hasChildren():
                        for i in range(folder.rowCount()):
                            scan = folder.child(i, 3).text() if folder.child(i, 3) else ""
                            if scan.startswith(issue_prefixes):
                                idx = model.index(i, 0, model.index(r, 0))
                                self._file_tree.expand(idx)
                    else:
                        scan = model.item(r, 3).text() if model.item(r, 3) else ""
                        if scan.startswith(issue_prefixes):
                            self._file_tree.expand(model.index(r, 0))
                # Size every column to its content (Name keeps a 260px
                # floor; Size/Format/Scan need real width too, or long
                # formats like application/x-spss-sav get truncated).
                self._file_tree.fit_columns_to_contents(floors={0: 260})
                self._sync_tree_carets()
            except Exception:
                pass
        total = sum(r[1] for r in all_rows)
        self._file_footer_left.setText(
            t(
                "detail.files.showing",
                shown=len(rows),
                total=len(all_rows),
            )
        )
        self._file_footer_right.setText(
            t("detail.files.total_size", size=_human_size(total)) if total else ""
        )
        self._update_file_checks_summary()
        self._refresh_download_state()
        self._update_expand_btn()
        # Re-apply the saved layout (the user's widths win over the fit).
        self._track_table_widths("dataset_files", self._file_tree.header())
        self._fit_file_tree_height()

    def _on_tree_expansion_changed(self, _index: QModelIndex | None = None) -> None:
        self._sync_tree_carets()
        self._update_expand_btn()
        self._fit_file_tree_height()

    def _fit_file_tree_height(self) -> None:
        """Grow the manifest tree to its visible rows (no inner scroll).

        The tree lives on the page's scroll canvas, so an inner scrollbar
        only traps the wheel. Delegates to the kit's content-fit helper
        (the same one the review-config checks tree uses).
        """
        fit_tree_height(self._file_tree, row_height=30, floor=80)

    def _sync_tree_carets(self) -> None:
        """Re-sync folder icons with the manifest tree's expanded state."""
        try:
            from ui.checks_tree import update_carets

            model = self._file_tree.model()
            if model is not None:
                update_carets(model, self._file_tree.isExpanded)
        except Exception:
            pass

    def _tree_has_collapsed(self) -> bool:
        """Check whether any expandable manifest node is currently collapsed."""
        try:
            model = self._file_tree.model()
            if model is None or model.rowCount() == 0:
                return False
            stack = [self._file_tree.rootIndex()]
            while stack:
                parent = stack.pop()
                for r in range(model.rowCount(parent)):
                    idx = model.index(r, 0, parent)
                    if model.hasChildren(idx):
                        if not self._file_tree.isExpanded(idx):
                            return True
                        stack.append(idx)
            return False
        except Exception:
            return False

    def _update_expand_btn(self) -> None:
        """Keep the toggle label in sync with the tree's real state."""
        try:
            self._expand_btn.setText(
                t("detail.files.collapse_all")
                if not self._tree_has_collapsed()
                else t("detail.files.expand_all")
            )
        except Exception:
            pass

    def _on_toggle_expand_all(self) -> None:
        """Expand every node when any is collapsed; otherwise collapse all."""
        try:
            if self._tree_has_collapsed():
                self._file_tree.expandAll()
            else:
                self._file_tree.collapseAll()
            self._sync_tree_carets()
            self._update_expand_btn()
            self._fit_file_tree_height()
        except Exception:
            pass

    def _on_reset_file_view(self) -> None:
        try:
            self._reset_table_view("dataset_files", self._file_tree.header())
            self._apply_file_filter_internal()
        except Exception:
            pass

    def _on_file_selected(self, row: int, _col: int) -> None:
        # Legacy table slot (pre-tree). Kept so old signal wiring fails
        # loudly in one place instead of scattered AttributeErrors.
        return None

    def _on_draft_dictionary(self) -> None:  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
        """Write a variable-dictionary draft CSV for one tabular file (dv-tfy)."""
        from PySide6.QtWidgets import QFileDialog

        from engine.checks.varmeta_check import write_dictionary_draft

        variables_by_path: dict[str, dict[str, Any]] = {}
        if self._report is not None:
            for check in getattr(self._report, "dataset_checks", []) or []:
                if getattr(check, "check_id", "") != "metadata.var_coverage":
                    continue
                vmap = (getattr(check, "details", {}) or {}).get("variables")
                if isinstance(vmap, dict):
                    variables_by_path = {
                        str(path): vars_
                        for path, vars_ in vmap.items()
                        if isinstance(vars_, dict) and vars_
                    }
                break
        # No report yet (or the check skipped the fetch): ask Dataverse
        # directly for the tabular files, best effort, capped like the worker.
        if not variables_by_path and self._client is not None and isinstance(self._inventory, list):
            for entry in self._inventory[:50]:
                if not isinstance(entry, dict) or not entry.get("tabular"):
                    continue
                if not entry.get("id"):
                    continue
                try:
                    meta = self._client.get_variable_metadata(str(entry["id"]))
                except Exception:
                    meta = None
                if isinstance(meta, dict) and meta:
                    path = str(entry.get("path") or entry.get("label") or "")
                    variables_by_path[path] = meta
        options = sorted(variables_by_path)
        if not options:
            dialogs.show_info(
                self,
                t("detail.dictionary.action"),
                t("detail.dictionary.none"),
            )
            return
        chosen = options[0]
        if len(options) > 1:
            chosen, ok = QInputDialog.getItem(
                self,
                t("detail.dictionary.pick_title"),
                t("detail.dictionary.pick_label"),
                options,
                0,
                False,
            )
            if not ok or not chosen:
                return
        variables = variables_by_path.get(chosen) or {}
        if not variables:
            dialogs.show_info(
                self,
                t("detail.dictionary.action"),
                t("detail.dictionary.none"),
            )
            return
        try:
            self._dl_mgr.reports_dir(self._pid).mkdir(parents=True, exist_ok=True)
            start = str(
                self._dl_mgr.reports_dir(self._pid)
                / (f"{Path(chosen).stem or 'variables'}-dictionary.csv")
            )
            path, _ = QFileDialog.getSaveFileName(
                self,
                t("detail.dictionary.save_title"),
                start,
                t("detail.dictionary.csv_filter"),
                options=QFileDialog.Option.DontUseNativeDialog,
            )
        except Exception as exc:
            dialogs.show_critical(
                self,
                t("detail.dictionary.action"),
                t("detail.dictionary.failed", exc=exc),
            )
            return
        if not path:
            return
        try:
            out = write_dictionary_draft(Path(path), variables)
        except Exception as exc:
            dialogs.show_warning(
                self,
                t("detail.dictionary.action"),
                t("detail.dictionary.failed", exc=exc),
            )
            return
        self._set_status(t("detail.dictionary.saved", path=str(out)), tone="success")
        self._log_action(
            "dictionary_drafted",
            t("detail.dictionary.saved_log", name=out.name),
            {"path": str(out), "file": chosen, "variables": len(variables)},
        )

    def _build_preview_card(self) -> "PreviewCard":
        """Sidebar file preview (dv-koz): the head of the clicked manifest file."""
        from ui.preview import PreviewCard

        return PreviewCard(on_open_folder=self._on_open_folder, parent=self)

    def _show_preview_for_file(self, path: str) -> None:
        """Route a manifest click into the preview card (dv-koz)."""
        try:
            staged = self._dl_mgr.files_dir(self._pid)
        except Exception:
            staged = None
        if self._preview_card is None:
            return
        candidate = (Path(staged) / path) if staged else Path(path)
        try:
            if candidate.is_file():
                kind = self._preview_card.set_path(candidate, rel=path)
            else:
                kind = self._preview_card.set_not_staged(rel=path)
        except Exception:
            kind = "error"
        try:
            self._log_action(
                "preview_rendered",
                path,
                {"path": str(path), "kind": str(kind)},
            )
        except Exception:
            pass
