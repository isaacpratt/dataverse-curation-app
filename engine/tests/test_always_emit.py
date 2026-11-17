"""Always-emit contract: a module run yields one result per owned check_id."""

from pathlib import Path

import pytest

from engine.checks import registry


def _expected_ids() -> dict[str, set[str]]:
    return {
        "inventory.extensions": {
            "inventory.extensions",
            "inventory.zero_byte",
            "inventory.executables",
            "inventory.system_junk",
        },
        "format.containers": {
            "format.containers.valid",
            "format.containers.unsafe_entry",
            "format.containers.encrypted",
        },
        "format.csv": {
            "format.csv.openable",
            "format.csv.structure",
            "format.csv.content",
            "format.csv.pii",
        },
        "format.code": {"format.code.readable", "format.code.todo_markers"},
        "format.secrets": {"format.secrets"},
        "format.text": {
            "format.text.readable",
            "format.text.line_endings",
            "format.text.control_chars",
            "format.text.pii",
        },
        "format.xlsx": {
            "format.xlsx.openable",
            "format.xlsx.sheets",
            "format.xlsx.hidden",
            "format.xlsx.macros",
            "format.xlsx.tabular",
            "format.xlsx.pii",
        },
        "format.hdf5": {"format.hdf5.openable", "format.hdf5.external_links"},
        "format.fastq": {"format.fastq.valid", "format.fastq.metadata"},
        "format.gpkg": {
            "format.gpkg.valid",
            "format.gpkg.layers",
            "format.gpkg.crs",
        },
        "format.ipynb": {
            "format.ipynb.valid",
            "format.ipynb.cells",
            "format.ipynb.executed",
        },
        "format.sqlite": {"format.sqlite.valid", "format.sqlite.manifest"},
        "format.pdf": {"format.pdf.openable", "format.pdf.text"},
        "format.sas": {
            "format.sas.format_detected",
            "format.sas.openable",
            "format.sas.dictionary",
            "format.sas.labels",
            "format.sas.encoding",
        },
        "format.spss": {
            "format.spss.openable",
            "format.spss.dictionary",
            "format.spss.labels",
            "format.spss.encoding",
        },
        "format.stata": {
            "format.stata.openable",
            "format.stata.dictionary",
            "format.stata.labels",
            "format.stata.encoding",
            "format.stata.pii",
        },
        "format.netcdf": {
            "format.netcdf.openable",
            "format.netcdf.metadata",
            "format.netcdf.spatial",
            "format.netcdf.data_health",
        },
    }


def test_clean_files_emit_full_id_sets(tmp_path: Path) -> None:
    expected = _expected_ids()
    samples: dict[str, tuple[str, ...] | None] = {
        "inventory.extensions": None,  # dataset-level, handled below
        "format.containers": ("a.zip",),
        "format.csv": ("a,b\n1,2\n",),
        "format.code": ("x = 1\n",),
        "format.secrets": ("x = 1\n",),
        "format.text": ("hello\n",),
        "format.xlsx": None,  # written below as real workbook via openpyxl path
        "format.fastq": ("@r\nACGT\n+\nIIII\n",),
        "format.ipynb": ('{"nbformat": 4, "cells": []}',),
    }
    import zipfile

    for _check_id, cls in registry.items():
        parent = cls.check_id
        if parent not in expected:
            continue  # single-id modules trivially satisfy the contract
        if parent == "inventory.extensions":
            paths = []
            for i in range(2):
                p = tmp_path / f"f{i}.txt"
                p.write_text("x\n")
                paths.append(p)
            results = cls().run(paths)
            assert {r.check_id for r in results} == expected[parent]
            assert all(r.passed for r in results)
            continue
        if parent not in samples:
            continue
        if parent == "format.containers":
            p = tmp_path / "a.zip"
            with zipfile.ZipFile(str(p), "w") as z:
                z.writestr("a.txt", "hi")
            results = cls().run([p])
        elif parent == "format.ipynb":
            p = tmp_path / "n.ipynb"
            content = samples[parent]
            assert content is not None
            p.write_text(content[0])
            results = cls().run([p])
        elif parent == "format.xlsx":
            openpyxl = pytest.importorskip("openpyxl")
            p = tmp_path / "s.xlsx"
            wb = openpyxl.Workbook()
            wb.active.append(["a", "b"])
            wb.active.append([1, 2])
            wb.save(str(p))
            results = cls().run([p])
        else:
            ext = next(iter(cls.extensions))
            p = tmp_path / f"s{ext}"
            content = samples[parent]
            assert content is not None
            p.write_text(content[0])
            results = cls().run([p])
        assert {r.check_id for r in results} == expected[parent], parent
