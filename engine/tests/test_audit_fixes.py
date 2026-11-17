"""Regression tests for the audit fix batches (no network, no GUI).

Covers: compound-extension dispatch, missing-library contract, zip-slip
guards, download atomicity/containment, scan caps, severity taxonomy and
the runner's unchecked-types hint.
"""

import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Any

import pytest

from download_manager import DownloadManager
from engine.checks._util import detect_encoding, missing_library
from engine.checks.code_check import CodeCheck
from engine.checks.containers_check import ContainersCheck
from engine.checks.csv_check import CsvCheck
from engine.checks.extensions_check import ExtensionsCheck
from engine.checks.fastq_check import FastqCheck
from engine.checks.hdf5_check import Hdf5Check
from engine.checks.images_check import ImagesCheck
from engine.checks.pdf_check import PdfCheck
from engine.checks.text_check import TextCheck
from engine.checks.tiff_check import TiffCheck
from engine.checks.xlsx_check import XlsxCheck
from engine.checks.xml_check import XmlCheck
from engine.dispatcher import checks_for_file
from engine.runner import collect_files, list_planned_checks, run_report

# -- dispatcher -----------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("sample.fq.gz", {"format.fastq"}),
        ("sample.fastq", {"format.fastq"}),
        ("a.tar.gz", {"format.containers"}),
        ("a.tgz", {"format.containers"}),
        ("a.tar", {"format.containers"}),
        ("data.gz", {"format.containers"}),
        ("d.csv", {"format.csv"}),
        ("x.mat", set()),
    ],
)
def test_compound_extension_dispatch(name: str, expected: Any) -> None:
    assert {c.check_id for c in checks_for_file(Path(name))} == expected


def test_planned_matches_dispatch(tmp_path: Path) -> None:
    files = []
    for name in ("a.fq.gz", "b.csv", "c.mat"):
        p = tmp_path / name
        p.write_text("x")
        files.append(p)
    by_id = {p["check_id"]: p for p in list_planned_checks(files)}
    assert by_id["format.fastq"]["will_run"] is True
    assert by_id["format.fastq"]["matching_files"] == 1


# -- missing-library contract ----------------------------------------------


def test_missing_library_contract() -> None:
    result = missing_library("format.xlsx.openable", "openpyxl")
    assert result.level == "warning"
    assert result.passed is True
    assert "Missing" in result.message
    assert result.details.get("skipped") is True


@pytest.mark.parametrize(
    ("module", "cls", "file_suffix", "result_id"),
    [
        ("openpyxl", XlsxCheck, ".xlsx", "format.xlsx.openable"),
        ("h5py", Hdf5Check, ".h5", "format.hdf5.openable"),
        ("tifffile", TiffCheck, ".tif", "format.tiff.valid"),
        ("pypdf", PdfCheck, ".pdf", "format.pdf.openable"),
        ("lxml", XmlCheck, ".xml", "format.xml.valid"),
        # NOTE: PIL/preset ImagesCheck intentionally excluded — images have a
        # pure-stdlib header fallback, so a missing Pillow no longer yields a
        # "Missing" warning (see test_images_stdlib_fallback_* below).
    ],
)
def test_optional_import_guard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    module: Any,
    cls: Any,
    file_suffix: str,
    result_id: str,
) -> None:
    monkeypatch.setitem(sys.modules, module, None)
    target = tmp_path / f"sample{file_suffix}"
    target.write_bytes(b"\x00\x01\x02")
    results = cls().run([target])
    # Always-emit: missing-lib openable + skipped siblings (never a lone row).
    by_id = {r.check_id: r for r in results}
    assert result_id in by_id
    assert by_id[result_id].level == "warning"
    assert by_id[result_id].passed is True
    assert by_id[result_id].details.get("skipped") is True
    for r in results:
        if r.check_id != result_id:
            assert r.details.get("skipped") is True
            assert r.passed is True


def test_images_stdlib_fallback_without_pillow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """JPG/PNG still validate via stdlib headers when Pillow is absent."""
    import struct

    monkeypatch.setitem(sys.modules, "PIL", None)
    monkeypatch.setitem(sys.modules, "PIL.Image", None)
    monkeypatch.setitem(sys.modules, "PIL.ImageFile", None)
    # Minimal 1x1 PNG: signature + IHDR (width=1, height=1, color type 2).
    png = tmp_path / "tiny.png"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    png.write_bytes(
        b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + ihdr + b"\x00\x00\x00\x00"
    )
    results = ImagesCheck().run([png])
    assert len(results) == 1
    assert results[0].check_id == "format.images.valid"
    assert "Missing" not in results[0].message
    assert results[0].passed is True
    assert results[0].details.get("width") == 1


def test_corrupt_png_reports_error_not_crash(tmp_path: Path) -> None:
    """Mypy dv-q9m catch: Pillow 12 removed ImageFile.TruncatedFileError.

    Evaluating a stale `except ImageFile.TruncatedFileError` clause raises
    AttributeError the moment it is needed, so a broken raster surfaced as
    "inspection failed" (or crashed) instead of a clean error finding.
    """
    pytest.importorskip("PIL.Image")
    import struct

    bad = tmp_path / "truncated.png"
    # Valid 8-byte PNG signature + IHDR for a 1x1 image, then a truncated
    # IDAT chunk: decoders reject it, the handler must report it.
    bad.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + bytes.fromhex("0000000d49484452")
        + struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
        + bytes.fromhex("0000000a49444154789c6300010000050001")
    )
    results = ImagesCheck().run([bad])
    assert len(results) == 1
    assert results[0].check_id == "format.images.valid"
    assert results[0].level == "error"
    assert results[0].passed is False
    assert "inspection failed" not in results[0].message
    assert "truncated" in results[0].message or "unreadable" in results[0].message


def test_images_stdlib_fallback_rejects_garbage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "PIL", None)
    monkeypatch.setitem(sys.modules, "PIL.Image", None)
    monkeypatch.setitem(sys.modules, "PIL.ImageFile", None)
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"\x00\x01\x02")
    results = ImagesCheck().run([bad])
    assert results[0].check_id == "format.images.valid"
    assert results[0].passed is False
    assert results[0].level == "error"


def test_chardet_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "chardet", None)
    target = tmp_path / "a.txt"
    target.write_bytes(b"plain ascii")
    assert detect_encoding(target) == "utf-8"


# -- containers guards ------------------------------------------------------


def test_zip_unsafe_entry_flagged(tmp_path: Path) -> None:
    bundle = tmp_path / "evil.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("ok.txt", "fine")
        archive.writestr("../escape.txt", "x")
    results = ContainersCheck().run([bundle])
    by_id = {r.check_id: r for r in results}
    assert by_id["format.containers.valid"].passed is True
    unsafe = by_id["format.containers.unsafe_entry"]
    assert unsafe.passed is False
    assert unsafe.level == "warning"


def test_tar_nested_macosx_and_unsafe(tmp_path: Path) -> None:
    bundle = tmp_path / "evil.tar"
    inner = tmp_path / "inner.txt"
    inner.write_text("d")
    with tarfile.open(bundle, "w") as archive:
        archive.add(inner, arcname="ok.txt")
        archive.add(inner, arcname="a/__MACOSX/sub/f.txt")
        archive.add(inner, arcname="sub/../../e.txt")
    results = ContainersCheck().run([bundle])
    by_id = {r.check_id: r for r in results}
    assert by_id["format.containers.valid"].passed is True
    assert by_id["format.containers.unsafe_entry"].passed is False


def test_zip_member_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.checks.containers_check as cc

    monkeypatch.setattr(cc, "_MAX_MEMBERS", 2)
    bundle = tmp_path / "big.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        for i in range(3):
            archive.writestr(f"f{i}.txt", "x")
    results = ContainersCheck().run([bundle])
    assert results[0].level == "warning"
    assert "too many entries" in results[0].message


# -- download hardening ------------------------------------------------------


def test_contained_blocks_traversal(tmp_path: Path) -> None:
    root = tmp_path / "files"
    root.mkdir()
    assert DownloadManager._contained(root, "a/b.csv") is not None
    assert DownloadManager._contained(root, "../evil") is None
    assert DownloadManager._contained(root, "/etc/passwd") is None
    assert DownloadManager._contained(root, "sub/../../evil") is None


def test_extract_atomic_preserves_stage(tmp_path: Path) -> None:
    manager = DownloadManager(object(), tmp_path)
    dest = tmp_path / "stage"
    (dest / "old").mkdir(parents=True)
    (dest / "old" / "keep.txt").write_text("keep")
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    with pytest.raises((zipfile.BadZipFile, OSError, ValueError, RuntimeError)):
        manager._extract(bad, dest)
    assert (dest / "old" / "keep.txt").read_text() == "keep"
    assert not (tmp_path / "stage.new").exists()


def test_verify_rejects_unsafe_and_malformed(tmp_path: Path) -> None:
    class FakeClient:
        def get_file_inventory(self, pid: str) -> list[dict[str, Any]]:
            return [
                {
                    "path": "../escape.csv",
                    "size_bytes": 1,
                    "checksum_type": "md5",
                    "checksum_value": "0" * 32,
                },
                {"size_bytes": 1},
            ]

    manager = DownloadManager(FakeClient(), tmp_path / "ws")
    ok, problems, _warnings = manager.verify("pid")
    assert not ok
    assert any("unsafe path" in p for p in problems)
    assert any("malformed" in p for p in problems)


def test_collect_files_skips_symlinks(tmp_path: Path) -> None:
    real = tmp_path / "real.csv"
    real.write_text("a")
    link = tmp_path / "link.csv"
    try:
        link.symlink_to(real)
    except OSError:
        pytest.skip("symlinks unavailable")
    assert collect_files(tmp_path) == [real]


# -- caps, taxonomy, inventory -----------------------------------------------


def test_csv_scan_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.checks.csv_check as csv_mod

    monkeypatch.setattr(csv_mod, "_MAX_ROWS_SCANNED", 10)
    target = tmp_path / "big.csv"
    target.write_text("a,b\n" + "".join(f"{i},{i}\n" for i in range(50)))
    results = CsvCheck().run([target])
    content = next(r for r in results if r.check_id == "format.csv.content")
    assert content.details["truncated"] is True
    assert "sampled" in content.message


def test_empty_files_are_errors(tmp_path: Path) -> None:
    csv_empty = tmp_path / "e.csv"
    csv_empty.write_bytes(b"")
    (tmp_path / "t.txt").write_bytes(b"")
    csv_res = CsvCheck().run([csv_empty])[0]
    txt_res = next(r for r in TextCheck().run([tmp_path / "t.txt"]) if "empty" in r.message)
    assert (csv_res.level, csv_res.passed) == ("error", False)
    assert (txt_res.level, txt_res.passed) == ("error", False)


def test_todo_markers_are_warnings(tmp_path: Path) -> None:
    target = tmp_path / "s.py"
    target.write_text("# TODO: fix me\nx = 1\n")
    results = CodeCheck().run([target])
    todo = next(r for r in results if r.check_id == "format.code.todo_markers")
    assert (todo.level, todo.passed) == ("warning", False)


def test_fastq_qual_mismatch_flagged(tmp_path: Path) -> None:
    target = tmp_path / "bad.fastq"
    target.write_text("@r1\nACGT\n+\nIII\n")  # qual shorter than seq
    results = FastqCheck().run([target])
    valid = next(r for r in results if r.check_id == "format.fastq.valid")
    assert valid.passed is False


def test_netcdf_name_patterns() -> None:
    from engine.checks.nc_check import _LAT, _LON

    for good in ("lat", "latitude", "grid_lat", "XLAT", "lon", "longitude", "xlong"):
        assert _LAT.search(good) or _LON.search(good), good
    for bad in ("relative", "flat", "dilatation", "clone", "alone"):
        assert not _LAT.search(bad), bad
        assert not _LON.search(bad), bad


def test_extensions_nested_junk_and_single_component(tmp_path: Path) -> None:

    nested = tmp_path / "a" / "__MACOSX" / "sub"
    nested.mkdir(parents=True)
    (nested / "f.txt").write_text("x")
    (tmp_path / "lone.txt").write_text("y")  # single-component relative path
    rels = [p.relative_to(tmp_path) for p in (nested / "f.txt", tmp_path / "lone.txt")]
    results = ExtensionsCheck().run(rels)
    junk = next(r for r in results if r.check_id == "inventory.system_junk")
    assert junk.passed is False


def test_runner_unchecked_types_hint(tmp_path: Path) -> None:
    staged = tmp_path / "ds"
    staged.mkdir()
    (staged / "model.mat").write_bytes(b"\x00" * 16)
    (staged / "note.csv").write_text("a\n1\n")
    report = run_report(staged, persistent_id="doi:10/x")
    hint = next(c for c in report.dataset_checks if c.check_id == "inventory.unchecked_types")
    assert hint.level == "warning"
    assert ".mat" in hint.message
