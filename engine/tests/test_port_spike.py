"""Phase 1 port-spike tests against CUR_Res_CurationTools sample data.

Run the ported checks and assert parity of findings. Skipped
automatically when the sibling repo or its samples are absent.
"""

from pathlib import Path

import pytest

from engine.checks.gpkg_check import GpkgCheck
from engine.checks.nc_check import NcCheck
from engine.checks.sas7bdat_check import Sas7bdatCheck

CUR_DATA = Path(__file__).resolve().parents[3] / "CUR_Res_CurationTools" / "data"

requires_samples = pytest.mark.skipif(
    not CUR_DATA.exists(), reason="CUR_Res_CurationTools sample data not found"
)


def _files(subdirectory: str, suffix: str):
    directory = CUR_DATA / subdirectory
    return sorted(directory.rglob(f"*{suffix}"))


@requires_samples
def test_sas_dictionary_extracted():
    files = _files("Inspect_sas7bdat", ".sas7bdat")
    assert files, "expected .sas7bdat samples"

    results = Sas7bdatCheck().run(files)
    by_id = {}
    for result in results:
        by_id.setdefault(result.check_id, []).append(result)

    opened = by_id["format.sas.openable"]
    assert any(r.passed for r in opened), "at least one SAS file should parse"

    dictionaries = [r for r in by_id["format.sas.dictionary"] if r.passed]
    assert dictionaries
    variables = dictionaries[0].details["variables"]
    assert variables and all("name" in v and "type" in v for v in variables)

    for result in results:
        assert result.level in {"info", "warning", "error"}


@requires_samples
def test_gpkg_layers_and_crs():
    files = _files("Inspect_gpkg", ".gpkg")
    assert files, "expected .gpkg samples"

    results = GpkgCheck().run(files[:2])
    valid = [r for r in results if r.check_id == "format.gpkg.valid"]
    assert valid and all(r.passed for r in valid), "samples should be valid GPKG"

    layers = [r for r in results if r.check_id == "format.gpkg.layers" and r.passed]
    assert layers, "samples should contain layers"
    first_layer = layers[0].details["layers"][0]
    assert first_layer["name"]


@requires_samples
def test_netcdf_georeferenced():
    files = _files("Inspect_Images", ".nc") or _files("Inspect_xml", ".nc")
    assert files, "expected .nc samples"

    results = NcCheck().run(files)
    spatial = [r for r in results if r.check_id == "format.netcdf.spatial"]
    assert spatial
    assert any(r.passed for r in spatial), "ERA5/CHIRPS-style nc should be georeferenced"

    openable = [r for r in results if r.check_id == "format.netcdf.openable"]
    assert openable and any(r.passed for r in openable)
