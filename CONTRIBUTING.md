# Contributing to Dataverse Docent

Thanks for helping improve Dataverse Docent. This guide covers how to report problems, propose changes, set up a development environment, and get your work through the gates. For the rules that govern the prose you write, read [docs/style-guide.md](docs/style-guide.md); the same guide is published on the [documentation site](https://isaacpratt.github.io/dataverse-curation-app/style-guide/) once Pages has deployed it.

## Report a bug or request a feature

1. Search the repository issues and the beads queue (`bd list`) before opening anything new. Security problems do not belong in a public issue; follow [SECURITY.md](SECURITY.md) instead.
2. Open an issue with a short title, the version you are running, your operating system, and the exact steps to reproduce. For a bug, include the expected and actual behaviour and any report or log output, with tokens and personal data removed.
3. Attach the smallest fixture or staged directory that reproduces the problem when you can.

## Propose a change

1. Discuss a substantial change in an issue first so the approach is agreed before code is written.
2. Claim the issue in beads (`bd update <id> --claim`), or state in the issue that you are working on it.
3. Keep one change per pull request. Open a draft early when you want feedback on direction.

## Set up the development environment

1. Install Python 3.11+ and [uv](https://docs.astral.sh/uv/).
2. Clone the repository and create the locked environment:

   ```powershell
   uv sync --group dev
   ```

3. Copy the configuration template and set your own instance. Never commit `config.json`:

   ```powershell
   Copy-Item config.example.json config.json
   ```

4. Confirm the setup by launching the app:

   ```powershell
   uv run python main.py
   ```

## Run the checks

Before you open a pull request, run the gates in [Run the gates](docs/how-to/run-the-gates.md) and confirm they pass:

```powershell
uv run poe check       # lint, format-check, typecheck, contracts, tests
uv run poe hooks       # pre-commit
uv run poe probes      # offscreen UI probes
uv run poe docs-check  # Markdown lint, links, strict site build
```

`poe check` already sequences typecheck, contracts and tests; run those individually only when you are debugging one of them.

CI runs the same gate on every pull request. A docs-only change still needs the strict docs build.

## Write documentation

- Follow [docs/style-guide.md](docs/style-guide.md) (also published on the documentation site once Pages has deployed it).
- Put one idea in one page and keep each page in one Diátaxis quadrant.
- Use relative links between pages in `docs/`, fenced code blocks with a language, and commands copied from `pyproject.toml`.
- Add a new page to the explicit `nav` in `zensical.toml`.
- Validate with `uv run poe docs-check` (Markdown lint, offline links, and strict build) and `uv run pre-commit run --all-files` (pymarkdown and codespell).

## Commit and pull request conventions

1. Write a short imperative commit subject, for example "Add scope declaration to new check".
2. Keep unrelated changes out of the same commit. Do not stage `config.json`, build output, or generated caches.
3. Reference the bead or issue in the pull request description and state what you ran to verify the change.
4. Expect CI to run pre-commit, lint, type checks, contracts, the test suite with coverage, the headless smoke, UI probes, a docs build, and an OSV dependency audit. Resolve failures before requesting review.

## Issue tracking with bd

The plan and all work items live in beads, a local Dolt-backed tracker:

```powershell
bd ready             # unblocked work
bd list              # the full queue
bd show <id>         # one item
bd update <id> --claim
bd close <id> --reason "Done"
```

Create new items for work you discover, link them with `discovered-from` dependencies, and avoid duplicating an item that is already open or closed. Do not use markdown task lists as a second tracking system.

## Security

Do not open a public issue for a vulnerability. Follow [SECURITY.md](SECURITY.md).
