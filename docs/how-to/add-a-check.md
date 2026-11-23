---
page_type: how-to
tgdp_template: How-to
audience: developer
---

# Add a check

Add a format or dataset check to the engine, register it, test it, and document its findings so the dispatcher, the runner, and the Auto-Checks card can discover it.

## Prerequisites

- Python 3.11+ and a synced environment (`uv sync --group dev`).
- Familiarity with the engine layout in [the project layout reference](../reference/project-layout.md).

## Steps

1. Create `engine/checks/<format>_check.py`. Declare a `Check` subclass with a unique `check_id` in the `format.<name>` namespace, a `scope` of `"dataset"` or `"file"`, and an `extensions` set listing the file suffixes the check reads. Import heavy or optional libraries lazily inside `run()` or `_run_one()`, and return `_util.missing_library(...)` when an optional library is absent.

   ```python
   from pathlib import Path
   from typing import ClassVar

   from engine.checks.base import Check, CheckResult


   class MyFormatCheck(Check):
       check_id = "format.myformat"
       scope: ClassVar[str] = "file"
       extensions: ClassVar[set[str]] = {".mf"}

       def run(self, files: list[Path]) -> list[CheckResult]: ...
   ```

2. Register the module. Import it in `engine/checks/__init__.py` and append it to `_MODULES`. The registry, dispatcher, `list_planned_checks()`, and runner all discover checks from that tuple. `register_checks()` rejects any class that does not declare `scope`.

3. Add fixtures and tests. Place small known-good and known-bad fixture files beside the test that uses them. Add cases to `engine/tests/test_formats.py` (or a matching `engine/tests/test_<format>_check.py`) that assert the `CheckResult` values, and cover the scope declaration in `engine/tests/test_check_scope.py`. Run the engine suite:

   ```powershell
   uv run pytest engine/tests -q
   ```

4. Run the gates. Follow [Run the gates](run-the-gates.md) and confirm `uv run poe check` and `uv run poe probes` pass. [The project layout reference](../reference/project-layout.md) lists where each suite lives.

5. Document the semantics. Describe what the check examines, its `check_id` values, and the meaning of each finding in [the checks reference](../reference/checks.md).
