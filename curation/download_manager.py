"""Approval-gated download workflow.

Flow: quote (file count + total bytes from the inventory, no download) ->
curator approval -> zip bundle download with progress -> safe unzip ->
checksum verification against the Dataverse inventory. Network work runs on
Qt worker threads; see docs/html/architecture.html.
"""

import hashlib
import os
import shutil
import threading
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from curation.client import DownloadCancelled

_STREAM_CHUNK = 1 << 20


_STAGE_LOCKS: dict[str, threading.Lock] = {}


_STAGE_LOCKS_GUARD = threading.Lock()


def _stage_lock(persistent_id: str) -> threading.Lock:
    key = persistent_id.replace(":", "_").replace("/", "_").replace("\\", "_")
    with _STAGE_LOCKS_GUARD:
        lock = _STAGE_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _STAGE_LOCKS[key] = lock
        return lock


@dataclass
class DownloadQuote:
    persistent_id: str
    file_count: int
    total_size_bytes: int


class DownloadManager:
    def __init__(self, client: Any, workspace: Path) -> None:
        self._client = client
        self._workspace = Path(workspace)

    # -- paths ---------------------------------------------------------------

    def dataset_dir(self, persistent_id: str) -> Path:
        sanitized = persistent_id.replace(":", "_").replace("/", "_").replace("\\", "_")
        # Block ".." traversal: server-supplied PIDs are untrusted.
        sanitized = sanitized.replace("..", "__")
        sanitized = sanitized.strip()
        if sanitized in ("", ".", "__", "_"):
            sanitized = "_dataset"
        # Avoid hidden / dot-leading dirs and cap length for Windows paths.
        sanitized = sanitized.lstrip(".")
        if not sanitized:
            sanitized = "_dataset"
        return self._workspace / "downloads" / sanitized[:120]

    def files_dir(self, persistent_id: str) -> Path:
        return self.dataset_dir(persistent_id) / "files"

    def metadata_path(self, persistent_id: str) -> Path:
        return self.dataset_dir(persistent_id) / "metadata.json"

    def manifest_path(self, persistent_id: str) -> Path:
        return self.dataset_dir(persistent_id) / "file-manifest.json"

    def reports_dir(self, persistent_id: str) -> Path:
        return self.dataset_dir(persistent_id) / "reports"

    # -- workflow ------------------------------------------------------------

    def inventory(self, persistent_id: str) -> list[Any]:
        """File inventory from Dataverse (single network call, shared)."""
        items: list[Any] = self._client.get_file_inventory(persistent_id)
        return items

    def quote(self, persistent_id: str) -> DownloadQuote:
        """File count and total size from the inventory - no download."""
        return self.quote_from(self.inventory(persistent_id), persistent_id)

    @staticmethod
    def quote_from(inventory: list[Any], persistent_id: str) -> DownloadQuote:
        total = 0
        count = 0
        for f in inventory:
            if not isinstance(f, dict):
                continue
            count += 1
            try:
                # Originals-only: quote the depositor upload size when known.
                if f.get("tabular") and str(f.get("original_name") or "").strip():
                    size = int(f.get("original_size", 0) or 0)
                    if size:
                        total += size
                        continue
                total += int(f.get("size_bytes", 0) or 0)
            except (TypeError, ValueError):
                continue
        return DownloadQuote(
            persistent_id=persistent_id,
            file_count=count,
            total_size_bytes=total,
        )

    def missing_files(self, persistent_id: str, inventory: list[Any] | None = None) -> list[Any]:  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
        """Inventory paths not yet staged (missing or size-changed).

        Exact directoryLabel paths win; a basename fallback covers bundles
        that flattened subfolders (otherwise fully-staged datasets forever
        read as missing and Download All re-prompts every time).
        """
        from pathlib import Path as _Path

        inv: Any = inventory if inventory is not None else self.inventory(persistent_id)
        staged_root = self.files_dir(persistent_id)
        # One directory walk for all basename fallbacks: map basename ->
        # list of staged sizes so the fallback can still enforce size match.
        staged_basenames: set[str] = set()
        staged_sizes: dict[str, list[int]] = {}
        try:
            if staged_root.exists():
                for p in staged_root.rglob("*"):
                    try:
                        if p.is_file():
                            staged_basenames.add(p.name)
                            try:
                                sz = p.stat().st_size
                            except OSError:
                                continue
                            staged_sizes.setdefault(p.name, []).append(sz)
                    except Exception:
                        continue
        except Exception:
            pass
        missing: list[Any] = []
        if not isinstance(inv, list):
            return []
        for item in inv:
            if not isinstance(item, dict):
                continue
            path = item.get("path", "")
            if not path or not isinstance(path, str):
                continue
            # Originals-only downloads: for tabular files the staged copy is
            # the original name (parent/original_name), not the .tab path.
            expected_path = path
            expected_size_key = "size_bytes"
            try:
                if item.get("tabular") and str(item.get("original_name") or "").strip():
                    original_name = Path(str(item["original_name"])).name
                    if "/" in path:
                        expected_path = path.rpartition("/")[0] + "/" + original_name
                    else:
                        expected_path = original_name
                    expected_size_key = "original_size"
            except Exception:
                pass
            local = self._contained(staged_root, expected_path)
            if local is not None:
                try:
                    if local.is_file():
                        try:
                            expected = int(item.get(expected_size_key, 0) or 0)
                        except (TypeError, ValueError):
                            expected = 0
                        try:
                            actual = local.stat().st_size
                        except OSError:
                            missing.append(path)
                            continue
                        if not expected or actual == expected:
                            continue
                        # Size mismatch on the expected path — still missing.
                        missing.append(path)
                        continue
                except OSError:
                    missing.append(path)
                    continue
            # Exact path absent (or unsafe): accept a same-named file
            # anywhere under files_dir as staged, but still enforce size
            # when the inventory knows it (avoids same-name false-staged).
            try:
                base = _Path(expected_path).name
                if base and base in staged_basenames:
                    try:
                        expected_fb = int(item.get(expected_size_key, 0) or 0)
                    except (TypeError, ValueError):
                        expected_fb = 0
                    if not expected_fb:
                        continue
                    if expected_fb in staged_sizes.get(base, []):
                        continue
            except Exception:
                pass
            if local is None:
                # Can never be staged safely — surface it, don't silently skip.
                missing.append(path)
                continue
            missing.append(path)
        return missing

    def is_fully_staged(self, persistent_id: str, inventory: list[Any] | None = None) -> bool:
        """Check whether every inventory file is already staged with matching size."""
        try:
            inv = inventory if inventory is not None else self.inventory(persistent_id)
            return bool(inv) and not self.missing_files(persistent_id, inv)
        except Exception as exc:
            from curation.applog import get_app_log

            get_app_log().error(f"is_fully_staged({persistent_id}): {exc}")
            return False

    # -- on-disk metadata / manifest / reports --------------------------------

    def save_metadata(
        self, persistent_id: str, metadata: dict[str, Any], inventory: list[Any]
    ) -> None:
        """Cache dataset metadata + file manifest beside the downloads."""
        try:
            import json as _json
            import os
            import tempfile

            def _atomic_write(path: Path, payload: Any) -> None:
                path.parent.mkdir(parents=True, exist_ok=True)
                fd, tmp_name = tempfile.mkstemp(
                    dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
                )
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as handle:
                        handle.write(_json.dumps(payload, indent=2, ensure_ascii=False))
                    os.replace(tmp_name, path)
                except Exception:
                    try:
                        os.unlink(tmp_name)
                    except OSError:
                        pass
                    raise

            base = self.dataset_dir(persistent_id)
            base.mkdir(parents=True, exist_ok=True)
            _atomic_write(self.metadata_path(persistent_id), metadata or {})
            _atomic_write(self.manifest_path(persistent_id), inventory or [])
        except Exception as exc:
            from curation.applog import get_app_log

            get_app_log().error(f"save_metadata({persistent_id}): {exc}")

    def load_metadata(self, persistent_id: str) -> tuple[dict[str, Any] | None, list[Any] | None]:
        """Load cached (metadata, inventory) or (None, None) — never raises."""
        try:
            import json as _json

            meta_path = self.metadata_path(persistent_id)
            mani_path = self.manifest_path(persistent_id)
            if not meta_path.exists() or not mani_path.exists():
                return None, None
            metadata = _json.loads(meta_path.read_text(encoding="utf-8"))
            inventory = _json.loads(mani_path.read_text(encoding="utf-8"))
            if not isinstance(metadata, dict) or not isinstance(inventory, list):
                return None, None
            return metadata, inventory
        except Exception:
            return None, None

    def approve_and_download(
        self,
        persistent_id: str,
        progress: Callable[[int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
        guestbook_response: dict[str, Any] | None = None,
    ) -> Path:
        """Download the bundle and stage its contents for the check engine.

        Afterwards, original-format uploads are fetched per tabular file
        (the bundle only carries server-generated .tab derivatives).
        `is_cancelled` stops both phases at the next stream chunk with
        DownloadCancelled; the truncated .part is removed first, while
        files already staged stay on disk (a later run skips them).
        `guestbook_response` carries the curator's answers for a dataset
        whose guestbook must be filled in before Dataverse serves the ZIP.
        """
        with _stage_lock(persistent_id):
            dest_dir = self.dataset_dir(persistent_id)
            part = dest_dir / "_bundle.zip.part"
            bundle = dest_dir / "_bundle.zip"
            try:
                self._client.download_dataset_zip(
                    persistent_id,
                    part,
                    progress=progress,
                    is_cancelled=is_cancelled,
                    guestbook_response=guestbook_response,
                )
            except DownloadCancelled:
                # Never leave a truncated .part behind — next run starts clean.
                try:
                    part.unlink(missing_ok=True)
                except OSError:
                    pass
                raise
            # Only publish the bundle on a complete download — a killed run
            # leaves .part behind, never a truncated _bundle.zip.
            part.replace(bundle)
            try:
                self._extract(bundle, self.files_dir(persistent_id))
            finally:
                try:
                    bundle.unlink(missing_ok=True)
                except OSError:
                    pass
            try:
                self.download_originals(
                    persistent_id,
                    progress=progress,
                    max_workers=min(4, os.cpu_count() or 4),
                    is_cancelled=is_cancelled,
                )
            except DownloadCancelled:
                raise
            except Exception as exc:
                from curation.applog import get_app_log

                get_app_log().error(f"download_originals after bundle ({persistent_id}): {exc}")
            return self.files_dir(persistent_id)

    def download_originals(  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
        self,
        persistent_id: str,
        inventory: list[Any] | None = None,
        progress: Callable[[int], None] | None = None,
        max_workers: int = 1,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> list[str]:
        """Fetch original uploads behind tabular .tab derivatives.

        Returns staged original paths. Skips files already staged with a
        matching size. Never raises for per-file failures — they are
        collected and ignored (the .tab remains available for checks).
        The one exception is DownloadCancelled (curator cancelled): it
        propagates immediately, the in-flight partial is removed, and
        files already staged are kept. `max_workers>1` fetches originals
        in parallel (I/O-bound).
        """
        try:
            inv: Any = inventory if inventory is not None else self.inventory(persistent_id)
        except Exception:
            return []
        root = self.files_dir(persistent_id)
        if not isinstance(inv, list):
            return []

        def _fetch_one(item: Any) -> str | None:  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
            dest: Path | None = None
            try:
                if is_cancelled and is_cancelled():
                    raise DownloadCancelled("originals")
                if not isinstance(item, dict) or not item.get("tabular"):
                    return None
                file_id = str(item.get("id") or "")
                original_name = str(item.get("original_name") or "")
                if not file_id or not original_name:
                    return None
                rel = Path(item.get("path", "") or "")
                if str(rel.parent) not in ("", "."):
                    target = rel.parent / Path(original_name).name
                else:
                    target = Path(Path(original_name).name)
                dest = self._contained(root, target.as_posix())
                if dest is None:
                    return None
                try:
                    expected = int(item.get("original_size", 0) or 0)
                except (TypeError, ValueError):
                    expected = 0
                if dest.is_file():
                    try:
                        actual_size = dest.stat().st_size
                    except OSError:
                        actual_size = -1
                    if actual_size >= 0 and (
                        (expected and actual_size == expected) or (not expected and actual_size > 0)
                    ):
                        return dest.relative_to(root).as_posix()
                dest.parent.mkdir(parents=True, exist_ok=True)
                self._client.download_datafile_original(
                    file_id, dest, progress=progress, is_cancelled=is_cancelled
                )
                return dest.relative_to(root).as_posix()
            except DownloadCancelled:
                # Curator cancelled: drop the in-flight partial, then let the
                # cancellation travel up — it is not a per-file failure.
                try:
                    if dest is not None and dest.is_file():
                        dest.unlink()
                except OSError:
                    pass
                raise
            except Exception:
                try:
                    if dest is not None and dest.is_file():
                        try:
                            if dest.stat().st_size == 0:
                                dest.unlink()
                        except OSError:
                            pass
                except Exception:
                    pass
                return None

        staged: list[str] = []
        tabular_items: list[Any] = [it for it in inv if isinstance(it, dict) and it.get("tabular")]
        if max_workers and max_workers > 1 and len(tabular_items) > 1:
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                for rel in pool.map(_fetch_one, tabular_items):
                    if rel:
                        staged.append(rel)
        else:
            for item in tabular_items:
                rel = _fetch_one(item)
                if rel:
                    staged.append(rel)
        # Originals-only: drop the server-generated .tab derivatives once
        # the depositor's upload is staged (checks match the original path).
        for item in tabular_items:
            if not isinstance(item, dict):
                continue
            original_name = str(item.get("original_name") or "")
            if not original_name:
                continue
            try:
                rel_tab = str(item.get("path", "") or "")
                if not rel_tab or not rel_tab.lower().endswith(".tab"):
                    continue
                # Only remove when the original actually landed beside it
                # (or anywhere under files_dir under its basename).
                orig_base = Path(original_name).name
                original_staged = False
                for rel in staged:
                    if Path(rel).name == orig_base:
                        original_staged = True
                        break
                if not original_staged:
                    continue
                tab_local = self._contained(root, rel_tab)
                if tab_local is not None and tab_local.is_file():
                    tab_local.unlink()
            except Exception:
                continue
        return staged

    @staticmethod
    def _is_tabular(item: dict[str, Any]) -> bool:
        return bool(item.get("tabular")) or str(item.get("path", "")).lower().endswith(".tab")

    def verify(  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
        self,
        persistent_id: str,
        progress: Callable[[int, int], None] | None = None,
        max_workers: int = 1,
        inventory: list[Any] | None = None,
    ) -> tuple[bool, list[str], list[str]]:
        """Rehash staged files against the Dataverse inventory checksums.

        Returns (ok, problems, warnings). Missing files, unsupported
        algorithms and non-tabular mismatches are blocking problems.
        `.tab` mismatches are warnings, not errors: tabular files are
        server-regenerated ingest products whose stored checksum can predate
        the download — the message carries hashes, size and the file's UNF
        for manual comparison (see docs/html/user-guide.html "Checksum problems").
        """
        if inventory is None:
            inventory = self._client.get_file_inventory(persistent_id)
        staged_root = self.files_dir(persistent_id)
        problems: list[str] = []
        warnings: list[str] = []
        items: list[Any] = inventory if isinstance(inventory, list) else []
        total = len(items)
        done = 0
        done_lock = threading.Lock()

        def _bump() -> None:
            nonlocal done
            with done_lock:
                done += 1
                current = done
            if progress:
                try:
                    progress(current, total)
                except Exception:
                    pass

        def _verify_one(item: Any) -> tuple[str | None, str | None]:  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
            if not isinstance(item, dict):
                return ("malformed inventory entry (missing path)", None)
            rel = str(item.get("path", "") or "")
            if not rel:
                return ("malformed inventory entry (missing path)", None)
            # Originals-only: verify the staged original (not the .tab path).
            check_rel = rel
            expected_size_key = "size_bytes"
            is_tab_orig = False
            try:
                if item.get("tabular") and str(item.get("original_name") or "").strip():
                    original_name = Path(str(item["original_name"])).name
                    if "/" in rel:
                        check_rel = rel.rpartition("/")[0] + "/" + original_name
                    else:
                        check_rel = original_name
                    expected_size_key = "original_size"
                    is_tab_orig = True
            except Exception:
                pass
            local = self._contained(staged_root, check_rel)
            if local is None:
                return (f"unsafe path (outside workspace): {check_rel}", None)
            # Exact path may be absent when a bundle flattened folders —
            # accept a same-basename file under files_dir before "missing".
            try:
                if not local.exists():
                    base_name = Path(check_rel).name
                    if base_name:
                        for candidate in staged_root.rglob(base_name):
                            try:
                                if candidate.is_file():
                                    local = candidate
                                    break
                            except OSError:
                                continue
            except OSError:
                pass
            try:
                if not local.exists():
                    return (f"missing: {check_rel}", None)
                # A directory masquerading as a file is a problem, not a crash.
                if not local.is_file():
                    return (f"not a file: {check_rel}", None)
            except OSError as exc:
                return (f"unreadable: {check_rel} ({exc})", None)
            if is_tab_orig:
                # Original-format download: inventory checksum covers the
                # server .tab, not the depositor upload — size is the check.
                try:
                    expected_sz = int(item.get(expected_size_key, 0) or 0)
                except (TypeError, ValueError):
                    expected_sz = 0
                try:
                    actual_sz = local.stat().st_size
                except OSError as exc:
                    return (f"unreadable: {check_rel} ({exc})", None)
                if expected_sz and actual_sz != expected_sz:
                    return (
                        f"size mismatch (original): {check_rel} "
                        f"(expected {expected_sz}, got {actual_sz} bytes)",
                        None,
                    )
                return (None, None)
            if not item.get("checksum_value"):
                return (None, f"no checksum recorded for {rel} — integrity unverified")
            algorithm = item.get("checksum_type") or "md5"
            try:
                actual = self._hash_file(local, algorithm)
            except ValueError:
                return (
                    f"unsupported checksum type '{algorithm}' for {rel}",
                    None,
                )
            except OSError as exc:
                return (f"unreadable: {rel} ({exc})", None)
            expected = str(item.get("checksum_value") or "").lower()
            if not expected:
                return (None, f"no checksum recorded for {rel} — integrity unverified")
            if actual.lower() != expected:
                try:
                    size = local.stat().st_size
                except OSError:
                    size = -1
                line = (
                    f"checksum mismatch: {rel} "
                    f"({algorithm} expected {expected[:16]}… "
                    f"got {actual[:16]}…, {size} bytes)"
                )
                if self._is_tabular(item):
                    unf = str(item.get("unf") or "")
                    original = str(item.get("original_format") or "")
                    line += (
                        " — tabular .tab files are server-regenerated ingest "
                        "products whose stored checksum can predate regeneration; "
                        "compare the UNF in Dataverse"
                        + (f" ({unf})" if unf else "")
                        + (
                            f" or download the original {original} for a byte-exact check"
                            if original
                            else ""
                        )
                    )
                    return (None, line)
                return (line, None)
            return (None, None)

        # Sequential by default (deterministic order for tests); opt-in
        # ThreadPool for multi-GB datasets via max_workers>1.
        items = inventory if isinstance(inventory, list) else []
        if max_workers and max_workers > 1:
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                for prob, warn in pool.map(_verify_one, items):
                    if prob:
                        problems.append(prob)
                    elif warn:
                        warnings.append(warn)
                    _bump()
        else:
            for item in items:
                prob, warn = _verify_one(item)
                if prob:
                    problems.append(prob)
                elif warn:
                    warnings.append(warn)
                _bump()
        return (not problems, problems, warnings)

    # -- helpers ---------------------------------------------------------------

    @staticmethod
    def _contained(root: Path, rel: str) -> Path | None:
        """Resolve `rel` under `root`; None when absolute or escaping.

        Inventory paths (directoryLabel + filename) come from the server —
        never let `..` or an absolute path redirect reads/writes outside
        the workspace.
        """
        try:
            target = (root / rel).resolve()
        except Exception:
            return None
        try:
            if target.is_relative_to(root.resolve()):
                return target
        except Exception:
            return None
        return None

    @staticmethod
    def _safe_extract(bundle: Path, dest: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        root = dest.resolve()
        with zipfile.ZipFile(bundle) as archive:
            for member in archive.infolist():
                # Refuse symlinks: a link inside dest could redirect a later
                # member's write outside the workspace (TOCTOU-proofing the
                # containment check below is not possible with extractall).
                if (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise RuntimeError(f"unsafe archive entry (symlink): {member.filename}")
                target = (dest / member.filename).resolve()
                if not target.is_relative_to(root):
                    raise RuntimeError(f"unsafe archive entry: {member.filename}")
            archive.extractall(dest)

    def _extract(self, bundle: Path, dest: Path) -> None:
        # Extract beside the target, then swap: a corrupt bundle or an
        # unsafe entry leaves the previous stage untouched instead of
        # deleting it first (destructive-restart bug).
        staging = dest.parent / (dest.name + ".new")
        if staging.exists():
            shutil.rmtree(staging)
        try:
            self._safe_extract(bundle, staging)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        if dest.exists():
            shutil.rmtree(dest)
        staging.rename(dest)

    @staticmethod
    def _hash_file(path: Path, algorithm: str) -> str:
        digest = hashlib.new(algorithm)
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(_STREAM_CHUNK), b""):
                digest.update(chunk)
        return digest.hexdigest()
