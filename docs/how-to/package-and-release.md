---
page_type: how-to
tgdp_template: How-to
audience: developer
---

# Package and release

Build the Windows artefacts, verify them locally, then publish from CI. For the authoritative list of published versions, see [the release notes](../release-notes.md).

## Prerequisites

- A green CI run on `master`.
- Python 3.11+, uv, and the committed lockfile.
- The .NET 10 SDK and the `vpk` tool, installed once per machine:

  ```powershell
  dotnet tool install -g vpk
  ```

- The release version set in `engine/__init__.py` **before** building: `poe pack` reads that literal, so artefacts built before the bump carry the old version.

## Steps

1. Build the onedir app folder:

   ```powershell
   uv run poe build
   ```

   This writes `dist/DataverseDocent/DataverseDocent.exe` and copies `config.example.json` beside it. PyInstaller flags live in `tools/build/build_app.py`.

2. Pack the folder into a Velopack release:

   ```powershell
   uv run poe pack
   ```

   This writes `dist/releases/`: the Setup executable, the portable zip, the `.nupkg`, and the update feed.

3. Verify the release directory without rebuilding:

   ```powershell
   uv run poe check-pack
   ```

4. Smoke-test the frozen executable:

   ```powershell
   uv run poe smoke
   ```

   Set `DOCENT_SMOKE_EXE` to inspect a different executable.

5. Confirm the release version. `__version__` in `engine/__init__.py` (for example `"0.2.0"`) was set before step 1 and committed; the wheel metadata, About pane, and updater read this literal, and the release job refuses a tag that disagrees with it. Locally packed artefacts are for verification only — CI rebuilds from the tagged source.

6. Release by tag push:

   ```powershell
   git tag v0.2.0
   git push origin v0.2.0
   ```

   The workflow runs the full gate, checks the tag against `engine.__version__`, builds, packs, and publishes. It attaches the portable zip and `SHA256SUMS.txt`.

7. Choose the channel with the tag. A plain `v0.2.0` publishes the stable `win` channel. A prerelease tag such as `v0.2.0-rc.1` or `v0.2.0-beta.1` packs the `win-beta` channel and publishes a pre-release; its assets and feed are named separately so prereleases never reach the stable updater.

8. Or dispatch the release instead: in GitHub, open Actions → Release → Run workflow and supply the version (for example `0.2.0`). It reuses an existing tag when present, so a failed release can be re-run without creating a second tag.

9. Yank a bad release by deleting its GitHub release (and, when appropriate, its tag). Installed copies stop seeing that version as an update once the feed regenerates; users reinstall the previous Setup executable from the release page. An aborted publish leaves a draft release, never a half-published one.
