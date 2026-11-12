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
├── tools/probes/         # offscreen UI probes (queue columns, manifest columns, page headings, card corner, buttons, gallery)
├── dataverse_client.py   # Native/Search API client (total-driven paginated search + pooled inventory enrichment, versions/compare/timestamps/notifications/curation labels)
├── download_manager.py   # approval-gated downloads, originals, skip-if-staged, verify (ok/problems/warnings)
├── metadata_check.py     # citation-block completeness (McMaster / Minimal profiles)
├── applog.py             # in-memory request log (Log page)
├── storage.py            # SQLite local state + JSON caches (sizes, labels, table layout)
├── main.py               # entry point (GUI + --headless)
└── config.example.json   # configuration template (copy to config.json)
```

## Quick start (development)

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy config.example.json config.json   # Windows cmd (PowerShell: Copy-Item config.example.json config.json); default is the Borealis demo (demo.borealisdata.ca); edit base_url/api_token for your instance
pytest                        # 499 tests (212 engine + 287 UI; run pytest --collect-only -q for current count)
python -m pip install -e ".[dev]"   # dev extras: needed only for `make typecheck` (mypy)
python main.py                # launch the desktop GUI — pick the Dataverse in the top-nav Settings page (demo preset included)
python main.py --gallery      # the component gallery: every kit component on one page
# headless against a staged directory (--dataverse/--config are GUI-only):
python main.py --headless <staged_dir> --out report.json --format json --persistent-id doi:10.5072/FK2/EXAMPLE
```

Requirements: Python 3.10+ (Windows recommended). `make` needs Git Bash on Windows; without it, run `.\build-lite.ps1` in PowerShell (same flags as `Makefile:rebuild-lite`). Headless exit codes: 0 clean, 1 error-level findings, 2 usage/IO failure. R is only needed for parity verification against the original scripts during the port phase, not at runtime.

## Packaging (portable)

```bash
make build         # both: lite onedir + full onedir folder in dist/
make rebuild-lite  # lite folder only (~2 min), keeps dist/curation-app-full/
make build-full    # onedir folder only
```

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

## Agent Context Profiles

The managed Beads block is task-tracking guidance, not permission to override repository, user, or orchestrator instructions.

- **Conservative (default)**: Use `bd` for task tracking. Do not run git commits, git pushes, or Dolt remote sync unless explicitly asked. At handoff, report changed files, validation, and suggested next commands.
- **Minimal**: Keep tool instruction files as pointers to `bd prime`; use the same conservative git policy unless active instructions say otherwise.
- **Team-maintainer**: Only when the repository explicitly opts in, agents may close beads, run quality gates, commit, and push as part of session close. A current "do not commit" or "do not push" instruction still wins.

## Session Completion

This protocol applies when ending a Beads implementation workflow. It is subordinate to explicit user, repository, and orchestrator instructions.

1. **File issues for remaining work** - Create beads for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **Handle git/sync by active profile**:
   ```bash
   # Conservative/minimal/default: report status and proposed commands; wait for approval.
   git status

   # Team-maintainer opt-in only, unless current instructions forbid it:
   git pull --rebase
   bd dolt push
   git push
   git status
   ```
5. **Hand off** - Summarize changes, validation, issue status, and any blocked sync/commit/push step

**Critical rules:**
- Explicit user or orchestrator instructions override this Beads block.
- Do not commit or push without clear authority from the active profile or the current user request.
- If a required sync or push is blocked, stop and report the exact command and error.

<!-- END BEADS INTEGRATION -->

## Bead creation

Use `.beads/templates/bead-creation.md` for every new bead. Before creating: `bd list` + `bd search` for dedup, confirm the item is still open (closed items are in beads, not `docs/html/proposals.html` — never re-create them), set type/priority, and order children with `bd dep add` so `bv` shows the work order. Descriptions are self-contained markdown: Outcome → Context (with file/section anchors) → Hooks → Tests (unit + e2e/probe, with what passing looks like). One bead, one outcome — split sequencing into separate beads. After creating, `bd show <id>` and fix anything that needs context you had to remember.

## License

MIT — see [LICENSE](LICENSE). The engine checks are ported from the MIT-licensed `CUR_Res_CurationTools` (© 2026 Curation Services Team, Digital Research Alliance of Canada); see LICENSE for full third-party attributions.
