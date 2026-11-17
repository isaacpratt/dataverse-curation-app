"""Frozen-mode user data: config.json and the requirement profiles.

An installed build (Velopack unpacks each version into `<root>/current/`,
replaces that folder on every update, and deletes the whole install folder
on uninstall) must keep the API token and the curator's rulesets in
per-user app data. Portable builds keep the beside-the-exe search, and dev
runs keep the working directory.
"""

import os
import sys
import types
from pathlib import Path

import pytest

import config as config_mod
import metadata_check


def _freeze(monkeypatch: pytest.MonkeyPatch, exe: Path) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))


def _installed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Lay out a Velopack install: <root>/current/<exe> with Update.exe beside it."""
    root = tmp_path / "DataverseDocent"
    exe_dir = root / "current"
    exe_dir.mkdir(parents=True)
    (root / "Update.exe").write_bytes(b"")
    exe = exe_dir / "DataverseDocent.exe"
    exe.write_bytes(b"")
    _freeze(monkeypatch, exe)
    return exe


def _no_velopack(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make sure a real (or faked) velopack runtime cannot answer for us."""
    monkeypatch.setitem(sys.modules, "velopack", None)


@pytest.fixture
def appdata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point per-user app data at tmp_path, whatever the host platform is."""
    roaming = tmp_path / "roaming"
    monkeypatch.setenv("APPDATA", str(roaming))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return roaming / config_mod.APP_DIR_NAME


def test_source_run_keeps_cwd_semantics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.chdir(tmp_path)
    assert config_mod.resolve_config_path(None) == Path("config.json")
    assert metadata_check.profiles_path() == Path("requirements_profiles.json")


def test_installed_build_uses_per_user_app_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, appdata: Path
) -> None:
    _installed(monkeypatch, tmp_path)
    _no_velopack(monkeypatch)
    assert config_mod.is_installed_build() is True
    assert config_mod.resolve_config_path(None) == appdata / "config.json"
    assert metadata_check.profiles_path() == appdata / "requirements_profiles.json"


def test_installed_build_migrates_a_beside_the_exe_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, appdata: Path
) -> None:
    exe = _installed(monkeypatch, tmp_path)
    _no_velopack(monkeypatch)
    # _legacy_candidates lists the cwd first; isolate from a dev checkout
    # that keeps a real config.json at the repo root.
    monkeypatch.chdir(tmp_path)
    legacy = exe.parent / "config.json"
    legacy.write_text('{"dataverse": {"api_token": "tok-123"}}', encoding="utf-8")

    resolved = config_mod.resolve_config_path(None)

    assert resolved == appdata / "config.json"
    assert resolved.exists()
    assert config_mod.Config.load(None).dataverse.api_token == "tok-123"
    # Copy, never move: an older portable run keeps working.
    assert legacy.exists()


def test_installed_build_keeps_an_existing_per_user_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, appdata: Path
) -> None:
    _installed(monkeypatch, tmp_path)
    _no_velopack(monkeypatch)
    appdata.mkdir(parents=True)
    (appdata / "config.json").write_text('{"dataverse": {"api_token": "keep"}}', encoding="utf-8")
    (tmp_path / "DataverseDocent" / "current" / "config.json").write_text(
        '{"dataverse": {"api_token": "stale"}}', encoding="utf-8"
    )

    assert config_mod.Config.load(None).dataverse.api_token == "keep"


def test_current_folder_alone_marks_an_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, appdata: Path
) -> None:
    # No Update.exe (older layout, or a partial listing) - the folder name
    # still says the folder gets replaced on update.
    exe_dir = tmp_path / "current"
    exe_dir.mkdir(parents=True)
    exe = exe_dir / "DataverseDocent.exe"
    exe.write_bytes(b"")
    _freeze(monkeypatch, exe)
    _no_velopack(monkeypatch)

    assert config_mod.is_installed_build() is True
    assert config_mod.resolve_config_path(None) == appdata / "config.json"


def test_the_portable_zip_is_not_an_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The portable package has exactly the `<root>/current/` + Update.exe shape
    # of an install; it marks its root `.portable` instead of registering an
    # uninstall entry, and that marker is the only thing telling them apart.
    root = tmp_path / "DataverseDocent-win-Portable"
    exe_dir = root / "current"
    exe_dir.mkdir(parents=True)
    (root / "Update.exe").write_bytes(b"")
    (root / ".portable").write_bytes(b"")
    exe = exe_dir / "DataverseDocent.exe"
    exe.write_bytes(b"")
    _freeze(monkeypatch, exe)
    _no_velopack(monkeypatch)
    monkeypatch.chdir(exe_dir)

    assert config_mod.is_installed_build() is False
    # Beside the exe, then one level up ("above the folder the installer
    # replaces"), never per-user app data.
    assert config_mod.resolve_config_path(None) == root / "config.json"


def test_velopack_portable_answer_wins_over_the_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, appdata: Path
) -> None:
    exe = _installed(monkeypatch, tmp_path)
    module = types.ModuleType("velopack")

    class _Source:
        def __init__(self, *args, **kwargs):
            pass

    class _Manager:
        def __init__(self, source=None):
            self._source = source

        def get_is_portable(self) -> bool:
            return True

    module.GithubSource = _Source  # type: ignore[attr-defined]
    module.UpdateManager = _Manager  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "velopack", module)

    assert config_mod.is_installed_build() is False
    # Portable semantics: the file beside the exe wins.
    # _legacy_candidates lists the cwd first; isolate from a dev checkout
    # that keeps a real config.json at the repo root.
    monkeypatch.chdir(tmp_path)
    beside = exe.parent / "config.json"
    beside.write_text("{}", encoding="utf-8")
    assert config_mod.resolve_config_path(None) == beside


def test_portable_build_keeps_the_beside_the_exe_search(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dist = tmp_path / "dist"
    exe = dist / "DataverseDocent" / "DataverseDocent.exe"
    exe.parent.mkdir(parents=True)
    (dist / "config.json").write_text(
        '{"dataverse": {"api_token": "tok-123"}}', encoding="utf-8"
    )
    monkeypatch.chdir(exe.parent)
    _freeze(monkeypatch, exe)
    _no_velopack(monkeypatch)

    assert config_mod.is_installed_build() is False
    assert config_mod.resolve_config_path(None) == dist / "config.json"
    assert config_mod.Config.load(None).dataverse.api_token == "tok-123"


def test_portable_fresh_save_lands_above_build_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dist = tmp_path / "dist"
    exe = dist / "DataverseDocent" / "DataverseDocent.exe"
    exe.parent.mkdir(parents=True)
    monkeypatch.chdir(exe.parent)
    _freeze(monkeypatch, exe)
    _no_velopack(monkeypatch)

    assert config_mod.resolve_config_path(None) == dist / "config.json"
    assert metadata_check.profiles_path() == dist / "requirements_profiles.json"


def test_portable_config_prefers_cwd_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cwd = tmp_path / "elsewhere"
    cwd.mkdir()
    (cwd / "config.json").write_text("{}", encoding="utf-8")
    exe = tmp_path / "dist" / "DataverseDocent" / "DataverseDocent.exe"
    exe.parent.mkdir(parents=True)
    monkeypatch.chdir(cwd)
    _freeze(monkeypatch, exe)
    _no_velopack(monkeypatch)

    resolved = config_mod.resolve_config_path(None)
    assert resolved == Path("config.json")
    assert resolved.exists()


def test_portable_profiles_prefer_file_beside_exe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exe_dir = tmp_path / "dist" / "DataverseDocent"
    exe_dir.mkdir(parents=True)
    (exe_dir / "requirements_profiles.json").write_text("{}", encoding="utf-8")
    _freeze(monkeypatch, exe_dir / "DataverseDocent.exe")
    _no_velopack(monkeypatch)

    assert metadata_check.profiles_path() == exe_dir / "requirements_profiles.json"


def test_explicit_config_path_is_honoured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _installed(monkeypatch, tmp_path)
    explicit = tmp_path / "my-config.json"
    assert config_mod.resolve_config_path(explicit) == explicit


def test_default_literal_is_still_the_policy_not_a_location(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, appdata: Path
) -> None:
    # argparse supplies the bare default; the GUI therefore hands over
    # Path("config.json") on every launch and must still land in app data.
    _installed(monkeypatch, tmp_path)
    _no_velopack(monkeypatch)
    assert config_mod.resolve_config_path(Path("config.json")) == appdata / "config.json"


@pytest.mark.skipif(os.name != "nt", reason="Windows APPDATA convention")
def test_user_data_dir_prefers_appdata_on_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    assert config_mod.user_data_dir() == tmp_path / "roaming" / config_mod.APP_DIR_NAME


def test_rulesets_path_follows_the_profiles_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, appdata: Path
) -> None:
    import review_rules

    _installed(monkeypatch, tmp_path)
    _no_velopack(monkeypatch)
    assert review_rules.rulesets_path() == appdata / "requirements_profiles.json"
