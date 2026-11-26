# ADR 0008 — All application code is checked under full `--strict`; only test modules relax annotation requirements

- **Status:** Accepted
- **Date:** 2026-11-20
- **Supersedes:** ADR 0007 (the `ui.*` relaxation is withdrawn)

## Context

ADR 0007 brought `ui/` under the mypy gate with a documented relaxation:
`disallow_untyped_defs`, `disallow_untyped_calls`, `disallow_incomplete_defs`,
`disallow_any_generics`, `warn_return_any` and `no_implicit_reexport` were all
turned off for `ui.*`, and a similar relaxation covered the test packages.
The rationale at the time was that PySide6 ships no usable stubs for the widget
tree, so a fully strict UI would need thousands of `Any` annotations that add
no safety.

Two things changed:

1. The enum sweep and the shape fixes from `dv-hcg.28` are in place, so the
   UI tree no longer depends on forgiveness-mode aliases or has the undeclared
   mixin attributes that made strict checking noisy. What remains is ordinary
   annotation work, not stub ambiguity.
2. The relaxation kept widening: with six "you must annotate" rules off, the
   UI layer was effectively outside the strict contract the engine and
   curation core have always satisfied. A contributor could not tell, from
   the config, which rules actually applied.

A census (2026-11-20) measured the cost of closing the gap: 959 strict errors,
dominated by `no-untyped-call` (579), `no-untyped-def` (193) and `type-arg`
(163), plus 23 `no-any-return` and one `attr-defined`. These are mechanical,
behaviour-preserving annotation fixes — they add no runtime code.

## Decision

- **Every application module — `engine/`, `curation/`, `ui/`, `main.py` and
  the `tools/` helpers in scope — is checked under full `mypy --strict`,
  with no per-module override.** There is no `ui.*` relaxation any more.
- **Only the test modules relax, and only these three rules:**
  `disallow_untyped_defs = false`, `disallow_incomplete_defs = false`,
  `disallow_untyped_decorators = false`.
- **`check_untyped_defs = true` stays on for the tests.** The bodies of
  unannotated test functions are still checked; only the obligation to
  annotate the function itself is lifted.
- **Every other strict rule stays on for tests**, including
  `disallow_untyped_calls`, `disallow_any_generics`, `warn_return_any` and
  all shape checks. The single override block lists the four test packages
  (`curation.tests.*`, `engine.tests.*`, `tools.tests.*`, `ui.tests.*`) and
  nothing else.

## Consequences

- The type contract is now simple to state and to audit: application code is
  strict; tests are checked but not required to be annotated. One override
  block, four flags, four test packages.
- Closing the UI gap touched the whole view layer (`widgets.py`, the kit, the
  dataset package, the view/dialog/worker modules) with annotation-only
  changes. Because `from __future__ import annotations` is used throughout,
  these annotations are strings at runtime: no behaviour, copy, geometry or
  layout changed.
- A consequence worth knowing: under `check_untyped_defs`, mypy checks the
  body of an unannotated function as a typed context, so a call to a fully
  unannotated helper still raises `no-untyped-call`. Annotating a helper's
  *parameters* (the return type is optional under `disallow_incomplete_defs =
  false`) is enough to make it callable from checked test code. Test helpers
  therefore carry parameter annotations even though the tests that use them
  do not have to.
- The gate is green: `uv run mypy` reports no errors across all source and
  test files. pytest, the probe suite, contracts, ruff and pre-commit remain
  green.

## Links

- Bead: `dv-a4w` (the ratified policy decision and implementation).
- `pyproject.toml` — `[tool.mypy]` and the single `[[tool.mypy.overrides]]`
  block for the four test packages.
- `docs/internal/reference/project-layout.md` — the type-check gate description.
- ADR 0007 — the earlier UI relaxation, superseded by this ADR.
