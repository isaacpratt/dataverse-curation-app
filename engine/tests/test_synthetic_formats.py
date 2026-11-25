"""Format-check coverage from fixtures the repository owns (dv-3wd).

The parity tests read an optional sibling clone and are deselected in CI,
which left the binary-format checks at 18-41% there. Every library these
checks use is a declared dependency, so small valid and corrupt files can
be generated in tmp_path and the checks exercised on any machine.
"""

from __future__ import annotations

import sqlite3
import zipfile
from pathlib import Path

import pytest

from engine.checks.base import CheckResult
from engine.checks.dta_check import DtaCheck
from engine.checks.fastq_check import FastqCheck
from engine.checks.gpkg_check import GpkgCheck
from engine.checks.hdf5_check import Hdf5Check
from engine.checks.images_check import ImagesCheck
from engine.checks.nc_check import NcCheck
from engine.checks.pdf_check import PdfCheck
from engine.checks.sav_check import SavCheck
from engine.checks.sqlite_check import SqliteCheck
from engine.checks.tiff_check import TiffCheck
from engine.checks.xml_check import XmlCheck


def _assert_results(results: list[CheckResult]) -> None:
    assert results, "a check must emit at least one finding"
    assert all(r.level in {"info", "warning", "error"} for r in results)
    assert all(r.message for r in results)


def test_sqlite_valid_corrupt_and_empty(tmp_path: Path) -> None:
    valid = tmp_path / "valid.sqlite"
    with sqlite3.connect(valid) as conn:
        conn.execute("CREATE TABLE deposits (id INTEGER, title TEXT)")
        conn.execute("INSERT INTO deposits VALUES (1, 'A study')")
    broken = tmp_path / "broken.sqlite"
    broken.write_bytes(b"not a database" * 20)
    empty = tmp_path / "empty.sqlite"
    empty.write_bytes(b"")

    for path in (valid, broken, empty):
        results = SqliteCheck().run([path])
        _assert_results(results)
    valid_results = SqliteCheck().run([valid])
    assert any(r.passed for r in valid_results)
    assert any(not r.passed and r.level == "error" for r in SqliteCheck().run([broken]))


def test_hdf5_datasets_and_external_link(tmp_path: Path) -> None:
    h5py = pytest.importorskip("h5py")
    path = tmp_path / "data.h5"
    with h5py.File(path, "w") as handle:
        handle.create_dataset("values", data=[1, 2, 3])
        handle.create_dataset("labels", data=["a", "b", "c"])
        handle["external"] = h5py.ExternalLink("other.h5", "values")
    results = Hdf5Check().run([path])
    _assert_results(results)
    assert "external" in _details_text(results)

    corrupt = tmp_path / "broken.h5"
    corrupt.write_bytes(b"not hdf5")
    _assert_results(Hdf5Check().run([corrupt]))


def _details_text(results: list[CheckResult]) -> str:
    return " ".join(str(r.details) + r.message for r in results).lower()


def test_netcdf_variables_and_missing_units(tmp_path: Path) -> None:
    nc4 = pytest.importorskip("nc4")
    path = tmp_path / "grid.nc"
    with nc4.Dataset(path, "w") as ds:
        ds.createDimension("lat", 2)
        ds.createDimension("lon", 2)
        lat = ds.createVariable("lat", "f4", ("lat",))
        lat.units = "degrees_north"
        lon = ds.createVariable("lon", "f4", ("lon",))
        lon.units = "degrees_east"
        temp = ds.createVariable("temperature", "f4", ("lat", "lon"))
        temp[:] = [[1, 2], [3, 4]]
    results = NcCheck().run([path])
    _assert_results(results)

    corrupt = tmp_path / "broken.nc"
    corrupt.write_bytes(b"not netcdf")
    _assert_results(NcCheck().run([corrupt]))


@pytest.mark.parametrize("suffix", [".png", ".jpg", ".gif", ".bmp", ".webp"])
def test_images_valid_and_corrupt(tmp_path: Path, suffix: str) -> None:
    pil_image = pytest.importorskip("PIL.Image")
    path = tmp_path / f"image{suffix}"
    image = pil_image.new("RGB", (8, 8), color="red")
    image.save(path)
    results = ImagesCheck().run([path])
    _assert_results(results)
    assert any(r.passed for r in results)

    corrupt = tmp_path / f"broken{suffix}"
    corrupt.write_bytes(path.read_bytes()[:12])
    _assert_results(ImagesCheck().run([corrupt]))


def test_xml_wellformed_malformed_and_namespaced(tmp_path: Path) -> None:
    good = tmp_path / "good.xml"
    good.write_text('<?xml version="1.0"?><root><item id="1">A</item></root>', encoding="utf-8")
    ns = tmp_path / "namespaced.xml"
    ns.write_text(
        '<r xmlns="urn:test"><x>1</x></r>',
        encoding="utf-8",
    )
    bad = tmp_path / "bad.xml"
    bad.write_text("<root><item></root>", encoding="utf-8")
    for path in (good, ns, bad):
        results = XmlCheck().run([path])
        _assert_results(results)
    assert any(r.passed for r in XmlCheck().run([good]))
    assert any(not r.passed for r in XmlCheck().run([bad]))


def test_tiff_valid_and_truncated(tmp_path: Path) -> None:
    tifffile = pytest.importorskip("tifffile")
    import numpy as np

    path = tmp_path / "stack.tiff"
    tifffile.imwrite(path, np.zeros((2, 8, 8), dtype="uint8"))
    results = TiffCheck().run([path])
    _assert_results(results)
    assert any(r.passed for r in results)

    broken = tmp_path / "broken.tiff"
    broken.write_bytes(b"II*\x00" + b"\x00" * 20)
    _assert_results(TiffCheck().run([broken]))


def _pdf_with_text(with_text: bool) -> bytes:
    content = b"BT /F1 12 Tf 72 720 Td (Hello curation) Tj ET" if with_text else b""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    ).encode()
    return bytes(out)


def test_pdf_text_layer_and_scanned(tmp_path: Path) -> None:
    text_pdf = tmp_path / "text.pdf"
    text_pdf.write_bytes(_pdf_with_text(True))
    scanned_pdf = tmp_path / "scanned.pdf"
    scanned_pdf.write_bytes(_pdf_with_text(False))
    for path in (text_pdf, scanned_pdf):
        results = PdfCheck().run([path])
        _assert_results(results)
    assert any(r.passed for r in PdfCheck().run([text_pdf]))


def test_spss_and_stata_corrupt_files(tmp_path: Path) -> None:
    # pyreadstat's writers now require a narwhals DataFrame and pandas is
    # not a dependency here; corrupt inputs still exercise the open/error
    # paths of both checks without any external sample data.
    for check, name in ((SavCheck(), "broken.sav"), (DtaCheck(), "broken.dta")):
        path = tmp_path / name
        path.write_bytes(b"not a statistical file")
        _assert_results(check.run([path]))
        assert any(not r.passed for r in check.run([path]))


def test_geopackage_like_sqlite(tmp_path: Path) -> None:
    path = tmp_path / "layers.gpkg"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE gpkg_spatial_ref_sys (srs_id INTEGER, srs_name TEXT)")
        conn.execute("CREATE TABLE gpkg_contents (table_name TEXT, data_type TEXT)")
        conn.execute("INSERT INTO gpkg_spatial_ref_sys VALUES (4326, 'WGS 84')")
        conn.execute("INSERT INTO gpkg_contents VALUES ('places', 'features')")
        conn.execute("CREATE TABLE places (fid INTEGER PRIMARY KEY, geom BLOB)")
    results = GpkgCheck().run([path])
    _assert_results(results)

    junk = tmp_path / "junk.gpkg"
    junk.write_bytes(b"not a geopackage")
    _assert_results(GpkgCheck().run([junk]))


def test_fastq_valid_and_malformed(tmp_path: Path) -> None:
    good = tmp_path / "reads.fastq"
    good.write_text("@r1\nACGT\n+\nIIII\n", encoding="utf-8")
    bad = tmp_path / "bad.fastq"
    bad.write_text("@r1\nACGT\n+\nII\n", encoding="utf-8")
    assert any(r.passed for r in FastqCheck().run([good]))
    assert any(not r.passed for r in FastqCheck().run([bad]))


def test_archive_member_cap_and_traversal(tmp_path: Path) -> None:
    from engine.checks.containers_check import ContainersCheck

    safe = tmp_path / "safe.zip"
    with zipfile.ZipFile(safe, "w") as archive:
        archive.writestr("a.txt", "hello")
        archive.writestr("sub/b.txt", "world")
    unsafe = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(unsafe, "w") as archive:
        archive.writestr("../escape.txt", "bad")
    for path in (safe, unsafe):
        _assert_results(ContainersCheck().run([path]))
    assert any(not r.passed for r in ContainersCheck().run([unsafe]))
