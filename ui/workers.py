"""Background workers for network and engine tasks."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QThread, Signal

# Parallelism for per-dataset confirmation calls (locks, label fallback).
# The client holds no shared session and applog is lock-guarded, so plain
# worker threads are safe; 8 keeps small instances fast without hammering.
_POOL_SIZE = 8

# Review-inbox scan cache: find_review_submissions re-reads up to 5 inbox
# pages, so memoize per (instance, dataset) for 10 minutes — reopening a
# dataset skips the rescan.
_INBOX_TTL_S = 600.0
_inbox_cache: dict = {}


class CrawlWorker(QThread):
    finished = Signal(list)
    error = Signal(str)
    progress = Signal(str)
    # Emitted alongside finished: the instance's curation-label set so the
    # dashboard can offer per-instance label filtering. Carried separately
    # because `finished(list)` signature is fixed.
    labelsDiscovered = Signal(list)

    def __init__(self, base_url: str, api_token: str, subtree: str, parent=None):
        super().__init__(parent)
        self._base_url = base_url
        self._api_token = api_token
        self._subtree = subtree

    def run(self) -> None:
        import traceback

        try:
            from dataverse_client import DataverseClient

            self.progress.emit(f"Connecting to {self._base_url} …")
            client = DataverseClient(self._base_url, self._api_token)
            coll = self._subtree.strip() or "whole repository"
            self.progress.emit(f"Fetching all datasets in {coll} (paginated Search API) …")
            datasets = client.list_draft_datasets(self._subtree)
            if self.isInterruptionRequested():
                return
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

            with ThreadPoolExecutor(max_workers=_POOL_SIZE) as pool:
                futures = [pool.submit(_check_lock, ds) for ds in datasets]
                for i, fut in enumerate(futures, 1):
                    if self.isInterruptionRequested():
                        for f in futures:
                            f.cancel()
                        return
                    ds, flag = fut.result()
                    if flag:
                        ds["state"] = "In Review"
                        in_review_n += 1
                    if i % 10 == 0 or i == total:
                        self.progress.emit(
                            f"Checking review locks… {i}/{total} ({in_review_n} in review)"
                        )
            # Curation labels are set at the Dataverse level — pull them in bulk
            # via the superuser CSV report (one call for all drafts). Non-
            # superuser tokens get 403 there, so fall back to per-dataset
            # curationStatus calls in that case.
            pids = [d.get("persistent_id", "") for d in datasets if d.get("persistent_id")]
            labels: list = []
            report = None
            try:
                self.progress.emit("Fetching curation-label report for this Dataverse …")
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
                    f"Curation report: {len(report)} draft(s), "
                    f"{len(labels)} label(s) in use"
                )
            else:
                def _read_status(ds: dict) -> tuple:
                    try:
                        status = client.get_curation_status(ds.get("persistent_id", ""))
                    except Exception:
                        status = None
                    return ds, status or {}

                total = len(datasets)
                with ThreadPoolExecutor(max_workers=_POOL_SIZE) as pool:
                    futures = [pool.submit(_read_status, ds) for ds in datasets]
                    for i, fut in enumerate(futures, 1):
                        if self.isInterruptionRequested():
                            for f in futures:
                                f.cancel()
                            return
                        ds, status = fut.result()
                        ds["curation_label"] = status.get("label", "")
                        ds["curation_time"] = status.get("time", "")
                        ds["curation_assigner"] = status.get("assigner", "")
                        if i % 10 == 0 or i == total:
                            self.progress.emit(f"Reading curation labels… {i}/{total}")
            # Union with the allowed set (labels can exist that no draft
            # currently carries, and vice versa for legacy values). The set
            # is collection-wide but may vary per collection/dataset, so walk
            # draft datasets first (bounded): first success wins, plus a few
            # more for cross-collection variation. Drafts go first because
            # the endpoint requires PublishDataset permission, which curator
            # tokens typically hold only on datasets under curation
            # (published rows otherwise 403).
            try:
                ordered = [
                    d.get("persistent_id", "")
                    for d in datasets
                    if d.get("persistent_id")
                    and (
                        (d.get("state") or "").upper() == "DRAFT"
                        or "REVIEW" in (d.get("state") or "").upper()
                        or d.get("has_draft")
                    )
                ]
                ordered += [
                    d.get("persistent_id", "")
                    for d in datasets
                    if d.get("persistent_id") and d.get("persistent_id") not in ordered
                ]
                self.progress.emit("Fetching allowed curation labels for this Dataverse …")
                attempts = 0
                for probe in ordered:
                    if attempts >= 5 or self.isInterruptionRequested():
                        break
                    attempts += 1
                    try:
                        found = client.get_allowed_curation_labels(probe)
                    except Exception:
                        found = []
                    for label in found:
                        if label not in labels:
                            labels.append(label)
            except Exception:
                pass
            if labels:
                shown = ", ".join(labels[:5]) + ("…" if len(labels) > 5 else "")
                self.progress.emit(f"Curation labels: {shown}")
            else:
                self.progress.emit(
                    "No curation labels found — none configured, or the token "
                    "lacks PublishDataset permission (see log for 403s)"
                )
            try:
                self.labelsDiscovered.emit(labels)
            except Exception:
                pass
            self.progress.emit(
                f"Received {total} dataset(s), {in_review_n} in review — "
                "use the filter bar to narrow by status/text"
            )
            self.finished.emit(datasets)
        except Exception as exc:
            self.error.emit(f"{exc}\n\n{traceback.format_exc()}")


class DownloadWorker(QThread):
    progress = Signal(int)
    finished = Signal(Path)
    error = Signal(str)

    def __init__(self, client, workspace: Path, persistent_id: str, parent=None):
        super().__init__(parent)
        self._client = client
        self._workspace = workspace
        self._pid = persistent_id

    def run(self) -> None:
        import traceback

        try:
            from download_manager import DownloadManager

            mgr = DownloadManager(self._client, self._workspace)
            staged = mgr.approve_and_download(
                self._pid, progress=lambda n: self.progress.emit(n)
            )
            self.finished.emit(staged)
        except Exception as exc:
            self.error.emit(f"{exc}\n\n{traceback.format_exc()}")


class CheckWorker(QThread):
    finished = Signal(object)
    error = Signal(str)
    progress = Signal(str)

    def __init__(self, dataset_dir: Path, persistent_id: str, label: str, parent=None):
        super().__init__(parent)
        self._dataset_dir = dataset_dir
        self._pid = persistent_id
        self._label = label

    def run(self) -> None:
        import traceback

        try:
            from engine.runner import run_report

            def _cb(msg: str) -> None:
                self.progress.emit(msg)

            report = run_report(self._dataset_dir, persistent_id=self._pid, label=self._label, progress_callback=_cb)
            self.finished.emit(report)
        except Exception as exc:
            self.error.emit(f"{exc}\n\n{traceback.format_exc()}")


class MetadataWorker(QThread):
    finished = Signal(dict, list, dict, dict, dict)
    error = Signal(str)

    def __init__(self, base_url: str, api_token: str, persistent_id: str, parent=None):
        super().__init__(parent)
        self._base_url = base_url
        self._api_token = api_token
        self._pid = persistent_id

    def run(self) -> None:
        import traceback

        try:
            from dataverse_client import DataverseClient

            client = DataverseClient(self._base_url, self._api_token)
            metadata = client.get_dataset_metadata(self._pid)
            try:
                inventory = client.get_file_inventory(self._pid)
                inventory_failed = False
            except Exception:
                # Keep [] (all consumers iterate it) but flag the failure so
                # the view shows an error state instead of "no files".
                inventory = []
                inventory_failed = True
            try:
                curation = client.get_curation_status(self._pid) or {}
            except Exception:
                curation = {}
            try:
                version_diff = client.compare_versions(self._pid) or {}
            except Exception:
                version_diff = {}
            try:
                versions = client.list_versions(self._pid)
            except Exception:
                versions = []
            try:
                history = client.get_curation_history(self._pid)
            except Exception:
                history = []
            try:
                allowed = client.discover_curation_labels([self._pid], sample_size=1)
            except Exception:
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
                import time as _time

                cache_key = (self._base_url, self._pid)
                cached = _inbox_cache.get(cache_key)
                if cached is not None and _time.monotonic() - cached[0] < _INBOX_TTL_S:
                    review_submissions = cached[1]
                else:
                    review_submissions = client.find_review_submissions(self._pid)
                    _inbox_cache[cache_key] = (_time.monotonic(), review_submissions)
            except Exception:
                review_submissions = []
            try:
                in_review = bool(client.dataset_in_review(self._pid))
            except Exception:
                in_review = False
            extra = {
                "versions": versions,
                "timestamps": timestamps if isinstance(timestamps, dict) else {},
                "review_submissions": review_submissions
                if isinstance(review_submissions, list)
                else [],
                "in_review": in_review,
                "inventory_failed": inventory_failed,
            }
            self.finished.emit(metadata, inventory, curation, version_diff, extra)
        except Exception as exc:
            self.error.emit(f"{exc}\n\n{traceback.format_exc()}")
