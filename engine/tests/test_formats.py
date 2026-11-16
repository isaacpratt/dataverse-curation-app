"""Phase 1 port tests for the remaining formats.

Run against CUR_Res_CurationTools sample data (skipped when absent).
"""

from pathlib import Path

import pytest

from engine.checks.code_check import CodeCheck
from engine.checks.containers_check import ContainersCheck
from engine.checks.csv_check import CsvCheck
from engine.checks.dta_check import DtaCheck
from engine.checks.extensions_check import ExtensionsCheck
from engine.checks.fastq_check import FastqCheck
from engine.checks.hdf5_check import Hdf5Check
from engine.checks.images_check import ImagesCheck
from engine.checks.ipynb_check import IpynbCheck
from engine.checks.json_check import JsonCheck
from engine.checks.pdf_check import PdfCheck
from engine.checks.sav_check import SavCheck
from engine.checks.sqlite_check import SqliteCheck
from engine.checks.text_check import TextCheck
from engine.checks.tiff_check import TiffCheck
from engine.checks.xlsx_check import XlsxCheck
from engine.checks.xml_check import XmlCheck

CUR_DATA = Path(__file__).resolve().parents[3] / "CUR_Res_CurationTools" / "data"

requires_samples = pytest.mark.skipif(
    not CUR_DATA.exists(), reason="CUR_Res_CurationTools sample data not found"
)

CASES = [
    ("csv", CsvCheck(), "Inspect_csv"),
    ("xlsx", XlsxCheck(), "Inspect_xlsx"),
    ("sav", SavCheck(), "Inspect_sav"),
    ("dta", DtaCheck(), "Inspect_dta"),
    ("json", JsonCheck(), "Inspect_json"),
    ("xml", XmlCheck(), "Inspect_xml"),
    ("ipynb", IpynbCheck(), "Inspect_ipynb"),
    ("sqlite", SqliteCheck(), "Inspect_sqlite"),
    ("hdf5", Hdf5Check(), "Inspect_hdf5"),
    ("tiff", TiffCheck(), "Inspect_tiff"),
    ("pdf", PdfCheck(), "Inspect_pdf"),
    ("text", TextCheck(), "Inspect_Text"),
    ("code", CodeCheck(), "Inspect_rCode"),
    ("containers", ContainersCheck(), "Inspect_Containers"),
]


def _sample_files(check, subdirectory):
    directory = CUR_DATA / subdirectory
    return sorted(
        path
        for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in check.extensions
    )


@requires_samples
@pytest.mark.parametrize("label,check,subdirectory", CASES, ids=[c[0] for c in CASES])
def test_format_check_on_samples(label, check, subdirectory):
    files = _sample_files(check, subdirectory)
    assert files, f"no {label} samples found in {subdirectory}"

    results = check.run(files)
    assert results, f"{label}: check produced no results"

    for result in results:
        assert result.level in {"info", "warning", "error"}
        assert result.message

    assert any(r.passed for r in results), (
        f"{label}: expected at least one passing finding; got {[r.message for r in results]}"
    )


@requires_samples
def test_extensions_inventory_flags():
    files = sorted(path for path in (CUR_DATA / "Inspect_Extensions").rglob("*") if path.is_file())
    results = ExtensionsCheck().run(files)
    distribution = next(r for r in results if r.check_id == "inventory.extensions")
    assert distribution.passed


def test_images_synthetic(tmp_path):
    from PIL import Image

    path = tmp_path / "sample.png"
    Image.new("RGB", (32, 16), color=(200, 10, 10)).save(path)

    results = ImagesCheck().run([path])
    valid = next(r for r in results if r.check_id == "format.images.valid")
    assert valid.passed
    assert valid.details["width"] == 32
    assert valid.details["height"] == 16


def test_fastq_synthetic(tmp_path):
    records = ""
    for index in range(4):
        records += f"@read{index}\nACGTACGT\n+\nIIIIIIII\n"
    path = tmp_path / "sample.fastq"
    path.write_text(records)

    results = FastqCheck().run([path])
    by_id = {r.check_id: r for r in results}
    assert by_id["format.fastq.valid"].passed
    assert by_id["format.fastq.metadata"].details["reads_sampled"] == 4
    assert by_id["format.fastq.metadata"].details["gc_content"] == 0.5


def test_fastq_gzip(tmp_path):
    import gzip

    path = tmp_path / "sample.fq.gz"
    with gzip.open(path, "wt") as handle:
        handle.write("@r1\nGGCC\n+\n!!!!\n")

    results = FastqCheck().run([path])
    metadata = next(r for r in results if r.check_id == "format.fastq.metadata")
    assert metadata.details["gc_content"] == 1.0
