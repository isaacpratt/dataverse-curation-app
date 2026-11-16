# Agent Instructions

Design decisions: native PySide6 desktop app (single process), API-token authentication against the Dataverse Native/Search API, SQLite for local state, PyInstaller packaging. See `docs/html/architecture.html`.

## Repository layout

```
dataverse-curation-app/
├── docs/html/            # documentation (source of truth): architecture, engine port, checks, dataverse, report contract, dev, user guide
├── engine/               # Python check engine (ports of the R inspectors)
│   ├── checks/           # one module per format (22), plus base.py/_util.py
│   ├── report.py         # DatasetReport JSON contract
│   ├── dispatcher.py     # extension -> check mapping
│   ├── runner.py         # run_report / list_planned_checks
│   └── tests/            # pytest suite (212 tests; see CI)
├── ui/                   # PySide6 views (main window, dashboard, detail, settings/about panes, log page, workers, dialogs, theme, widgets incl. AppTable content-fit, progress ring)
│   ├── theme.py          # palette -> semantic roles -> contrast contract -> one button system
│   ├── widgets.py        # the component kit (every view builds its controls through it)
│   ├── gallery.py        # the component gallery: every kit component on one page
│   └── table_layout.py   # one layout controller per table header (persists user gestures only)
├── tools/                  # operational helpers (audit/SBOM/licenses, smoke, startup probe) + probes/
│   ├── probes/             # offscreen UI probes (queue columns, manifest columns, page headings, card corner, buttons, gallery)
│   └── startup_probe.py    # opt-in startup phase timings (DOCENT_STARTUP_LOG)
├── client/               # Native/Search API client (constants/errors/http/parsers/caches/downloads/DataverseClient; total-driven paginated search + pooled inventory enrichment, versions/compare/timestamps/notifications/curation labels)
├── dataverse_client.py   # compatibility shim re-exporting client/ (existing imports keep working)
├── download_manager.py   # approval-gated downloads, originals, skip-if-staged, verify (ok/problems/warnings)
├── metadata_check.py     # citation-block completeness (McMaster / Minimal profiles)
├── applog.py             # in-memory request log (Log page)
├── storage.py            # SQLite local state + JSON caches (sizes, labels, table layout)
├── main.py               # entry point (GUI + --headless)
└── config.example.json   # configuration template (copy to config.json)
```

## Quick start (development)

```bash
uv sync                   # create .venv and install everything incl. dev group (from uv.lock; no pip needed)
copy config.example.json config.json   # Windows cmd (PowerShell: Copy-Item config.example.json config.json); default is the Borealis demo (demo.borealisdata.ca); edit base_url/api_token for your instance
uv run pytest             # 513 tests (218 engine + 295 UI; run uv run pytest --collect-only -q for current count)
pre-commit run --all-files # optional local gate (CI runs it too); needs uv on PATH. core.hooksPath is beads-managed, so hooks are not auto-installed — run it manually or rely on CI (uv run poe hooks wraps the same thing)
uv run poe audit        # OSV vulnerability scan of the locked dependency set (fails on any advisory)
uv run poe hooks        # pre-commit run --all-files (wrapped for uv users)
uv run python main.py                # launch the desktop GUI — pick the Dataverse in the top-nav Settings page (demo preset included)
uv run python main.py --gallery      # the component gallery: every kit component on one page
# headless against a staged directory (--dataverse/--config are GUI-only):
uv run python main.py --headless <staged_dir> --out report.json --format json --persistent-id doi:10.5072/FK2/EXAMPLE
```

Requirements: Python 3.11+ (Windows recommended); builds pin Python 3.11 via `.python-version` and `uv.lock`. Earlier `pip install -r requirements.txt` workflow is gone — dependencies live only in `pyproject.toml` + `uv.lock` (pip escape hatch: `uv export --format requirements-txt`). Headless exit codes: 0 clean, 1 error-level findings, 2 usage/IO failure. R is only needed for parity verification against the original scripts during the port phase, not at runtime.

## Packaging (portable)

```bash
poe build          # both: lite onedir + full onedir folder in dist/
poe build-lite     # lite folder only; incremental, keeps dist/curation-app-full/
poe build-full     # onedir folder only
poe smoke          # lite smoke test: --headless --help + frozen CSV/PII probe
```

All build commands also work identically from bare cmd/PowerShell (no Git Bash); `make` and `build-lite.ps1` were removed when poe was adopted. poe is in the dev dependency group; run it as `uv run poe …`.

Outputs: `dist/curation-app-lite/curation-app-lite.exe` (onedir folder, fast launches — common formats JPG/PNG/PDF/XML/XLSX/TIFF bundled, work offline) next to `dist/curation-app-full/` (heavy libs pyreadstat/netCDF4/h5py/scipy — run its exe directly for SPSS/SAS/Stata/NetCDF/HDF5/MAT). Missing optional libs report “Missing …” in the Auto-Checks card rather than failing; JPG/PNG/GIF/BMP/WEBP fall back to a stdlib header parse when Pillow is absent.

## Documentation

- `docs/html/architecture.html` — components, threading, storage, the UI layering contract (palette → role → component), the table component contract, packaging
- `docs/html/engine-port.html` — R-to-Python port matrix and go/no-go criteria
- `docs/html/checks-reference.html` — what each auto-check examines, PASS semantics, issue taxonomy
- `docs/html/dataverse-integration.html` — Native/Search API endpoints, auth, discovery + download flow
- `docs/html/report-contract.html` — the JSON report format shared by engine and GUI
- `docs/html/development.html` — setup, testing, adding checks, UI conventions, the component gallery, Qt pitfalls, probes, the planned dark-mode step, packaging
- `docs/html/user-guide.html` — how a curator uses the app (dashboard, detail, metadata, log)
- `docs/html/proposals.html` — pointer stub; plan lives in beads (`bd ready` / `bd list`)

This project uses **bd** (beads) for issue tracking and project plan. Run `bd prime` for full workflow context.

> **Architecture in one line:** Issues live in a local Dolt database
> (`.beads/dolt/`); cross-machine sync uses `bd dolt push/pull` (a
> git-compatible protocol), stored under `refs/dolt/data` on your git
> remote — separate from `refs/heads/*` where your code lives.
> `.beads/issues.jsonl` is a passive export, not the wire protocol.
>
> See [sync-concepts](https://github.com/gastownhall/beads/blob/main/docs/core-concepts/sync-concepts.md)
> for the one-screen overview and anti-patterns (don't treat JSONL as the
> source of truth; don't `bd import` during normal operation; don't
> reach for third-party Dolt hosting before trying the default).

## Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work atomically
bd close <id>         # Complete work
bd dolt push          # Push beads data to remote
```

## Testing

Gate before handoff; run from the repository root when code (not docs-only) changed:

- **Module sizes**: view modules aim for ≤ ~1,000 lines and engine modules ≤ ~1,500; oversize view modules are missing a subcomponent. Exceptions carry a dated comment naming the reason. `poe check` (format + C90 budget) is the mechanical backstop, this line is the expectation for reviewers.

- `uv run pytest -q` — must exit 0
- `uv run poe typecheck` — must report `Success: no issues found`; scope is the engine contract (`[tool.mypy] files`), so run bare `uv run mypy`
- `uv run poe contracts` — import-linter contracts must stay green: `engine/` may not import `ui/` or `PySide6`, and the operational helpers in `tools/` may not import `ui/` (the UI probes and the two engine-test fixtures are the documented exceptions)
- `python tools/probes/run_all.py` — must end with `all N probes passed`; mandatory for UI/theme changes, and cheap enough to always run
- headless box? set `QT_QPA_PLATFORM=offscreen` first, or the probes fail for the wrong reason
- probes run against a throwaway temp workspace (see `tools/probes/README.md`) — never against the configured instance or the real `workspace/table_layout.json`
- docs-only changes need neither

## Non-Interactive Shell Commands

**ALWAYS use non-interactive flags** with file operations to avoid hanging on confirmation prompts.

Shell commands like `cp`, `mv`, and `rm` may be aliased to include `-i` (interactive) mode on some systems, causing the agent to hang indefinitely waiting for y/n input.

**Use these forms instead:**
```bash
# Force overwrite without prompting
cp -f source dest           # NOT: cp source dest
mv -f source dest           # NOT: mv source dest
rm -f file                  # NOT: rm file

# For recursive operations
rm -rf directory            # NOT: rm -r directory
cp -rf source dest          # NOT: cp -r source dest
```

**Other commands that may prompt:**
- `scp` - use `-o BatchMode=yes` for non-interactive
- `ssh` - use `-o BatchMode=yes` to fail instead of prompting
- `apt-get` - use `-y` flag
- `brew` - use `HOMEBREW_NO_AUTO_UPDATE=1` env var

<!-- BEGIN BEADS INTEGRATION v:1 profile:full hash:bacef91e -->
## Issue Tracking with bd (beads)

**IMPORTANT**: This project uses **bd (beads)** for ALL issue tracking. Do NOT use markdown TODOs, task lists, or other tracking methods.

### Why bd?

- Dependency-aware: Track blockers and relationships between issues
- Git-friendly: Dolt-powered version control with native sync
- Agent-optimized: JSON output, ready work detection, discovered-from links
- Prevents duplicate tracking systems and confusion

### Quick Start

**Check for ready work:**

```bash
bd ready --json
```

**Create new issues:**

```bash
bd create "Issue title" --description="Detailed context" -t bug|feature|task -p 0-4 --json
bd create "Issue title" --description="What this issue is about" -p 1 --deps discovered-from:bd-123 --json
```

**Claim and update:**

```bash
bd update <id> --claim --json
bd update bd-42 --priority 1 --json
```

**Complete work:**

```bash
bd close bd-42 --reason "Completed" --json
```

### Issue Types

- `bug` - Something broken
- `feature` - New functionality
- `task` - Work item (tests, docs, refactoring)
- `epic` - Large feature with subtasks
- `chore` - Maintenance (dependencies, tooling)

### Priorities

- `0` - Critical (security, data loss, broken builds)
- `1` - High (major features, important bugs)
- `2` - Medium (default, nice-to-have)
- `3` - Low (polish, optimization)
- `4` - Backlog (future ideas)

### Workflow for AI Agents

1. **Check ready work**: `bd ready` shows unblocked issues
2. **Claim your task atomically**: `bd update <id> --claim`
3. **Work on it**: Implement, test, document
4. **Discover new work?** Create linked issue:
   - `bd create "Found bug" --description="Details about what was found" -p 1 --deps discovered-from:<parent-id>`
5. **Complete**: `bd close <id> --reason "Done"`

### Quality
- Use `--acceptance` and `--design` fields when creating issues
- Use `--validate` to check description completeness

### Lifecycle
- `bd defer <id>` / `bd supersede <id>` for issue management
- `bd stale` / `bd orphans` / `bd lint` for hygiene
- `bd human <id>` to flag for human decisions
- `bd formula list` / `bd mol pour <name>` for structured workflows

### Sync

bd stores issue history in Dolt:

- Each write auto-commits to Dolt history
- Use `bd dolt push`/`bd dolt pull` for remote sync
- Do not treat `.beads/issues.jsonl` as the sync protocol

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/core-concepts/sync-concepts.md for details and anti-patterns.

### Important Rules

- ✅ Use bd for ALL task tracking
- ✅ Always use `--json` flag for programmatic use
- ✅ Link discovered work with `discovered-from` dependencies
- ✅ Check `bd ready` before asking "what should I work on?"
- ❌ Do NOT create markdown TODO lists
- ❌ Do NOT use external issue trackers
- ❌ Do NOT duplicate tracking systems

For more details, see README.md and https://github.com/gastownhall/beads/blob/main/docs/getting-started/quickstart.md.

<!-- END BEADS INTEGRATION -->

## Repository profile & overrides

The Beads block is generated by `bd setup codex` and governs only `bd` mechanics — it is re-generated on every run. This section and every other section in this file *outside* the Beads markers (`## Testing`, `## Git rules`, repository layout, quick start) are user-owned and govern project policy; where they conflict with the block, they win. Explicit user or orchestrator instructions override everything.

## Agent Context Profiles

- **Conservative**: Use `bd` for task tracking. Do not run git commits, git pushes, or Dolt remote sync unless explicitly asked. At handoff, report changed files, validation, and suggested next commands.
- **Standard (default)**: Use `bd` for task tracking. At handoff, report changed files, validation, and next commands. When the user's request is satisfied: run the gates (if code changed — pytest + tools/probes/run_all.py), git commit only the files changed for the task (never git add -A), and bd dolt push. Do not git push without being asked. Do not commit unrelated modifications or untracked files. Close the bead for the work with `bd close --reason`
- **Minimal**: Keep tool instruction files as pointers to `bd prime`; use the same conservative git policy unless active instructions say otherwise.
- **Team-maintainer**: Only when the repository explicitly opts in, agents may close beads, run quality gates, and commit as part of session close. A current "do not commit" or "do not push" instruction still wins.

## Session Completion

This protocol applies when ending a Beads implementation workflow. It is subordinate to explicit user, repository, and orchestrator instructions.

1. **File issues for remaining work** - Create beads for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **Handle git/sync by active profile**:
   ```bash
   # Conservative/minimal: report status and proposed commands; wait for approval.
   git status

   # Standard/Team-maintainer: report status and proposed commands, and unless current instructions forbid it:
   git pull --rebase
   bd dolt push
   git status
   ```
5. **Hand off** - Summarize changes, validation, issue status, and any blocked sync/commit/push step

**Critical rules:**
- Explicit user or orchestrator instructions override this repository profile.
- Do not commit or push without clear authority from the active profile or the current user request.
- If a required sync or push is blocked, stop and report the exact command and error.

## Git rules

- ❌ Do NOT `git push` without being asked. No profile authorizes it; only an explicit user request or orchestrator instruction does.

## Bead creation

Use `.beads/templates/bead-creation.md` for every new bead. Before creating: `bd list` + `bd search` for dedup, confirm the item is still open (closed items are in beads, not `docs/html/proposals.html` — never re-create them), set type/priority, and order children with `bd dep add` so `bv` shows the work order. Descriptions are self-contained markdown: Outcome → Context (with file/section anchors) → Hooks → Tests (unit + e2e/probe, with what passing looks like). One bead, one outcome — split sequencing into separate beads. After creating, `bd show <id>` and fix anything that needs context you had to remember.

## License

MIT — see [LICENSE](LICENSE). The engine checks are ported from the MIT-licensed `CUR_Res_CurationTools` (© 2026 Curation Services Team, Digital Research Alliance of Canada); see LICENSE for full third-party attributions.
