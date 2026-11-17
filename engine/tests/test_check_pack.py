"""The packed release is checked, not assumed: `tools/check_pack.py`.

`poe pack` and CI both call that script, so these tests define what "packed"
means without a 229 MB PyInstaller build: a fake release directory with the
real Velopack file names and a real `.nuspec` inside a real `.nupkg`.
"""

from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import check_pack, pack_app  # noqa: E402

SCRIPT = ROOT / "tools" / "check_pack.py"
VERSION = "0.2.0"
NEW_ENOUGH = 1_100_000  # a Setup.exe smaller than a megabyte is reported as truncated


def _nuspec(
    *,
    pack_id: str = check_pack.PACK_ID,
    version: str = VERSION,
    main_exe: str = check_pack.MAIN_EXE,
    channel: str = check_pack.CHANNEL,
    rid: str = check_pack.RUNTIME,
) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<package xmlns="http://schemas.microsoft.com/packaging/2010/07/nuspec.xsd">'
        "<metadata>"
        f"<id>{pack_id}</id><title>{check_pack.PACK_TITLE}</title>"
        f"<version>{version}</version><channel>{channel}</channel>"
        f"<mainExe>{main_exe}</mainExe><os>win</os><rid>{rid}</rid>"
        "</metadata></package>"
    )


def make_release(
    directory: Path,
    *,
    version: str = VERSION,
    nuspec: str | None = None,
    include_main_exe: bool = True,
    feed_version: str | None = None,
    releases_entry: str | None = None,
    setup_bytes: int = NEW_ENOUGH,
    channel: str = check_pack.CHANNEL,
) -> Path:
    """Write the five files `vpk pack` produces, shaped like the real ones."""
    directory.mkdir(parents=True, exist_ok=True)
    nupkg = directory / check_pack.nupkg_name(version, channel=channel)
    with zipfile.ZipFile(nupkg, "w") as zf:
        zf.writestr(
            f"{check_pack.PACK_ID}.nuspec", nuspec or _nuspec(version=version, channel=channel)
        )
        if include_main_exe:
            # vpk puts app content under lib/app/ rather than the archive root.
            zf.writestr(f"lib/app/{check_pack.MAIN_EXE}", b"MZ" + b"\0" * 64)
        zf.writestr("lib/app/_internal/python313.dll", b"\0" * 32)

    with open(directory / check_pack.setup_exe_name(channel=channel), "wb") as handle:
        handle.truncate(setup_bytes)
    with open(directory / check_pack.portable_name(channel=channel), "wb") as handle:
        handle.truncate(64)

    asset = {
        "PackageId": check_pack.PACK_ID,
        "Version": feed_version or version,
        "Type": "Full",
        "FileName": nupkg.name,
        "SHA1": "AB" * 20,
        "SHA256": "CD" * 32,
        "Size": nupkg.stat().st_size,
    }
    (directory / check_pack.feed_name(channel=channel)).write_text(
        json.dumps({"Assets": [asset]}), encoding="utf-8"
    )
    (directory / check_pack.releases_index_name(channel)).write_text(
        releases_entry or f"{asset['SHA1']} {nupkg.name} {asset['Size']}\n",
        encoding="utf-8",
    )
    return directory


def test_a_complete_release_passes(tmp_path: Path) -> None:
    release = make_release(tmp_path / "releases")
    assert check_pack.check_release(release, version=VERSION) == []


def test_a_missing_directory_says_how_to_build_one(tmp_path: Path) -> None:
    problems = check_pack.check_release(tmp_path / "nope", version=VERSION)
    assert len(problems) == 1
    assert "poe pack" in problems[0]


def test_a_missing_or_stubbed_setup_exe_is_reported(tmp_path: Path) -> None:
    release = make_release(tmp_path / "releases")
    (release / check_pack.setup_exe_name()).unlink()
    problems = check_pack.check_release(release, version=VERSION)
    assert any(check_pack.setup_exe_name() in p for p in problems)

    stubbed = make_release(tmp_path / "stubbed", setup_bytes=2048)
    assert any("truncated" in p for p in check_pack.check_release(stubbed, version=VERSION))


def test_the_package_version_must_match_the_expected_one(tmp_path: Path) -> None:
    release = make_release(tmp_path / "releases", version="0.1.0")
    problems = check_pack.check_release(release, version=VERSION)
    assert any("0.2.0" in p and "found: DataverseDocent-0.1.0-full.nupkg" in p for p in problems)


def test_nuspec_identity_must_match_the_fixed_choices(tmp_path: Path) -> None:
    release = make_release(
        tmp_path / "releases",
        nuspec=_nuspec(pack_id="OtherApp", main_exe="app.exe", rid="win-x86", channel="beta"),
    )
    joined = " | ".join(check_pack.check_release(release, version=VERSION))
    assert "nuspec id 'OtherApp'" in joined
    assert "nuspec mainExe 'app.exe'" in joined
    assert "nuspec rid 'win-x86'" in joined  # vpk's x86 default when --runtime is missing
    assert "nuspec channel 'beta'" in joined


def test_the_package_must_carry_the_main_executable(tmp_path: Path) -> None:
    release = make_release(tmp_path / "releases", include_main_exe=False)
    problems = check_pack.check_release(release, version=VERSION)
    assert any(check_pack.MAIN_EXE in p and "does not contain" in p for p in problems)


def test_the_feed_must_list_this_version(tmp_path: Path) -> None:
    release = make_release(tmp_path / "releases", feed_version="0.1.0")
    problems = check_pack.check_release(release, version=VERSION)
    assert any(check_pack.feed_name() in p and "no DataverseDocent 0.2.0 asset" in p for p in problems)


def test_the_legacy_index_must_mention_the_package(tmp_path: Path) -> None:
    release = make_release(tmp_path / "releases", releases_entry="AB DataverseDocent-0.1.0-full.nupkg 1\n")
    problems = check_pack.check_release(release, version=VERSION)
    assert any("RELEASES does not mention" in p for p in problems)


def test_a_corrupt_package_is_reported_not_raised(tmp_path: Path) -> None:
    release = make_release(tmp_path / "releases")
    (release / check_pack.nupkg_name(VERSION)).write_bytes(b"not a zip")
    problems = check_pack.check_release(release, version=VERSION)
    assert any("not a readable zip" in p for p in problems)


def test_cli_exit_codes(tmp_path: Path) -> None:
    good = make_release(tmp_path / "good")
    bad = make_release(tmp_path / "bad", feed_version="0.1.0")

    ok = subprocess.run(
        [sys.executable, str(SCRIPT), "--dir", str(good), "--version", VERSION],
        capture_output=True,
        text=True,
    )
    assert ok.returncode == 0, ok.stderr
    assert "release ok" in ok.stdout

    broken = subprocess.run(
        [sys.executable, str(SCRIPT), "--dir", str(bad), "--version", VERSION],
        capture_output=True,
        text=True,
    )
    assert broken.returncode == 1
    assert "not a shippable release" in broken.stderr

    absent = subprocess.run(
        [sys.executable, str(SCRIPT), "--dir", str(tmp_path / "absent")],
        capture_output=True,
        text=True,
    )
    assert absent.returncode == 2
    assert "poe pack" in absent.stderr


def test_rebuilding_a_version_replaces_only_that_version(tmp_path: Path) -> None:
    release = make_release(tmp_path / "releases", version="0.2.0")
    other = make_release(tmp_path / "releases", version="0.1.0")

    removed = pack_app.clear_version(release, "0.2.0")

    assert removed == ["DataverseDocent-0.2.0-full.nupkg"]
    assert not (release / "DataverseDocent-0.2.0-full.nupkg").exists()
    assert (other / "DataverseDocent-0.1.0-full.nupkg").exists()


def test_artifact_names_carry_the_channel(tmp_path: Path) -> None:
    assert check_pack.nupkg_name("0.9.9") == "DataverseDocent-0.9.9-full.nupkg"
    assert (
        check_pack.nupkg_name("0.9.9", channel="win-beta")
        == "DataverseDocent-0.9.9-win-beta-full.nupkg"
    )
    assert check_pack.releases_index_name("win-beta") == "RELEASES-win-beta"
    assert check_pack.releases_index_name() == "RELEASES"


def test_a_prerelease_channel_pack_verifies_against_that_channel(tmp_path: Path) -> None:
    release = make_release(tmp_path / "releases", channel="win-beta")

    assert check_pack.check_release(release, version=VERSION, channel="win-beta") == []
    # The default (stable) expectation must fail on the beta folder: the
    # artifacts carry the beta name and releases.win-beta.json.
    problems = check_pack.check_release(release, version=VERSION)
    assert any("missing DataverseDocent-win-Setup.exe" in p for p in problems)
    assert any("releases.win.json" in p for p in problems)

    feed = json.loads((release / "releases.win-beta.json").read_text(encoding="utf-8"))
    assert feed["Assets"][0]["FileName"] == "DataverseDocent-0.2.0-win-beta-full.nupkg"
    assert feed["Assets"][0]["PackageId"] == check_pack.PACK_ID


def test_a_wrong_main_exe_is_reported_not_raised(tmp_path: Path) -> None:
    release = make_release(tmp_path / "releases", channel="win-beta")
    problems = check_pack.check_release(release, version=VERSION, channel="win-beta", main_exe="Other.exe")
    assert any("nuspec mainExe" in p for p in problems)
