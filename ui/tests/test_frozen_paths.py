"""Frozen-mode path resolution: config.json + requirement profiles.

The lite artefact moved onefile → onedir (exe now inside
`dist/curation-app-lite/`), so both resolvers must keep finding the files
that used to sit beside the onefile exe (the folder holding the build),
write fresh files where rebuilds will not wipe them, and leave source
runs and explicit paths untouched.
"""

import sys
from pathlib import Path

import pytest

import config as config_mod
import metadata_check


def _freeze(monkeypatch: pytest.MonkeyPatch, exe: Path) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))


def test_source_run_keeps_cwd_semantics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.chdir(tmp_path)
    assert config_mod.resolve_config_path(None) == Path("config.json")
    assert metadata_check.profiles_path() == Path("requirements_profiles.json")


def test_frozen_config_found_one_level_above_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dist = tmp_path / "dist"
    exe = dist / "curation-app-lite" / "curation-app-lite.exe"
    exe.parent.mkdir(parents=True)
    (dist / "config.json").write_text('{"dataverse": {"api_token": "tok-123"}}', encoding="utf-8")
    monkeypatch.chdir(exe.parent)
    _freeze(monkeypatch, exe)
    assert config_mod.resolve_config_path(None) == dist / "config.json"
    assert config_mod.Config.load(None).dataverse.api_token == "tok-123"


def test_frozen_fresh_save_lands_above_build_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dist = tmp_path / "dist"
    exe = dist / "curation-app-lite" / "curation-app-lite.exe"
    exe.parent.mkdir(parents=True)
    monkeypatch.chdir(exe.parent)
    _freeze(monkeypatch, exe)
    assert config_mod.resolve_config_path(None) == dist / "config.json"
    assert metadata_check.profiles_path() == dist / "requirements_profiles.json"


def test_frozen_config_prefers_cwd_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cwd = tmp_path / "elsewhere"
    cwd.mkdir()
    (cwd / "config.json").write_text("{}", encoding="utf-8")
    exe = tmp_path / "dist" / "curation-app-lite" / "curation-app-lite.exe"
    exe.parent.mkdir(parents=True)
    monkeypatch.chdir(cwd)
    _freeze(monkeypatch, exe)
    # Legacy semantics: a CWD config keeps resolving as the relative
    # default (candidate1), never hijacked by the exe-adjacent fallbacks.
    resolved = config_mod.resolve_config_path(None)
    assert resolved == Path("config.json")
    assert resolved.exists()


def test_frozen_profiles_prefer_file_beside_exe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exe_dir = tmp_path / "dist" / "curation-app-full"
    exe_dir.mkdir(parents=True)
    (exe_dir / "requirements_profiles.json").write_text("{}", encoding="utf-8")
    _freeze(monkeypatch, exe_dir / "curation-app-full.exe")
    assert metadata_check.profiles_path() == exe_dir / "requirements_profiles.json"


def test_explicit_config_path_is_honoured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _freeze(monkeypatch, tmp_path / "somewhere" / "app.exe")
    explicit = tmp_path / "my-config.json"
    assert config_mod.resolve_config_path(explicit) == explicit
