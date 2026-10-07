"""Sibling full-build folder lookup (`main._sibling_libs_path`).

The lite artefact is an onedir build (`dist/curation-app-lite/curation-app-lite.exe`)
but the lookup must also handle the former onefile layout (exe directly in
`dist/`): both layouts have to resolve a sibling `dist/curation-app-full/`,
and source (non-frozen) runs must never resolve anything.
"""

import sys
from pathlib import Path

import pytest

import main


def _freeze(monkeypatch: pytest.MonkeyPatch, exe: Path) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))


def test_finds_full_beside_onefile_exe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "dist" / "curation-app-full").mkdir(parents=True)
    _freeze(monkeypatch, tmp_path / "dist" / "curation-app-lite.exe")
    assert main._sibling_libs_path() == (tmp_path / "dist" / "curation-app-full").resolve()


def test_finds_full_from_onedir_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "dist" / "curation-app-full").mkdir(parents=True)
    exe = tmp_path / "dist" / "curation-app-lite" / "curation-app-lite.exe"
    exe.parent.mkdir(parents=True)
    _freeze(monkeypatch, exe)
    assert main._sibling_libs_path() == (tmp_path / "dist" / "curation-app-full").resolve()


def test_returns_none_without_full_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exe = tmp_path / "dist" / "curation-app-lite" / "curation-app-lite.exe"
    exe.parent.mkdir(parents=True)
    _freeze(monkeypatch, exe)
    assert main._sibling_libs_path() is None


def test_ignores_source_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python"))
    assert main._sibling_libs_path() is None
