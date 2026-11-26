---
page_type: how-to
tgdp_template: How-to
audience: developer
---

# Run the gates

Run the local checks that CI enforces before you open a pull request. [The project layout reference](../reference/project-layout.md) explains what each suite covers.

## Prerequisites

- Python 3.11+ and [uv](https://docs.astral.sh/uv/) on PATH.
- `QT_QPA_PLATFORM=offscreen` set when you run the UI probes on a headless machine.

## Steps

1. Create or update the environment from the committed lockfile:

   ```powershell
   uv sync --group dev
   ```

2. Run the consolidated gate (lint, format check, typecheck, architecture contracts, tests):

   ```powershell
   uv run poe check
   ```

3. Run the pre-commit hooks (whitespace and EOF fixers, JSON/TOML/YAML validation, secret detection, codespell, pymarkdown, `uv lock --check`, ruff, actionlint, and the `config.json` guard):

   ```powershell
   uv run poe hooks
   ```

   This task runs `pre-commit run --all-files`. Because `core.hooksPath` is beads-managed, the hooks are not installed automatically; run this task yourself or rely on CI.

4. Type-check the application with mypy. All application modules are checked under full `--strict`; only the four test packages relax three "you must annotate" rules:

   ```powershell
   uv run poe typecheck
   ```

5. Check the architecture contracts with import-linter:

   ```powershell
   uv run poe contracts
   ```

6. Run the offscreen UI probes:

   ```powershell
   uv run poe probes
   ```

7. Run the tests:

   ```powershell
   uv run poe test
   ```

8. Run the full docs gate (Markdown lint, offline internal link check, and strict site build):

   ```powershell
   uv run poe docs-check
   ```

   This chains `poe docs-lint`, `poe docs-links`, and `poe docs`. The last of these runs `zensical build --strict`, so a broken relative link or anchor fails the build.

## Poe task quick lookup

| Task | Command it runs | Purpose |
| --- | --- | --- |
| `poe check` | `lint`, `format-check`, `typecheck`, `contracts`, `test` | Consolidated gate |
| `poe hooks` | `pre-commit run --all-files` | Commit hygiene, including pymarkdown and codespell |
| `poe typecheck` | `mypy` | Strict type check |
| `poe contracts` | `lint-imports` | Dependency direction |
| `poe probes` | `python tools/probes/run_all.py` | Offscreen UI probes |
| `poe test` | `pytest -q` | Test suite |
| `poe docs-check` | `docs-lint`, `docs-links`, `docs` | Full docs gate |
| `poe docs-lint` | `pymarkdown --strict-config --config .pymarkdown.json scan -r docs CONTRIBUTING.md README.md` | Markdown lint |
| `poe docs-links` | `python tools/docs/check_doc_links.py` | Offline internal link check |
| `poe docs` | `zensical build --strict` | Strict docs build |
| `poe cover` | `pytest -q --cov=engine --cov-report=term-missing` | Engine coverage against the configured floor |
| `poe cover-ui` | `pytest -q -n 4 ui/tests/ --cov=ui --cov-report=term-missing --cov-fail-under=71` | UI-only coverage against its own ratcheting floor |
| `poe samples` | `pytest -q -m samples` | Opt-in parity tests against external sample data |
