"""Lite-build smoke: the excluded heavy libraries must stay out of the build."""

from __future__ import annotations

import pathlib
from pathlib import Path

from tools.smoke_lite import HEAVY_MODULES, find_heavy_modules


def _touch(root: pathlib.Path, name: str) -> None:
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("", encoding="utf-8")


def test_clean_tree_has_no_heavy_modules(tmp_path: Path) -> None:
    assert find_heavy_modules(tmp_path) == []


def test_detects_a_bundled_module_directory(tmp_path: Path) -> None:
    _touch(tmp_path, "scipy")
    assert find_heavy_modules(tmp_path) == ["scipy"]


def test_detects_a_bundled_binary(tmp_path: Path) -> None:
    _touch(tmp_path, "h5py.cp311-win_amd64.pyd")
    assert find_heavy_modules(tmp_path) == ["h5py"]


def test_detects_every_excluded_library(tmp_path: Path) -> None:
    for name in HEAVY_MODULES:
        _touch(tmp_path, name)
    assert find_heavy_modules(tmp_path) == sorted(HEAVY_MODULES)


def test_missing_root_is_not_an_error(tmp_path: Path) -> None:
    assert find_heavy_modules(tmp_path / "does-not-exist") == []
