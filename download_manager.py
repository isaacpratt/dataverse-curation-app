"""Approval-gated download workflow.

Flow: quote (file count + total bytes from the inventory, no download) ->
curator approval -> zip bundle download with progress -> safe unzip ->
checksum verification against the Dataverse inventory. Network work runs on
Qt worker threads; see docs/architecture.md.
"""

import hashlib
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

_STREAM_CHUNK = 1 << 20


@dataclass
class DownloadQuote:
    persistent_id: str
    file_count: int
    total_size_bytes: int


class DownloadManager:
    def __init__(self, client, workspace: Path) -> None:
        self._client = client
        self._workspace = Path(workspace)

    # -- paths ---------------------------------------------------------------

    def dataset_dir(self, persistent_id: str) -> Path:
        sanitized = (
            persistent_id.replace(":", "_").replace("/", "_").replace("\\", "_")
        )
        return self._workspace / "downloads" / sanitized

    def files_dir(self, persistent_id: str) -> Path:
        return self.dataset_dir(persistent_id) / "files"

    def metadata_path(self, persistent_id: str) -> Path:
        return self.dataset_dir(persistent_id) / "metadata.json"

    def manifest_path(self, persistent_id: str) -> Path:
        return self.dataset_dir(persistent_id) / "file-manifest.json"

    def reports_dir(self, persistent_id: str) -> Path:
        return self.dataset_dir(persistent_id) / "reports"

    # -- workflow ------------------------------------------------------------

    def inventory(self, persistent_id: str) -> list:
        """File inventory from Dataverse (single network call, shared)."""
        return self._client.get_file_inventory(persistent_id)

    def quote(self, persistent_id: str) -> DownloadQuote:
        """File count and total size from the inventory - no download."""
        return self.quote_from(self.inventory(persistent_id), persistent_id)

    @staticmethod
    def quote_from(inventory: list, persistent_id: str) -> DownloadQuote:
        return DownloadQuote(
            persistent_id=persistent_id,
            file_count=len(inventory),
            total_size_bytes=sum(int(f.get("size_bytes", 0) or 0) for f in inventory),
        )

    def missing_files(self, persistent_id: str, inventory: list | None = None) -> list:
        """Inventory paths not yet staged (missing or size-changed).

        Exact directoryLabel paths win; a basename fallback covers bundles
        that flattened subfolders (otherwise fully-staged datasets forever
        read as missing and Download All re-prompts every time).
        """
        from pathlib import Path as _Path

        inv = inventory if inventory is not None else self.inventory(persistent_id)
        staged_root = self.files_dir(persistent_id)
        # One directory walk for all basename fallbacks.
        staged_basenames: set[str] = set()
        try:
            if staged_root.exists():
                for p in staged_root.rglob("*"):
                    try:
                        if p.is_file():
                            staged_basenames.add(p.name)
                    except Exception:
                        continue
        except Exception:
            pass
        missing: list = []
        for item in inv:
            path = item.get("path", "")
            if not path:
                continue
            local = self._contained(staged_root, path)
            if local is not None and local.is_file():
                try:
                    expected = int(item.get("size_bytes", 0) or 0)
                    if not expected or local.stat().st_size == expected:
                        continue
                    # Size mismatch on the exact path — still missing.
                    missing.append(path)
                    continue
                except Exception:
                    continue
            # Exact path absent (or unsafe): accept a same-named file
            # anywhere under files_dir as staged.
            try:
                if _Path(path).name and _Path(path).name in staged_basenames:
                    continue
            except Exception:
                pass
            if local is None:
                # Can never be staged safely — surface it, don't silently skip.
                missing.append(path)
                continue
            missing.append(path)
        return missing

    def is_fully_staged(self, persistent_id: str, inventory: list | None = None) -> bool:
        """True when every inventory file is already staged with matching size."""
        try:
            inv = inventory if inventory is not None else self.inventory(persistent_id)
            return bool(inv) and not self.missing_files(persistent_id, inv)
        except Exception:
            return False

    # -- on-disk metadata / manifest / reports --------------------------------

    def save_metadata(self, persistent_id: str, metadata: dict, inventory: list) -> None:
        """Cache dataset metadata + file manifest beside the downloads."""
        try:
            import json as _json

            base = self.dataset_dir(persistent_id)
            base.mkdir(parents=True, exist_ok=True)
            self.metadata_path(persistent_id).write_text(
                _json.dumps(metadata or {}, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            self.manifest_path(persistent_id).write_text(
                _json.dumps(inventory or [], indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception:
            pass

    def load_metadata(self, persistent_id: str) -> tuple:
        """Cached (metadata, inventory) or (None, None) — never raises."""
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
        progress: Optional[Callable[[int], None]] = None,
    ) -> Path:
        """Download the bundle and stage its contents for the check engine.

        Afterwards, original-format uploads are fetched per tabular file
        (the bundle only carries server-generated .tab derivatives).
        """
        dest_dir = self.dataset_dir(persistent_id)
        part = dest_dir / "_bundle.zip.part"
        bundle = dest_dir / "_bundle.zip"
        self._client.download_dataset_zip(
            persistent_id, part, progress=progress
        )
        # Only publish the bundle on a complete download — a killed run
        # leaves .part behind, never a truncated _bundle.zip.
        part.replace(bundle)
        self._extract(bundle, self.files_dir(persistent_id))
        bundle.unlink()
        try:
            self.download_originals(persistent_id, progress=progress)
        except Exception:
            pass
        return self.files_dir(persistent_id)

    def download_originals(
        self,
        persistent_id: str,
        inventory: list | None = None,
        progress: Optional[Callable[[int], None]] = None,
    ) -> List[str]:
        """Fetch original uploads behind tabular .tab derivatives.

        Returns staged original paths. Skips files already staged with a
        matching size. Never raises — per-file failures are collected and
        ignored (the .tab remains available for checks).
        """
        try:
            inv = inventory if inventory is not None else self.inventory(persistent_id)
        except Exception:
            return []
        root = self.files_dir(persistent_id)
        staged: List[str] = []
        for item in inv:
            try:
                if not item.get("tabular"):
                    continue
                file_id = str(item.get("id") or "")
                original_name = str(item.get("original_name") or "")
                if not file_id or not original_name:
                    continue
                rel = Path(item.get("path", "") or "")
                # original_name is a bare file name; rel.parent carries any
                # subdirectory. Both are containment-checked as one path.
                if str(rel.parent) not in ("", "."):
                    target = rel.parent / Path(original_name).name
                else:
                    target = Path(Path(original_name).name)
                dest = self._contained(root, target.as_posix())
                if dest is None:
                    continue
                expected = int(item.get("original_size", 0) or 0)
                if dest.is_file() and (not expected or dest.stat().st_size == expected):
                    staged.append(dest.relative_to(root).as_posix())
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                self._client.download_datafile_original(file_id, dest, progress=progress)
                staged.append(dest.relative_to(root).as_posix())
            except Exception:
                continue
        return staged

    @staticmethod
    def _is_tabular(item: dict) -> bool:
        return bool(item.get("tabular")) or str(item.get("path", "")).lower().endswith(".tab")

    def verify(self, persistent_id: str) -> Tuple[bool, List[str], List[str]]:
        """Rehash staged files against the Dataverse inventory checksums.

        Returns (ok, problems, warnings). Missing files, unsupported
        algorithms and non-tabular mismatches are blocking problems.
        `.tab` mismatches are warnings, not errors: tabular files are
        server-regenerated ingest products whose stored checksum can predate
        the download — the message carries hashes, size and the file's UNF
        for manual comparison (see docs/user-guide.md "Checksum problems").
        """
        inventory = self._client.get_file_inventory(persistent_id)
        staged_root = self.files_dir(persistent_id)
        problems: List[str] = []
        warnings: List[str] = []
        for item in inventory:
            rel = str(item.get("path", "") or "")
            if not rel or not isinstance(item, dict):
                problems.append("malformed inventory entry (missing path)")
                continue
            local = self._contained(staged_root, rel)
            if local is None:
                problems.append(f"unsafe path (outside workspace): {rel}")
                continue
            if not local.exists():
                problems.append(f"missing: {rel}")
                continue
            if not item.get("checksum_value"):
                warnings.append(f"no checksum recorded for {rel} — integrity unverified")
                continue
            algorithm = item.get("checksum_type") or "md5"
            try:
                actual = self._hash_file(local, algorithm)
            except ValueError:
                problems.append(
                    f"unsupported checksum type '{algorithm}' for {rel}"
                )
                continue
            expected = str(item["checksum_value"]).lower()
            if actual != expected:
                try:
                    size = local.stat().st_size
                except Exception:
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
                    warnings.append(line)
                else:
                    problems.append(line)
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
                    raise RuntimeError(
                        f"unsafe archive entry (symlink): {member.filename}"
                    )
                target = (dest / member.filename).resolve()
                if not target.is_relative_to(root):
                    raise RuntimeError(
                        f"unsafe archive entry: {member.filename}"
                    )
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