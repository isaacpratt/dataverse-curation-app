---
page_type: home
tgdp_template: Home
audience: all
---

# Dataverse Docent

A desktop curation assistant for Alliance Dataverse. It pulls datasets
submitted for review, gates downloads behind curator approval, runs automated
format checks on the files, checks metadata completeness against a
configurable ruleset, and turns the findings into an exportable curation
report and a response draft.

## Find your way

| I want to… | Go to | What you get |
| --- | --- | --- |
| Learn by doing — complete one review from start to finish | [Tutorial: your first review](tutorials/first-review.md) | A guided first experience |
| Get something done — install, configure, download, respond, run checks headlessly | [How-to guides](how-to/install.md) | Task-focused steps |
| Look something up — a check ID, a config key, an endpoint, a CLI flag | [Reference](reference/checks.md) | Factual, lookup-only details |
| Fix a problem | [Troubleshooting](troubleshooting.md) | Symptoms, causes and remedies |
| See what changed between versions | [Release notes](release-notes.md) | A summary of shipped changes |

## Install at a glance

```powershell
# From a release (Windows): download DataverseDocent-win-Setup.exe and SHA256SUMS.txt
Get-FileHash -Algorithm SHA256 .\DataverseDocent-win-Setup.exe
# Or from source (Python 3.11+ and uv required):
uv sync
uv run python main.py
```

The released build is unsigned, so Windows SmartScreen warns on first run;
[verify the checksum](how-to/install.md), then choose **More info → Run anyway**.
Full instructions are in the [installation guide](how-to/install.md).
