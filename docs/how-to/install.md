---
page_type: how-to
tgdp_template: Installation guide
audience: all
---

# Install Dataverse Docent

Dataverse Docent is a Windows desktop app for curating datasets in a [Dataverse instance](../reference/glossary.md). Choose one installation method below, then [configure your instance](configure-instance.md).

## Before you begin

- Windows is recommended. A released build needs no Python installation.
- To run from source you need Python 3.11+ and [uv](https://docs.astral.sh/uv/), a Python package and environment manager.
- Get the release assets from [GitHub Releases](https://github.com/isaacpratt/dataverse-curation-app/releases).

## Install with Setup.exe

1. Download `DataverseDocent-win-Setup.exe` and `SHA256SUMS.txt` from the latest release.

2. Verify the download before running it. Open PowerShell in the folder that holds the installer and run:

   ```powershell
   Get-FileHash -Algorithm SHA256 .\DataverseDocent-win-Setup.exe
   ```

   Compare the hash with the line for `DataverseDocent-win-Setup.exe` in `SHA256SUMS.txt`. Do not run the installer if they differ.

3. Run `DataverseDocent-win-Setup.exe`. The install is per-user: it does not ask for administrator rights and adds Start menu and desktop shortcuts. Remove it later through **Apps & Features**.

4. On first launch, Windows SmartScreen may show **Windows protected your PC**. The current build is unsigned, so choose **More info → Run anyway** only after you have verified the checksum. Later releases are signed by SignPath Foundation and show the publisher name instead.

5. Open the app and follow [configure your instance](configure-instance.md).

## Install the portable build

1. Download `DataverseDocent-win-Portable.zip` and `SHA256SUMS.txt` from the latest release.

2. Verify the archive. In PowerShell, run `Get-FileHash -Algorithm SHA256 .\DataverseDocent-win-Portable.zip` and compare the result with `SHA256SUMS.txt`.

3. Unzip the archive and run `DataverseDocent.exe` from the extracted folder. Nothing is installed; the app keeps its configuration beside the executable.

## Run from source

1. Clone the repository and open PowerShell in its root.

2. Create the environment and install the locked dependencies:

   ```powershell
   uv sync
   ```

3. Launch the app:

   ```powershell
   uv run python main.py
   ```

4. Open **Settings** (or press `Ctrl+,`) and [configure your instance](configure-instance.md).

## Apply updates

1. Open the **About** page with `?` in the top nav.

2. The app checks the release feed once a day. When an update is published, accept the offer to restart and apply it. You do not download an installer again.

3. If you installed the portable build, download the new release and use its extracted folder instead.
