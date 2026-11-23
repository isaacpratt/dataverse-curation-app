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

This site follows [Diátaxis](https://diataxis.fr): each page is one of four
kinds. Pick the door that matches what you need right now.

## Find your way

| I want to… | Go to | What you get |
| --- | --- | --- |
| Learn by doing — complete one review from start to finish | [Tutorial: your first review](tutorials/first-review.md) | A guided first experience that always works |
| Get something done — install, configure, download, respond, release | [How-to guides](how-to/install.md) | Task-focused steps for a competent user |
| Look something up — a check ID, a config key, an endpoint, a CLI flag | [Reference](reference/checks.md) | Dry, complete, lookup-only facts |
| Understand why — the architecture, the discovery design, the port rationale | [Explanation](explanation/architecture.md) | Background, context and trade-offs |

Other doors: [Troubleshooting](troubleshooting.md) when something goes wrong,
[Release notes](release-notes.md) for what shipped, and the
[documentation style guide](style-guide.md) for contributors.

## Project status

The app is feature-complete for its documented scope: a curation queue,
approval-gated downloads and verification, a registry of format and inventory
checks, metadata completeness rulesets, dispositions, response drafts,
curation records and a headless mode. One onedir build is packaged as a
Velopack installer and published on
[GitHub Releases](https://github.com/isaacpratt/dataverse-curation-app/releases).
The remaining plan is queued in [beads](https://github.com/gastownhall/beads)
(`bd ready` / `bd list`); see [Design records](explanation/design-records/index.md)
for where decisions live.

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

## How the docs are maintained

Documentation is code: it lives in this repository's `docs/` tree as
Markdown, is reviewed in the same pull requests as the app, and is built and
checked automatically. Every page declares its quadrant and the
[The Good Docs Project](https://thegooddocsproject.dev) template it follows in
front matter. CI enforces a strict Zensical build, a Markdown lint, offline
internal-link checking and doc-to-code consistency tests. External links are
checked on a schedule rather than on every pull request, so a third-party
outage never blocks a docs change. Contributors start with the
[style guide](style-guide.md) and [CONTRIBUTING.md](https://github.com/isaacpratt/dataverse-curation-app/blob/master/CONTRIBUTING.md).
