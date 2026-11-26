# ADR 0007 — The UI layer joins the mypy gate under a documented relaxation of `--strict`

- **Status:** Superseded by ADR 0008 — the `ui.*` relaxation is withdrawn; all application code is now checked under full `--strict`.
- **Date:** 2026-11-17

## Context

The engine contract has been gated under `mypy --strict` since
`dv-hcg.27` (ADR 0004-era toolchain work), but the Qt view layer was
outside the gate: `[tool.mypy] files` listed `engine/` and `curation/`
only, and `ui/` was excluded by default. The exclusion hid real defects.

The census behind `dv-hcg.28` (2026-11-16) measured **308 mypy errors in
20 UI files**. 232 of them (75%) had one mechanical cause: PySide6's
stubs expose enums only under their scoped names, so forgiveness-mode
aliases such as `Qt.PointingHandCursor`, `Qt.UserRole`,
`QHeaderView.Interactive` or `QSizePolicy.Preferred` are `attr-defined`
at check time while remaining valid at runtime. The other 76 were shape
bugs — `int(QSize)`, a mixin calling methods it never declared, an
attribute annotated in one place and redefined in another, functions used
for their return value, `itemFromIndex` called on the abstract base model.

Two constraints shaped the answer:

1. **PySide6 ships no usable stubs for the widget tree.** The widgets are
   created in code, not declared, so a fully strict UI would need
   thousands of `Any` annotations that add no safety and are erased by
   the first refactor.
2. **The gate has to buy something.** A check that reports nothing is
   decoration. The checks that found the real defects are the *shape*
   checks: `attr-defined`, `union-attr`, `assignment`, `arg-type`,
   `operator`, `has-type`, `var-annotated`, `func-returns-value`,
   `no-redef`.

## Decision

- **`ui/` and `main.py` join `[tool.mypy] files`.** The scope is now
  `["engine", "curation", "ui", "main.py"]` — the whole shipped tree,
  with no exclusion list.
- **The UI layer is checked under a documented relaxation of
  `--strict`**, expressed as a `[[tool.mypy.overrides]]` block for
  `module = ["ui.*"]`: `disallow_untyped_defs`,
  `disallow_untyped_calls`, `disallow_incomplete_defs`,
  `disallow_any_generics`, `warn_return_any` and
  `no_implicit_reexport` are off. `check_untyped_defs` stays **on**, so
  the bodies of unannotated functions are still checked; only the
  "you must annotate this" rules are relaxed.
- **`main.py` keeps the full strict settings.** It is the entry point,
  not a UI module, and it is small enough to stay strict.
- **The forgiveness-mode enum aliases are gone.** Every alias was
  rewritten to its scoped PySide6 name (`Qt.CursorShape.PointingHandCursor`,
  `Qt.ItemDataRole.UserRole`, `QHeaderView.ResizeMode.Interactive`,
  `QSizePolicy.Policy.Preferred`, …): 252 call sites across 25 files.
  The aliases are deprecated, and the scoped names are what the stubs
  describe.
- **The relaxation is a floor, not a ceiling.** New UI code may be
  annotated, and the override can be narrowed module by module as views
  are reworked; the ADR is amended when it is.

## Consequences

- The UI gate is green: **0 errors**, 144 source files checked, no
  per-module ignore list anywhere in `pyproject.toml`.
- The ramp found and fixed real defects, not just alias noise: `int(QSize)`
  (a width that was never a width), the `_BranchPainting` mixin's
  undeclared `model`/`isExpanded`/`indentation`, the twice-declared
  `_all_file_rows`, the dashboard's tuple-lambda used for its value,
  `itemFromIndex` called on `QAbstractItemModel`, and the
  `DownloadCancelled` re-export that did not exist.
- Rendering is unchanged: the enum values are identical at runtime, which
  the 548-test suite and the four UI probes confirm.
- The gate now covers the tests as well as the sources, so a test double
  that drifts from the signature it stands in for (`MainWindow._apply_dwm_frame`
  called with a stub) is a type error instead of a comment.
- The cost is that the UI is not *fully* strict. The relaxed rules are
  the ones that demand annotations everywhere; the ones that catch bugs
  are all still on.

## Links

- Beads: `dv-hcg` (audit), `dv-hcg.28` (UI typing ramp), `dv-5ns`
  (the original typing bead, superseded by the ramp).
- `pyproject.toml` — `[tool.mypy] files` and the `ui.*` override.
- `docs/internal/reference/project-layout.md` — the type-check gate.
- ADR 0006 — the curation core package (the mypy scope it described).
