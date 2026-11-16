# ADR 0001 — uv, poe and pre-commit are the toolchain

- **Status:** Accepted
- **Date:** 2026-11-13 (ratified 2026-11-16)

## Context

The repository arrived with `requirements.txt`, `Makefile`, a `pip install`
workflow and a partially wired `pre-commit` configuration. Three consequences
followed: contributors installed different dependency sets, the CI and a
developer's machine could disagree, and the task runner only worked on
Git Bash (`make` targets with shell-specific syntax). The 2026-11-13
code-cleaning audit also found that the lockfile was not enforced anywhere,
so a stale `requirements.txt` could pass CI.

The project is a Windows-first desktop application with heavy optional
scientific dependencies (SPSS/SAS/Stata readers, netCDF, HDF5, SciPy). The
toolchain therefore has to make a *locked* environment cheap to reproduce and
must run identically from `cmd.exe`, PowerShell and bash.

## Decision

- **uv is the package manager and the lockfile is the source of truth.**
  `uv.lock` (with hashes) is committed and enforced by `uv lock --check` in
  both pre-commit and CI; `uv sync --locked --group dev` is the install
  command. `requirements.txt` is gone — `uv export --format requirements-txt`
  is the escape hatch for a pip-only environment, not a tracked file.
- **poe (poethepoet) is the task runner.** Every developer command is a
  named poe task (`poe check`, `poe fmt`, `poe format-check`, `poe typecheck`,
  `poe test`, `poe audit`, `poe hooks`, `poe probes`, `poe build*`, `poe smoke`,
  `poe license-report`, `poe sbom`, `poe docs-links`). Tasks use the `cmd`
  executor so the same definition runs on every shell.
- **pre-commit is the local gate, CI is the authority.** The hook set is
  check-only (whitespace/EOF fixers aside): JSON/TOML/YAML validation,
  large-file/case-conflict/Windows-illegal-name checks, private-key detection,
  codespell (Canadian English), a `forbid-config-json` guard for the token
  file, `uv lock --check`, ruff, ruff-format, and actionlint.
- **CI pins every action by commit SHA** and Dependabot proposes the
  updates (`uv` + `github-actions` weekly, `pre-commit` monthly).

## Consequences

- A new contributor needs `uv` and nothing else: `uv sync` then `uv run poe
  check` reproduces the environment exactly.
- `core.hooksPath` is beads-managed, so hooks are not auto-installed; run
  `uv run poe hooks` (or rely on CI).
- Adding a dependency means editing `pyproject.toml` and running `uv lock`;
  CI fails on an out-of-date lockfile.
- The cost is that the toolchain itself has a learning curve (uv/poe/pre-commit
  are three tools). The payoff is that "works on my machine" stopped being a
  category of bug.

## Links

- Beads: `dv-hcg` (audit), `dv-hcg.4` (CI hardening), `dv-hcg.6` (poe tasks),
  `dv-hcg.8` (config.json guard).
- `docs/html/development.html` — setup, quality gates, adding a dependency.
- `pyproject.toml` — the tool configuration itself.
