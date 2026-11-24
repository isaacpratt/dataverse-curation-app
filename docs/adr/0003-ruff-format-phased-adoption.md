# ADR 0003 — Ruff format adopted in phases, over the whole tree

- **Status:** Accepted
- **Date:** 2026-11-13 (decision), 2026-11-16 (phases 1 and 2 landed)

## Context

The repository carried an inconsistent mix of hand-formatting: some modules
were black-shaped, others were not, and a pre-commit hook only checked a
handful of files. The audit found that formatting drift was the single
largest source of "why is this diff 400 lines" noise, and that no gate
guaranteed the formatter's output would survive a commit.

A whole-tree reformat in one commit is unreviewable: the diff mixes
mechanical change with real change, and reviewers stop reading.

## Decision

- **Ruff's formatter is the canonical formatter** (replacing ad-hoc
  black/isort habits). Line length 100, target Python 3.11.
- **Adoption is phased, one area per commit:**
  1. phase 1 — `engine/`, root modules, `tools/`;
  2. phase 2 — `ui/`;
  3. phase 3 — the gate covers the **whole tree** (`ruff format --check .`),
     so the phases are a review strategy, not a permanent split.
- **`ruff format` also formats fenced Python inside Markdown**, so the
  documentation examples stay in the same shape as the code.
- The lint rule set is extended alongside the formatter (`N`, `RUF`, `SIM`,
  `PT`, `C90` complexity, `TID` import hygiene). Findings were triaged
  explicitly rather than silenced wholesale; 61 complexity hotspots are
  grandfathered with `noqa: C901` burn-down notes.
- Deliberately **not** enabled: `E501` (the formatter enforces the width),
  `SIM105` (contextlib would obscure the existing error branches) and
  `RUF001-003` (the codebase intentionally uses ASCII punctuation in prose
  and strings).

## Consequences

- Formatting is now a non-issue in review: `uv run poe format-check` is the
  gate, and it runs on the whole tree.
- The first phase produced large mechanical diffs; those commits are marked
  as such in the history (`ruff format: apply to engine + root modules`,
  `ruff format: apply to ui/`) so they can be skipped during review.
- Docstring rules (`D103`) are active: public functions need a one-line
  summary; tests are exempt per-file because their names document them.
- The complexity budget (`max-complexity = 12`) is the burn-down target for
  the grandfathered functions; the advisory complexity report
  (`dv-hcg.45`) makes the trend visible.

## Links

- Beads: `dv-hcg` (audit), `dv-hcg.2` (formatter), `dv-hcg.3` (lint rules),
  `dv-hcg.44` (docstring rules), `dv-hcg.45` (complexity report).
- `pyproject.toml` — `[tool.ruff]` configuration.
- `docs/reference/project-layout.md` — quality gates.
