"""GeoPackage inspection via SQLite (a GeoPackage is an SQLite container).

Port of CUR_Res_CurationTools Scripts/Inspect_gpkg_Script.R: layer listing
with geometry types, CRS and feature counts; empty-file and read-failure
detection. Uses the gpkg_* standard tables instead of GDAL, so no heavy
geospatial stack is required.
"""

import sqlite3
from pathlib import Path

from engine.checks.base import Check, CheckResult

_GPKG_APPLICATION_ID = int.from_bytes(b"GPKG", "big")
_UNDEFINED_SRS = {-1, 0}
_MAX_LAYERS = 50


def _connect_readonly(path: Path) -> sqlite3.Connection:
    from engine.checks._util import sqlite_uri

    return sqlite3.connect(sqlite_uri(path), uri=True)


def _scalar(conn: sqlite3.Connection, sql: str) -> object:
    return conn.execute(sql).fetchone()[0]


class GpkgCheck(Check):
    """GeoPackage check - port of the CUR_Res_CurationTools R inspector."""

    check_id = "format.gpkg"
    extensions = {".gpkg"}

    def run(self, files: list[Path]) -> list[CheckResult]:
        # Per-file isolation like every other check: one bad file must not
        # kill the whole batch (run_per_file converts faults to findings).
        from engine.checks._util import run_per_file

        return run_per_file(self, files, self._run_one)

    def _run_one(self, path: Path) -> list[CheckResult]:
        from engine.checks._util import quoted_ident
        from engine.checks._util import skipped as _skipped

        name = path.name
        try:
            conn = _connect_readonly(path)
        except sqlite3.Error as exc:
            return [
                CheckResult(
                    check_id="format.gpkg.valid",
                    level="error",
                    passed=False,
                    message=f"{name}: read failed ({exc})",
                ),
                _skipped(
                    "format.gpkg.layers",
                    f"{name}: layer scan skipped (unreadable file)",
                ),
                _skipped(
                    "format.gpkg.crs",
                    f"{name}: CRS scan skipped (unreadable file)",
                ),
            ]

        try:
            # NOTE: connect() is lazy — a non-database file only fails here,
            # so everything below stays inside the guarded region.
            application_id = _scalar(conn, "PRAGMA application_id")
            if application_id != _GPKG_APPLICATION_ID:
                return [
                    CheckResult(
                        check_id="format.gpkg.valid",
                        level="error",
                        passed=False,
                        message=(
                            f"{name}: not a GeoPackage "
                            f"(application_id {application_id:#x})"
                        ),
                    ),
                    _skipped(
                        "format.gpkg.layers",
                        f"{name}: layer scan skipped (not a GeoPackage)",
                    ),
                    _skipped(
                        "format.gpkg.crs",
                        f"{name}: CRS scan skipped (not a GeoPackage)",
                    ),
                ]

            try:
                contents = conn.execute(
                    "SELECT table_name, data_type FROM gpkg_contents"
                ).fetchall()
                geometry = {
                    table_name: (geom_type, srs_id)
                    for table_name, geom_type, srs_id in conn.execute(
                        "SELECT table_name, geometry_type_name, srs_id "
                        "FROM gpkg_geometry_columns"
                    )
                }
                defined_srs = {
                    srs_id
                    for srs_id, org, org_id in conn.execute(
                        "SELECT srs_id, organization, organization_coordsys_id "
                        "FROM gpkg_spatial_ref_sys"
                    )
                    if org or org_id is not None
                }
            except sqlite3.Error as exc:
                return [
                    CheckResult(
                        check_id="format.gpkg.valid",
                        level="error",
                        passed=False,
                        message=f"{name}: invalid GeoPackage tables ({exc})",
                    ),
                    _skipped(
                        "format.gpkg.layers",
                        f"{name}: layer scan skipped (invalid tables)",
                    ),
                    _skipped(
                        "format.gpkg.crs",
                        f"{name}: CRS scan skipped (invalid tables)",
                    ),
                ]

            layers = []
            for table_name, data_type in contents[:_MAX_LAYERS]:
                geom_type, srs_id = geometry.get(table_name, (None, None))
                features = None
                if data_type == "features":
                    try:
                        features = _scalar(
                            conn, f"SELECT COUNT(*) FROM {quoted_ident(table_name)}"
                        )
                    except sqlite3.Error:
                        features = None
                layers.append(
                    {
                        "name": table_name,
                        "type": data_type,
                        "geometry": geom_type,
                        "srs_id": srs_id,
                        "features": features,
                    }
                )

            valid = CheckResult(
                check_id="format.gpkg.valid",
                level="info",
                passed=True,
                message=f"{name}: valid GeoPackage",
            )

            if not layers:
                empty = CheckResult(
                    check_id="format.gpkg.layers",
                    level="warning",
                    passed=False,
                    message=f"{name}: empty GPKG (0 layers)",
                )
                return [
                    valid,
                    empty,
                    _skipped(
                        "format.gpkg.crs",
                        f"{name}: CRS scan skipped (0 layers)",
                    ),
                ]

            layers_result = CheckResult(
                check_id="format.gpkg.layers",
                level="info",
                passed=True,
                message=f"{name}: {len(contents)} layer(s)",
                details={"layers": layers},
            )

            undefined = [
                layer["name"]
                for layer in layers
                if layer["srs_id"] is None
                or layer["srs_id"] in _UNDEFINED_SRS
                or (defined_srs and layer["srs_id"] not in defined_srs)
            ]
            crs = CheckResult(
                check_id="format.gpkg.crs",
                level="warning" if undefined else "info",
                passed=not undefined,
                message=(
                    f"{name}: layers without a defined CRS: "
                    + ", ".join(undefined)
                    if undefined
                    else f"{name}: all layers have a defined CRS"
                ),
            )

            return [valid, layers_result, crs]
        except sqlite3.Error as exc:
            return [
                CheckResult(
                    check_id="format.gpkg.valid",
                    level="error",
                    passed=False,
                    message=f"{name}: read failed ({exc})",
                ),
                _skipped(
                    "format.gpkg.layers",
                    f"{name}: layer scan skipped (read failed)",
                ),
                _skipped(
                    "format.gpkg.crs",
                    f"{name}: CRS scan skipped (read failed)",
                ),
            ]
        finally:
            try:
                conn.close()
            except Exception:
                pass
