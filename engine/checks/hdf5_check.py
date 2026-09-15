"""HDF5 deep inspection.

Port of CUR_Res_CurationTools Scripts/Inspect_hdf5_Script.R: hierarchy walk,
dataset shapes/dtypes/compression and external-link risk detection.
"""

from pathlib import Path
from typing import List

from engine.checks.base import Check, CheckResult

_MAX_ITEMS_LISTED = 200
# Object-walk cap: a million-group file must not materialize a million
# path strings (only the listing display was capped before).
_MAX_OBJECTS_VISITED = 5000


class Hdf5Check(Check):
    """HDF5 check - port of the CUR_Res_CurationTools R inspector."""

    check_id = "format.hdf5"
    extensions = {".h5", ".hdf5", ".hdf"}

    def run(self, files: List[Path]) -> List[CheckResult]:
        from engine.checks._util import run_per_file

        return run_per_file(self, files, self._run_one)

    def _run_one(self, path: Path) -> List[CheckResult]:
        try:
            import h5py
        except ImportError:
            from engine.checks._util import missing_library

            return [missing_library("format.hdf5.openable", "h5py")]

        name = path.name
        items = []
        external_links = []
        truncated = False
        with h5py.File(str(path), "r") as handle:
            def _visit(obj_path, obj):
                nonlocal truncated
                if truncated:
                    return
                if len(items) + len(external_links) >= _MAX_OBJECTS_VISITED:
                    truncated = True
                    return
                if isinstance(obj, h5py.ExternalLink):
                    external_links.append(obj_path)
                else:
                    items.append(obj_path)

            handle.visititems(_visit)
            datasets = []
            for obj_path in items[:_MAX_ITEMS_LISTED]:
                obj = handle[obj_path]
                if isinstance(obj, h5py.Dataset):
                    datasets.append(
                        {
                            "path": obj_path,
                            "shape": list(obj.shape),
                            "dtype": str(obj.dtype),
                            "compression": obj.compression or "none",
                        }
                    )

        results = [
            CheckResult(
                check_id="format.hdf5.openable",
                level="info",
                passed=True,
                message=(
                    f"{name}: opened ({len(items)}{'+' if truncated else ''} objects, "
                    f"{len(datasets)} dataset(s))"
                    + (" — object walk capped, listing partial" if truncated else "")
                ),
                details={"datasets": datasets, "truncated": truncated},
            )
        ]
        if external_links:
            results.append(
                CheckResult(
                    check_id="format.hdf5.external_links",
                    level="warning",
                    passed=False,
                    message=(
                        f"{name}: external link(s) - dependency on other files: "
                        + ", ".join(external_links)
                    ),
                )
            )
        return results