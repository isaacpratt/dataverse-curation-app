# Architecture Decision Records

Short, dated records of the decisions that shape this repository — the ones
that would otherwise be re-litigated every time someone asks "why is it like
this?".

| ADR | Decision | Status | Date |
|---|---|---|---|
| [0001](0001-uv-poe-precommit.md) | uv + poe + pre-commit are the toolchain; the lockfile is enforced | Accepted | 2026-11-13 |
| [0002](0002-no-src-layout-flat-pyinstaller-entry.md) | No `src/` layout; flat root, `main.py` as the entry point | Accepted | 2026-09-15 |
| [0003](0003-ruff-format-phased-adoption.md) | Ruff format adopted in phases, gated on the whole tree | Accepted | 2026-11-13 |
| [0004](0004-no-pypi-packaging-app-not-library.md) | The app is not a PyPI package (`package = false`) | Accepted | 2026-11-13 |
| [0005](0005-api-token-os-credential-store.md) | The API token lives in the OS credential store | Accepted | 2026-11-13 |
| [0006](0006-curation-core-package.md) | The application core lives in `curation/`; `main.py` stays the entry point | Accepted | 2026-11-16 |
| [0007](0007-ui-typing-gate.md) | The UI layer joins the mypy gate under a documented relaxation of `--strict` | Superseded by ADR-0008 | 2026-11-17 |
| [0008](0008-strict-app-relaxed-tests.md) | All application code is strict; only tests relax annotation requirements | Accepted | 2026-11-20 |
| [0009](0009-zensical-docs.md) | Documentation is built from Markdown by Zensical and published on GitHub Pages | Accepted; IA superseded by dv-uq6 (2026-11-23) | 2026-11-20 |

## Format

Each ADR is one page with the same headings:

- **Status** — `Accepted`, `Superseded by ADR-XXXX`, or `Proposed`.
- **Date** — when the decision was made.
- **Context** — the forces and constraints that produced it.
- **Decision** — what was decided, in the active voice.
- **Consequences** — what this costs and what it buys.
- **Links** — the beads, files and documentation that carry the detail.

## Writing one

1. Copy the structure of an existing ADR.
2. Name the decision in the title as a statement (`No src/ layout; flat root
   with main.py as the entry point`), not as a topic.
3. Link the beads that carry the work — an ADR is the *why*, the bead is the
   *what*.
4. If a decision is reversed, write a new ADR and mark the old one
   `Superseded by ADR-XXXX`; do not edit history.

The decision log in `docs/explanation/architecture.md` holds the UI-level decisions;
these ADRs hold the repository-level ones (toolchain, layout, packaging,
security).
