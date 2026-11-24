# ADR 0004 — The app is not published to PyPI; `package = false`

- **Status:** Accepted
- **Date:** 2026-11-13

## Context

The project metadata said `name = "dataverse-curation-app"`, `version =
"0.1.0"` and carried a setuptools build backend, which implied a
distributable Python package. It is not one: the deliverable is a PyInstaller
folder (or the installer built from it) that a curator runs as a desktop
program. The audit found that the packaging metadata was actively misleading —
a stale `License :: OSI Approved :: MIT License` classifier would only fail
when the metadata was actually built, which the `package = false` setting
suppressed.

The audit also asked for PEP 639 metadata (SPDX `license-expression` instead
of the legacy classifier), repository/docs/issues URLs and an explicit Python
floor.

## Decision

- **The project is an application, not a library.** `pyproject.toml` sets
  `[tool.uv] package = false`: `uv sync` installs the dependencies and the
  toolchain, and does not try to build or install the project itself.
- **No PyPI publication, no console-script entry point.** At the time, distribution was the PyInstaller artefact (then a `lite`/`full` pair) and, later, the installer produced from it. There is now one onedir build packaged as a Velopack release; the no-PyPI decision is unchanged.
- **Metadata is PEP 639-clean:** `license = "MIT"` (SPDX expression),
  `license-files = ["LICENSE"]`, repository/homepage/documentation/issues
  URLs, authors, and no duplicate licence classifier.
- **The Python floor is 3.11** (`.python-version`, CI matrix, `requires-python`),
  matching the `datetime.UTC` alias and the `tomllib` usage.
- **The version lives in two places that must agree** — `pyproject.toml` and
  `engine.__init__.__version__` — and a test (`engine/tests/test_version.py`)
  fails if they drift. Bumping means changing both in one commit.

## Consequences

- `uv sync` is fast and never fails on a packaging problem; there is no
  wheel to publish or maintain.
- Version bumps touch two files and are covered by a test, so the About pane
  and the release workflow cannot disagree about the version.
- Anyone who *wants* the engine as a library must vendor it; that is
  deliberate — the engine exists to serve this app.
- The release workflow (`dv-hcg.36`) builds artefacts from the tag, not from
  a package index.

## Links

- Beads: `dv-hcg` (audit), `dv-hcg.1` (uv/PEP 639 metadata), `dv-hcg.37`
  (single-sourced version), `dv-hcg.36` (release workflow).
- `pyproject.toml` — project metadata.
- `engine/tests/test_version.py` — the version-agreement test.
