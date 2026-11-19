"""NetCDF inspection.

Port of CUR_Res_CurationTools Scripts/Inspect_nc_Script.R Phase A
(usability scan): safe load, dimension summary, variable count, spatial
reference check (lat/lon dimensions or grid_mapping attribute) and a data
health sample of the first variable.
"""

import re
from pathlib import Path
from typing import Any, ClassVar

from engine.checks.base import Check, CheckResult

_LAT = re.compile(r"(?i)(^|_)(lat|latitude|xlat)($|_|[^a-z])|^y$")
_LON = re.compile(r"(?i)(^|_)(lon|lng|long|longitude|xlong)($|_|[^a-z])|^x$")
_SAMPLE_VALUES = 100


def _is_georeferenced(ds: Any) -> bool:
    dim_names = list(ds.dimensions)
    has_lat = any(_LAT.search(n) for n in dim_names)
    has_lon = any(_LON.search(n) for n in dim_names)
    if has_lat and has_lon:
        return True
    for var in ds.variables.values():
        if "grid_mapping" in var.ncattrs():
            return True
    return "crs" in ds.variables


def _data_health(ds: Any) -> tuple[str, bool]:
    """Return (message, healthy). Mirrors the R 'All NaNs (Empty)' scan."""
    if not ds.variables:
        return ("no variables", False)
    first = next(iter(ds.variables.values()))
    if not first.dimensions:
        return ("scalar variable, skipped", True)
    if getattr(first.dtype, "kind", "") not in "biufc":
        return ("non-numeric variable, skipped", True)
    try:
        import numpy as np

        per_dim = max(1, int(np.ceil(_SAMPLE_VALUES ** (1 / len(first.dimensions)))))
        index = tuple(slice(0, min(per_dim, ds.dimensions[d].size)) for d in first.dimensions)
        values = np.ma.compressed(first[index])
        if values.size == 0 or np.all(np.isnan(values.astype("float64"))):
            return ("all NaNs (empty)", False)
        return ("contains data", True)
    except Exception:
        return ("could not sample values", False)


class NcCheck(Check):
    """NetCDF check - port of the CUR_Res_CurationTools R inspector."""

    check_id = "format.netcdf"
    scope: ClassVar[str] = "file"
    extensions: ClassVar[set[str]] = {".nc", ".cdf"}

    def run(self, files: list[Path]) -> list[CheckResult]:
        # Per-file isolation: a fault in one file becomes a finding, never a
        # batch-killing crash (the `with ds:` body below is fallible).
        from engine.checks._util import run_per_file

        return run_per_file(self, files, self._run_one)

    def _run_one(self, path: Path) -> list[CheckResult]:
        try:
            from netCDF4 import Dataset
        except ImportError:
            from engine.checks._util import missing_library
            from engine.checks._util import skipped as _skipped

            return [
                missing_library("format.netcdf.openable", "netCDF4"),
                _skipped(
                    "format.netcdf.metadata",
                    f"{path.name}: metadata skipped (netCDF4 not installed)",
                ),
                _skipped(
                    "format.netcdf.spatial",
                    f"{path.name}: spatial scan skipped (netCDF4 not installed)",
                ),
                _skipped(
                    "format.netcdf.data_health",
                    f"{path.name}: data-health skipped (netCDF4 not installed)",
                ),
            ]
        name = path.name
        try:
            ds = Dataset(str(path), "r")
        except Exception as exc:
            from engine.checks._util import skipped as _skipped2

            return [
                CheckResult(
                    check_id="format.netcdf.openable",
                    level="error",
                    passed=False,
                    message=f"{name}: corrupt/unreadable ({exc})",
                ),
                _skipped2(
                    "format.netcdf.metadata",
                    f"{name}: metadata skipped (unreadable file)",
                ),
                _skipped2(
                    "format.netcdf.spatial",
                    f"{name}: spatial scan skipped (unreadable file)",
                ),
                _skipped2(
                    "format.netcdf.data_health",
                    f"{name}: data-health skipped (unreadable file)",
                ),
            ]

        with ds:
            dim_names = list(ds.dimensions)
            var_count = len(ds.variables)

            metadata = CheckResult(
                check_id="format.netcdf.metadata",
                level="info",
                passed=True,
                message=(
                    f"{name}: {var_count} variables, "
                    f"{len(dim_names)} dimensions ({' x '.join(dim_names)})"
                ),
                details={
                    "dimensions": dim_names,
                    "variables": var_count,
                },
            )

            geo = _is_georeferenced(ds)
            spatial = CheckResult(
                check_id="format.netcdf.spatial",
                level="info" if geo else "warning",
                passed=geo,
                message=(
                    f"{name}: georeferenced"
                    if geo
                    else f"{name}: no spatial grid (no lat/lon dims or grid_mapping)"
                ),
            )

            health_msg, healthy = _data_health(ds)
            health = CheckResult(
                check_id="format.netcdf.data_health",
                level="info" if healthy else "warning",
                passed=healthy,
                message=f"{name}: first variable {health_msg}",
            )

            return [
                CheckResult(
                    check_id="format.netcdf.openable",
                    level="info",
                    passed=True,
                    message=f"{name}: valid NetCDF",
                ),
                metadata,
                spatial,
                health,
            ]
