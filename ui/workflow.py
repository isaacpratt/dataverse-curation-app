"""Pure workflow state for the dataset detail step rail.

No Qt here: the detail view already tracks cheap booleans and counts
(metadata loaded, staged file count, cached report, export path, committed
decision). This module turns those into the six-step progress the rail
renders — metadata → changes → download → checks → export → respond.

The rail is guidance, not a gate: a step may be blocked (its prerequisite
is missing) but it is never disabled and clicking it never runs an action.
Keeping the derivation pure makes its tests fast and network-free.
"""

from __future__ import annotations

from dataclasses import dataclass

STEP_ORDER: tuple[str, ...] = (
    "metadata",
    "changes",
    "download",
    "checks",
    "export",
    "respond",
)

STEP_LABELS: dict[str, str] = {
    "metadata": "Metadata",
    "changes": "Changes",
    "download": "Download",
    "checks": "Checks",
    "export": "Export",
    "respond": "Respond",
}

DONE = "done"
CURRENT = "current"
AVAILABLE = "available"
BLOCKED = "blocked"


@dataclass(frozen=True)
class WorkflowInput:
    """Everything the derivation needs; all values are already known."""

    metadata_loaded: bool = False
    changes_loaded: bool = False
    # False when metadata loaded but the file list fetch failed, so an
    # unknown inventory is never mistaken for a zero-file dataset.
    inventory_ok: bool = True
    staged: int = 0
    total_files: int = 0
    report_ready: bool = False
    exported: bool = False
    response_open: bool = False
    decision_committed: bool = False


@dataclass(frozen=True)
class Step:
    key: str
    label: str
    state: str
    hint: str
    accessible: str


@dataclass(frozen=True)
class Workflow:
    steps: tuple[Step, ...]
    current: str | None
    hint: str

    def state_of(self, key: str) -> str:
        for step in self.steps:
            if step.key == key:
                return step.state
        return BLOCKED

    def step_of(self, key: str) -> Step | None:
        for step in self.steps:
            if step.key == key:
                return step
        return None


def derive_workflow(inp: WorkflowInput) -> Workflow:
    """Derive the six step states, the current step, and the next-step hint."""
    meta = bool(inp.metadata_loaded)
    inv_ok = bool(inp.inventory_ok)
    total = max(0, int(inp.total_files))
    staged = max(0, int(inp.staged))
    no_files = meta and inv_ok and total == 0
    download_done = no_files or (meta and inv_ok and total > 0 and staged >= total)

    # -- base states (before the single "current" overlay) ---------------
    base: dict[str, tuple[str, str]] = {}

    base["metadata"] = (
        (DONE, "Metadata loaded") if meta else (AVAILABLE, "Load the dataset metadata")
    )

    if inp.changes_loaded:
        base["changes"] = (DONE, "Changes reviewed")
    elif meta:
        base["changes"] = (AVAILABLE, "Review what changed in this version")
    else:
        base["changes"] = (BLOCKED, "Load metadata first")

    if download_done:
        hint = "No files to download" if no_files else f"All {total} file(s) staged"
        base["download"] = (DONE, hint)
    elif meta and not inv_ok:
        base["download"] = (AVAILABLE, "File list unavailable \u2014 retry Load metadata")
    elif meta:
        base["download"] = (AVAILABLE, f"{staged}/{total} staged" if total else "Download the files")
    else:
        base["download"] = (BLOCKED, "Load metadata first")

    checks_ready = staged > 0 or no_files
    if inp.report_ready:
        base["checks"] = (DONE, "Checks complete")
    elif checks_ready:
        base["checks"] = (AVAILABLE, "Run the automated checks")
    else:
        base["checks"] = (BLOCKED, "Download files first")

    if inp.exported:
        base["export"] = (DONE, "Reports exported")
    elif inp.report_ready:
        base["export"] = (AVAILABLE, "Export the reports")
    else:
        base["export"] = (BLOCKED, "Run checks first")

    if inp.decision_committed:
        base["respond"] = (DONE, "Decision recorded")
    else:
        base["respond"] = (AVAILABLE, "Draft the response")

    # -- one current step ------------------------------------------------
    done = {key for key, (state, _hint) in base.items() if state == DONE}
    current: str | None = None
    if inp.response_open and not inp.decision_committed:
        current = "respond"
    else:
        for key in STEP_ORDER:
            if key not in done:
                current = key
                break

    # -- next-step hint --------------------------------------------------
    if current is None:
        hint = "Workflow complete"
    elif current == "download" and 0 < staged < total:
        hint = f"{staged}/{total} staged"
    elif inp.response_open and current == "respond":
        outstanding = next(
            (key for key in STEP_ORDER if key != "respond" and key not in done),
            None,
        )
        hint = f"Next: {STEP_LABELS[outstanding]}" if outstanding else "Draft the response"
    else:
        hint = f"Next: {STEP_LABELS[current]}"

    steps: list[Step] = []
    for key in STEP_ORDER:
        state, step_hint = base[key]
        if key == current:
            state = CURRENT
        label = STEP_LABELS[key]
        steps.append(
            Step(
                key=key,
                label=label,
                state=state,
                hint=step_hint,
                accessible=f"{label}, {state} step",
            )
        )
    return Workflow(steps=tuple(steps), current=current, hint=hint)
