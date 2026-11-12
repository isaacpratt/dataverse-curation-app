"""Background workers for network and engine tasks."""

import atexit
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ui.i18n import t
from ui.progress import (
    PHASE_DISCOVERY,
    PHASE_ENRICHMENT,
    PHASE_LABELS,
    PHASE_LOCKS,
    phase_fraction,
)

# Parallelism for per-dataset confirmation calls (locks, label fallback).
# The client holds no shared session and applog is lock-guarded, so plain
# worker threads are safe; 8 keeps small instances fast without hammering.
_POOL_SIZE = 8

# Review-inbox scan cache: find_review_submissions re-reads up to 5 inbox
# pages, so memoize per (instance, dataset, token) for 10 minutes —
# reopening a dataset skips the rescan. Token hash is included so a token
# switch never reuses the prior user's inbox.
_INBOX_TTL_S = 600.0
_inbox_cache: dict = {}
_inbox_lock = __import__("threading").Lock()

# Every QThread the app starts is tracked here, so the process can stop
# them before teardown. A QThread destroyed while it is still running
# aborts the process (Qt prints "QThread: Destroyed while thread is
# still running" and calls abort), which is reachable when the user
# quits mid-scan and when an offscreen probe ends with a worker live.
_LIVE_WORKERS: set = set()


def register_worker(worker: QThread) -> None:
    """Track a QThread so the process can stop it before teardown."""
    _LIVE_WORKERS.add(worker)
    # Absorb the signal's payload: several workers emit `finished` with an
    # argument (dict, list, DatasetReport...). Without *args Qt would bind
    # that payload to `w` and `discard()` would raise TypeError
    # ("unhashable type: 'dict' / 'DatasetReport'").
    worker.finished.connect(lambda *_, w=worker: _LIVE_WORKERS.discard(w))
    # The app quitting is the clean path: stop the workers there, before
    # the application object (and the widgets holding the threads) dies.
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(stop_all_workers)
    except Exception:
        pass


def stop_all_workers(timeout_ms: int = 10000) -> None:
    """Stop every tracked worker and wait for it to finish.

    The workers check ``isInterruptionRequested()`` between steps, so
    they stop promptly rather than running their task to the end.
    """
    for worker in list(_LIVE_WORKERS):
        try:
            if worker.isRunning():
                worker.requestInterruption()
                worker.wait(timeout_ms)
        except Exception:
            pass
    _LIVE_WORKERS.clear()


# The process can end without a clean quit (a probe, a Ctrl+C in a
# console): stop the workers there too.
atexit.register(stop_all_workers)


def _inbox_key(base_url: str, pid: str, api_token: str) -> tuple:
    import hashlib

    try:
        token_hash = hashlib.sha256((api_token or "").encode("utf-8")).hexdigest()[:16]
    except Exception:
        token_hash = ""
    return (base_url, pid, token_hash)


class CrawlWorker(QThread):
    finished = Signal(list)
    error = Signal(str)
    progress = Signal(str)
    # Emitted alongside finished: the instance's curation-label set so the
    # dashboard can offer per-instance label filtering. Carried separately
    # because `finished(list)` signature is fixed.
    labelsDiscovered = Signal(list)
    # Emitted with the PURE probe result (never the filter union):
    # {"labels": [...], "probed": bool, "collection": str}. The dashboard
    # stamps the disk slot only when probed is True, so a cache hit can
    # never freeze an unverified union in place.
    allowedProbed = Signal(dict)
    # Emitted during dashboard enrichment with shallow copies of newly
    # enriched rows (batched): the dashboard merges them into the painted
    # table progressively so a 1300-row crawl never blocks the UI.
    enriched = Signal(list)
    # Emitted with the overall crawl fraction (0..1) for the progress
    # ring. Phased: discovery → enrichment → locks → labels. The value
    # is monotonic; a skipped phase jumps to the next phase's floor.
    progressFraction = Signal(float)

    # Dashboard enrichment bounds (approved scope): drafts first, capped,
    # sums-only, flushed to the table in batches.
    _ENRICH_MAX_ROWS = 200
    _ENRICH_WORKERS = 5
    _ENRICH_FLUSH_EVERY = 25

    def __init__(self, base_url: str, api_token: str, subtree: str, parent=None):
        super().__init__(parent)
        register_worker(self)
        self._base_url = base_url
        self._api_token = api_token
        self._subtree = subtree
        self._last_fraction = -1.0

    def _emit_fraction(self, value: float) -> None:
        """Emit a monotonic overall fraction for the progress ring.

        Never goes backwards (a later phase always has a higher floor),
        so the ring cannot visibly rewind.
        """
        try:
            frac = float(value)
        except (TypeError, ValueError):
            return
        if frac < 0.0:
            frac = 0.0
        elif frac > 1.0:
            frac = 1.0
        if frac <= self._last_fraction:
            return
        self._last_fraction = frac
        try:
            self.progressFraction.emit(frac)
        except Exception:
            pass

    def run(self) -> None:
        import traceback

        try:
            from applog import get_app_log
            from dataverse_client import STATE_IN_REVIEW, DataverseClient

            self.progress.emit(t("workers.connecting", base_url=self._base_url))
            client = DataverseClient(self._base_url, self._api_token)
            coll = self._subtree.strip() or t("workers.whole_repository")
            self.progress.emit(t("workers.fetching_all", collection=coll))
            self._emit_fraction(phase_fraction(PHASE_DISCOVERY, 0, 0))

            def _on_discovery_page(page: int, pages_total: int, collected: int) -> None:
                # Discovery is total-driven: pages_total is known after the
                # first page, so the ring can show real progress.
                try:
                    if pages_total > 0:
                        self.progress.emit(
                            t(
                                "workers.fetching_page",
                                page=page,
                                pages=pages_total,
                                found=collected,
                            )
                        )
                        self._emit_fraction(
                            phase_fraction(PHASE_DISCOVERY, page, pages_total)
                        )
                    else:
                        self.progress.emit(
                            t("workers.fetching_found", found=collected)
                        )
                        self._emit_fraction(
                            phase_fraction(PHASE_DISCOVERY, collected, 0)
                        )
                except Exception:
                    pass

            datasets = client.list_draft_datasets(
                self._subtree,
                progress=_on_discovery_page,
                is_cancelled=self.isInterruptionRequested,
            )
            if self.isInterruptionRequested():
                return
            # Dashboard enrichment: patch thin search rows with live
            # inventory sums + depositor + authoritative state (drafts
            # first, capped, cancellable). The locks stage below still owns
            # the "In Review" state — enrichment never clobbers it.
            try:
                total_rows = len(datasets)
                if total_rows:
                    self.progress.emit(
                        t("workers.enriching", count=total_rows)
                    )
                emitted: set = set()
                pending_batch: list = []

                def _on_enrich_progress(done: int, total: int) -> None:
                    try:
                        self.progress.emit(
                            t("workers.enriching_progress", done=done, total=total)
                        )
                        self._emit_fraction(
                            phase_fraction(PHASE_ENRICHMENT, done, total)
                        )
                    except Exception:
                        pass
                    # Progressive paint: hand newly enriched rows to the
                    # dashboard every _ENRICH_FLUSH_EVERY completions (plus
                    # the tail), as shallow copies — the worker keeps the
                    # live dicts for the final finished() payload.
                    try:
                        for d in datasets:
                            try:
                                pid = str(d.get("persistent_id") or "")
                            except Exception:
                                continue
                            if d.get("size_enriched") and pid and pid not in emitted:
                                pending_batch.append(d)
                                emitted.add(pid)
                        if pending_batch and (
                            len(pending_batch) >= CrawlWorker._ENRICH_FLUSH_EVERY
                            or done >= total
                        ):
                            self.enriched.emit([dict(d) for d in pending_batch])
                            pending_batch.clear()
                    except Exception:
                        pass

                enrich_stats = client.enrich_datasets_with_inventory(
                    datasets,
                    max_rows=CrawlWorker._ENRICH_MAX_ROWS,
                    max_workers=CrawlWorker._ENRICH_WORKERS,
                    progress=_on_enrich_progress,
                    is_cancelled=self.isInterruptionRequested,
                )
                if self.isInterruptionRequested():
                    return
                try:
                    rest = [
                        dict(d) for d in datasets
                        if d.get("size_enriched")
                        and str(d.get("persistent_id") or "") not in emitted
                    ]
                    if rest:
                        self.enriched.emit(rest)
                except Exception:
                    pass
                try:
                    n_enriched = int((enrich_stats or {}).get("enriched", 0))
                    n_pending = int((enrich_stats or {}).get("pending", 0))
                except Exception:
                    n_enriched, n_pending = 0, 0
                if n_enriched:
                    tail = (
                        t("workers.beyond_cap", count=n_pending)
                        if n_pending else ""
                    )
                    self.progress.emit(
                        t(
                            "workers.enriched",
                            count=n_enriched,
                            tail=tail,
                        )
                    )
            except Exception:
                pass
            # Search API versionState is only DRAFT/RELEASED — in-review state
            # lives in the locks endpoint, so confirm per dataset here.
            # Parallel: one locks call per dataset would take minutes serially.
            total = len(datasets)
            in_review_n = 0

            def _check_lock(ds: dict) -> tuple:
                try:
                    flag = bool(client.dataset_in_review(ds.get("persistent_id", "")))
                except Exception:
                    flag = False
                return ds, flag

            from concurrent.futures import as_completed

            with ThreadPoolExecutor(max_workers=_POOL_SIZE) as pool:
                futures = [pool.submit(_check_lock, ds) for ds in datasets]
                # as_completed avoids head-of-line blocking: one stalled
                # locks call no longer stalls all later results.
                done_n = 0
                for fut in as_completed(futures):
                    if self.isInterruptionRequested():
                        for f in futures:
                            f.cancel()
                        return
                    ds, flag = fut.result()
                    done_n += 1
                    if flag:
                        ds["state"] = STATE_IN_REVIEW
                        in_review_n += 1
                    if done_n % 10 == 0 or done_n == total:
                        self.progress.emit(
                            t(
                                "workers.checking_locks",
                                done=done_n,
                                total=total,
                                in_review=in_review_n,
                            )
                        )
                        self._emit_fraction(
                            phase_fraction(PHASE_LOCKS, done_n, total)
                        )
            # Curation labels are set at the Dataverse level. Superusers
            # pull them in bulk via the CSV report (one call for all
            # drafts). Non-superuser tokens 403 there, so for them the
            # identity probe (/api/users/:me) decides up front: skip the
            # doomed report call and read per-draft curationStatus only —
            # labels/status exist solely for datasets under curation, so
            # published/deaccessioned rows are never attempted.
            from dataverse_client import is_draft_dataset

            labels: list = []
            report = None
            # Labels phase starts here; the fraction advances as the
            # per-dataset reads or the bulk report complete.
            self._emit_fraction(phase_fraction(PHASE_LABELS, 0, 0))
            try:
                superuser = client.user_is_superuser()
            except Exception:
                superuser = None
            try:
                me = client.get_me() or {}
                who = (
                    str(me.get("displayName") or me.get("identifier") or "").strip()
                )
                if superuser is True:
                    who_display = who or t("workers.user_fallback")
                    self.progress.emit(
                        t("workers.connected_superuser", who=who_display)
                    )
                    get_app_log().info(
                        t("workers.identity_superuser", who=who_display)
                    )
                elif superuser is False:
                    who_display = who or t("workers.user_fallback")
                    self.progress.emit(
                        t("workers.connected_user", who=who_display)
                    )
                    get_app_log().info(
                        t("workers.identity_user", who=who_display)
                    )
            except Exception:
                pass
            if superuser is True:
                try:
                    report = client.list_curation_states()
                except Exception:
                    report = None
            elif superuser is False:
                report = None  # skip the doomed 403 entirely
            else:
                # Identity unknown (network): legacy try-then-fallback.
                try:
                    report = client.list_curation_states()
                except Exception:
                    report = None
            if report is not None:
                by_pid = {r["persistent_id"]: r for r in report if r.get("persistent_id")}
                by_title = {r["title"]: r for r in report if r.get("title")}
                for ds in datasets:
                    row = by_pid.get(ds.get("persistent_id", "")) or by_title.get(ds.get("title", ""))
                    if row:
                        ds["curation_label"] = row.get("label", "")
                        ds["curation_time"] = row.get("label_time", "")
                        ds["curation_assigner"] = row.get("assigner", "")
                    else:
                        ds["curation_label"] = ""
                        ds["curation_time"] = ""
                        ds["curation_assigner"] = ""
                for r in report:
                    if r.get("label") and r["label"] not in labels:
                        labels.append(r["label"])
                self.progress.emit(
                    t(
                        "workers.curation_report",
                        drafts=len(report),
                        labels=len(labels),
                    )
                )
                self._emit_fraction(phase_fraction(PHASE_LABELS, 1, 1))
                try:
                    get_app_log().info(
                        t(
                            "workers.curation_report_log",
                            labels=", ".join(
                                t("workers.labels_in_use", labels=lbl)
                                for lbl in labels
                            ) or t("common.none_in_parentheses"),
                        )
                    )
                except Exception:
                    pass
            else:
                def _read_status(ds: dict) -> tuple:
                    try:
                        status = client.get_curation_status(ds.get("persistent_id", ""))
                    except Exception:
                        status = None
                    return ds, status or {}

                # Drafts only — non-drafts have no readable curation status.
                drafts: list = []
                for ds in datasets:
                    if is_draft_dataset(ds):
                        drafts.append(ds)
                    else:
                        ds["curation_label"] = ""
                        ds["curation_time"] = ""
                        ds["curation_assigner"] = ""
                total = len(drafts)
                if total == 0:
                    self.progress.emit(t("workers.no_drafts"))
                with ThreadPoolExecutor(max_workers=_POOL_SIZE) as pool:
                    futures = [pool.submit(_read_status, ds) for ds in drafts]
                    done_n = 0
                    for fut in as_completed(futures):
                        if self.isInterruptionRequested():
                            for f in futures:
                                f.cancel()
                            return
                        ds, status = fut.result()
                        ds["curation_label"] = status.get("label", "")
                        ds["curation_time"] = status.get("time", "")
                        ds["curation_assigner"] = status.get("assigner", "")
                        done_n += 1
                        if done_n % 10 == 0 or done_n == total:
                            self.progress.emit(
                                t("workers.reading_labels", done=done_n, total=total)
                            )
                            self._emit_fraction(
                                phase_fraction(PHASE_LABELS, done_n, total)
                            )
            # Union with the allowed set (labels can exist that no draft
            # currently carries, and vice versa for legacy values). The set
            # is shared across a first-level collection: a stamped disk
            # slot (one real probe round, first alias use) serves every
            # later session with zero calls; otherwise a single probe round
            # runs here (drafts go first — the endpoint needs
            # PublishDataset permission, which curator tokens typically
            # hold only on datasets under curation; published rows
            # otherwise 403). Sub-collections reuse the top-level entry.
            try:
                ordered = [
                    d.get("persistent_id", "")
                    for d in datasets
                    if d.get("persistent_id") and is_draft_dataset(d)
                ]
                ordered += [
                    d.get("persistent_id", "")
                    for d in datasets
                    if d.get("persistent_id") and d.get("persistent_id") not in ordered
                ]
                from dataverse_client import get_cached_allowed_labels

                was_cached = (
                    get_cached_allowed_labels(self._base_url, self._subtree)
                    is not None
                )
                if was_cached:
                    self.progress.emit(t("workers.using_cached_labels"))
                else:
                    self.progress.emit(t("workers.fetching_allowed_labels"))
                if self.isInterruptionRequested():
                    return
                fetched = client.fetch_allowed_labels_shared(
                    self._subtree, ordered, max_attempts=3
                )
                for label in fetched:
                    if label not in labels:
                        labels.append(label)
                # Report the pure probe result (not the union above) so the
                # dashboard stamps the disk slot only for a real round.
                # Empty pid lists never stamp: a zero-dataset crawl must not
                # freeze [] in place before any dataset exists to probe.
                # Rounds where nothing answered (transport/server errors)
                # never stamp either: they retry next session instead of
                # freezing an error [] forever.
                try:
                    answered = False
                    try:
                        answered = bool(client.last_allowed_probe_answered())
                    except Exception:
                        answered = False
                    self.allowedProbed.emit(
                        {
                            "labels": list(fetched),
                            "probed": (not was_cached) and bool(ordered) and answered,
                            "collection": self._subtree,
                        }
                    )
                except Exception:
                    pass
            except Exception:
                pass
            if labels:
                shown = ", ".join(labels[:5]) + ("…" if len(labels) > 5 else "")
                self.progress.emit(t("workers.curation_labels", labels=shown))
            else:
                self.progress.emit(t("workers.no_curation_labels"))
            try:
                get_app_log().info(
                    t(
                        "workers.curation_labels_log",
                        labels=", ".join(
                            t("workers.labels_in_use", labels=lbl)
                            for lbl in labels
                        ) or t("common.none_in_parentheses"),
                    )
                )
            except Exception:
                pass
            try:
                self.labelsDiscovered.emit(labels)
            except Exception:
                pass
            self.progress.emit(
                t("workers.received", total=total, in_review=in_review_n)
            )
            self.finished.emit(datasets)
        except Exception as exc:
            self.error.emit(f"{exc}\n\n{traceback.format_exc()}")


class DownloadWorker(QThread):
    progress = Signal(int)
    finished = Signal(Path)
    error = Signal(str)
    # Emitted when the curator cancels (or cancel wins a race at the tail
    # of a run) — the UI resets via _on_download_cancelled, never a dialog.
    cancelled = Signal()
    # Overall download fraction (0..1) for a progress ring. The bundle
    # size is known up front, so this is determinate; a None target
    # (unknown size) leaves the ring indeterminate.
    progressFraction = Signal(float)

    def __init__(
        self,
        client,
        workspace: Path,
        persistent_id: str,
        parent=None,
        guestbook_response: dict | None = None,
    ):
        super().__init__(parent)
        register_worker(self)
        self._client = client
        self._workspace = workspace
        self._pid = persistent_id
        self._cancel_requested = False
        self._guestbook_response = guestbook_response

    def cancel(self) -> None:
        """Stop the run at the next stream chunk.

        Sets a Python-side flag (works before the thread starts) *and*
        the QThread interruption flag (works mid-run).
        """
        self._cancel_requested = True
        self.requestInterruption()

    def _stop_requested(self) -> bool:
        return self._cancel_requested or self.isInterruptionRequested()

    def run(self) -> None:
        import traceback

        from download_manager import DownloadCancelled, DownloadManager

        try:
            mgr = DownloadManager(self._client, self._workspace)
            if self._stop_requested():
                self.cancelled.emit()
                return
            # Bundle size up front makes the ring determinate.
            try:
                quote = mgr.quote(self._pid)
                total_bytes = int(quote.total_size_bytes or 0)
            except Exception:
                total_bytes = 0

            def _on_bytes(n: int) -> None:
                try:
                    self.progress.emit(n)
                except Exception:
                    pass
                try:
                    if total_bytes > 0:
                        frac = max(0.0, min(1.0, n / total_bytes))
                        self.progressFraction.emit(frac)
                except Exception:
                    pass

            staged = mgr.approve_and_download(
                self._pid,
                progress=_on_bytes,
                is_cancelled=self._stop_requested,
                guestbook_response=self._guestbook_response,
            )
            if self._stop_requested():
                self.cancelled.emit()
                return
            try:
                self.progressFraction.emit(1.0)
            except Exception:
                pass
            self.finished.emit(staged)
        except DownloadCancelled:
            self.cancelled.emit()
        except Exception as exc:
            if self._stop_requested():
                self.cancelled.emit()
                return
            self.error.emit(f"{exc}\n\n{traceback.format_exc()}")


class CheckWorker(QThread):
    finished = Signal(object)
    error = Signal(str)
    progress = Signal(str)
    # Emitted when the curator cancels a running check pass. The UI
    # resets through _on_checks_cancelled: no report, no dialog.
    cancelled = Signal()
    # Overall check fraction (0..1) for a progress ring.
    progressFraction = Signal(float)

    def __init__(self, dataset_dir: Path, persistent_id: str, label: str,
                 inventory: list | None = None, metadata: dict | None = None,
                 client=None, ruleset: dict | None = None, parent=None):
        super().__init__(parent)
        register_worker(self)
        self._dataset_dir = dataset_dir
        self._pid = persistent_id
        self._label = label
        self._inventory = inventory
        self._metadata = metadata
        # Optional Dataverse client (dv-tfy): used to fetch per-file DDI
        # variable metadata for the coverage check. Never required.
        self._client = client
        # Optional ruleset (dv-81q): a dataset-level check honours its
        # README section rules. None falls back to the built-in defaults.
        self._ruleset = ruleset
        self._cancel_requested = False

    def cancel(self) -> None:
        """Stop the run at the next check boundary.

        Sets a Python-side flag (works before the thread starts) *and*
        the QThread interruption flag (works mid-run).
        """
        self._cancel_requested = True
        self.requestInterruption()

    def _stop_requested(self) -> bool:
        return self._cancel_requested or self.isInterruptionRequested()

    def run(self) -> None:
        import os
        import traceback

        try:
            from engine.runner import run_report

            def _cb(msg: str) -> None:
                self.progress.emit(msg)

            def _frac(done: int, total: int) -> None:
                try:
                    if total > 0:
                        self.progressFraction.emit(
                            max(0.0, min(1.0, done / total))
                        )
                except Exception:
                    pass

            workers = max(1, min(8, (os.cpu_count() or 4)))
            # Variable metadata for tabular files (dv-tfy): best-effort DDI
            # fetch, capped so a large deposit never stalls the check pass.
            variable_metadata: dict | None = None
            if self._client is not None and isinstance(self._inventory, list):
                variable_metadata = {}
                tabular = [
                    e for e in self._inventory
                    if isinstance(e, dict) and e.get("tabular") and e.get("id")
                ][:50]
                for entry in tabular:
                    if self._stop_requested():
                        break
                    try:
                        meta = self._client.get_variable_metadata(str(entry["id"]))
                    except Exception:
                        meta = None
                    if meta:
                        variable_metadata[
                            str(entry.get("path") or entry.get("label") or "")
                        ] = meta
            report = run_report(
                self._dataset_dir,
                persistent_id=self._pid,
                label=self._label,
                progress_callback=_cb,
                progress_fraction=_frac,
                max_workers=workers,
                is_cancelled=self._stop_requested,
                inventory=self._inventory,
                metadata=self._metadata,
                variable_metadata=variable_metadata,
                ruleset=self._ruleset,
            )
            if self._stop_requested():
                self.cancelled.emit()
                return
            try:
                self.progressFraction.emit(1.0)
            except Exception:
                pass
            self.finished.emit(report)
        except Exception as exc:
            if self._stop_requested():
                self.cancelled.emit()
                return
            self.error.emit(f"{exc}\n\n{traceback.format_exc()}")


class MetadataBlocksWorker(QThread):
    """Fetch the instance's metadata-field catalog (metadatablocks API)."""

    finished = Signal(list)
    error = Signal(str)

    def __init__(self, base_url: str, api_token: str, workspace, parent=None):
        super().__init__(parent)
        register_worker(self)
        self._base_url = base_url
        self._api_token = api_token
        self._workspace = workspace

    def run(self) -> None:
        import traceback

        try:
            from dataverse_client import (
                DataverseClient,
                read_metadata_fields_cache,
                write_metadata_fields_cache,
            )

            try:
                cached = read_metadata_fields_cache(self._workspace, self._base_url)
            except Exception:
                cached = None
            if cached:
                self.finished.emit(cached)
                return
            client = DataverseClient(self._base_url, self._api_token)
            fields = client.fetch_metadata_field_catalog()
            if self.isInterruptionRequested():
                return
            try:
                write_metadata_fields_cache(self._workspace, self._base_url, fields)
            except Exception:
                pass
            self.finished.emit(fields or [])
        except Exception as exc:
            if self.isInterruptionRequested():
                return
            self.error.emit(f"{exc}\n\n{traceback.format_exc()}")


class MetadataWorker(QThread):
    finished = Signal(dict, list, dict, dict, dict)
    error = Signal(str)

    def __init__(self, base_url: str, api_token: str, persistent_id: str, parent=None,
                 collection: str = ""):
        super().__init__(parent)
        register_worker(self)
        self._base_url = base_url
        self._api_token = api_token
        self._pid = persistent_id
        self._collection = collection or ""

    def run(self) -> None:
        import time as _time
        import traceback
        from concurrent.futures import ThreadPoolExecutor, as_completed

        try:
            from dataverse_client import DataverseClient

            client = DataverseClient(self._base_url, self._api_token)
            # Parallel independent fetches (was serial sum of 8x RTT).
            def _fetch(name: str):
                try:
                    if name == "metadata":
                        return ("metadata", client.get_dataset_metadata(self._pid))
                    if name == "inventory":
                        return ("inventory", client.get_file_inventory(self._pid))
                    if name == "curation":
                        return ("curation", client.get_curation_status(self._pid) or {})
                    if name == "version_diff":
                        return ("version_diff", client.compare_versions(self._pid) or {})
                    if name == "versions":
                        return ("versions", client.list_versions(self._pid))
                    if name == "history":
                        return ("history", client.get_curation_history(self._pid))
                    if name == "allowed":
                        # Shared top-level cache: zero calls on hit, else one
                        # call for this dataset (its collection's list is the
                        # top-level list). No per-open probing.
                        return (
                            "allowed",
                            client.fetch_allowed_labels_shared(
                                self._collection, [self._pid], max_attempts=1
                            ),
                        )
                    if name == "in_review":
                        return ("in_review", bool(client.dataset_in_review(self._pid)))
                except Exception:
                    return (name, None)
                return (name, None)

            results: dict = {}
            names = ["metadata", "inventory", "curation", "version_diff", "versions", "history", "allowed", "in_review"]
            with ThreadPoolExecutor(max_workers=5) as pool:
                futures = {pool.submit(_fetch, n): n for n in names}
                for fut in as_completed(futures):
                    if self.isInterruptionRequested():
                        for f in futures:
                            f.cancel()
                        return
                    try:
                        key, value = fut.result()
                    except Exception:
                        continue
                    results[key] = value
            metadata = results.get("metadata") or {}
            if not isinstance(metadata, dict):
                metadata = {}
            inventory = results.get("inventory")
            inventory_failed = False
            if not isinstance(inventory, list):
                inventory = []
                inventory_failed = True
            # Enrich tabular inventory rows with live ingest status/errors
            # (GET /api/files/{id}/ingestStatus) — best effort, never fails
            # the metadata load.
            try:
                tab_rows = [
                    e for e in inventory
                    if isinstance(e, dict) and e.get("tabular") and e.get("id")
                ]
                if tab_rows:
                    def _ingest(row):
                        try:
                            return client.get_tabular_ingest_status(str(row.get("id") or ""))
                        except Exception:
                            return None

                    from concurrent.futures import ThreadPoolExecutor as _TPE

                    with _TPE(max_workers=4) as pool:
                        for row, st in zip(tab_rows, pool.map(_ingest, tab_rows), strict=True):
                            if isinstance(st, dict):
                                if st.get("status"):
                                    row["ingest_status"] = str(st["status"])
                                if st.get("error"):
                                    row["ingest_error"] = str(st["error"])
            except Exception:
                pass
            curation = results.get("curation")
            if not isinstance(curation, dict):
                curation = {}
            version_diff = results.get("version_diff")
            if not isinstance(version_diff, dict):
                version_diff = {}
            versions = results.get("versions")
            if not isinstance(versions, list):
                versions = []
            history = results.get("history")
            if not isinstance(history, list):
                history = []
            allowed = results.get("allowed")
            if not isinstance(allowed, list):
                allowed = []
            if isinstance(curation, dict):
                curation["history"] = history
                curation["allowed"] = allowed
            try:
                numeric_id = metadata.get("id")
            except Exception:
                numeric_id = None
            try:
                timestamps = client.get_timestamps(self._pid, numeric_id=numeric_id)
            except Exception:
                timestamps = {}
            try:
                cache_key = _inbox_key(self._base_url, self._pid, self._api_token)
                with _inbox_lock:
                    cached = _inbox_cache.get(cache_key)
                if cached is not None and _time.monotonic() - cached[0] < _INBOX_TTL_S:
                    review_submissions = cached[1]
                else:
                    review_submissions = client.find_review_submissions(self._pid)
                    with _inbox_lock:
                        _inbox_cache[cache_key] = (_time.monotonic(), review_submissions)
            except Exception:
                review_submissions = []
            in_review = bool(results.get("in_review"))
            # The dataset record names its guestbook, if any. Fetch the
            # definition now so the download window can render its fields
            # before the curator clicks Download (one small extra call).
            guestbook = None
            account = {}
            try:
                guestbook_id = metadata.get("guestbookId")
                if guestbook_id:
                    guestbook = client.get_guestbook(guestbook_id) or None
                    # Prefill the window with the curator's account details;
                    # Dataverse still requires any field the account lacks
                    # (e.g. Position) to be filled in.
                    account = client.get_current_user()
            except Exception:
                guestbook = None
            extra = {
                "versions": versions,
                "timestamps": timestamps if isinstance(timestamps, dict) else {},
                "review_submissions": review_submissions
                if isinstance(review_submissions, list)
                else [],
                "in_review": in_review,
                "inventory_failed": inventory_failed,
                "guestbook": guestbook,
                "account": account,
            }
            self.finished.emit(metadata, inventory, curation, version_diff, extra)
        except Exception as exc:
            self.error.emit(f"{exc}\n\n{traceback.format_exc()}")
