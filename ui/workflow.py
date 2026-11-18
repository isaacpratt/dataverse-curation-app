"""Pure workflow state for the dataset detail step rail.

No Qt here: the detail view already tracks cheap booleans and counts
(metadata loaded, staged file count, cached report, export path, committed
decision). This module turns those into the six-step progress the rail
renders — metadata → changes → download → checks → export → respond.

The rail is guidance, not a gate: a step may be blocked (its prerequisite
is missing) but it is never disabled and clicking it never runs an action.
Keeping the derivation pure makes its tests fast and network-free.

The wording comes from ``ui/assets/strings.json``; this module stays Qt-free
by using the standard-library catalogue loader only.
"""

from __future__ import annotations

from dataclasses import dataclass

from ui.i18n import t

STEP_ORDER: tuple[str, ...] = (
    "metadata",
    "changes",
    "download",
    "checks",
    "export",
    "respond",
)

# The step label for each key lives in the string catalogue; the map below
# only says which catalogue entry belongs to which step.  Keys are literal so
# the string guard can see that every entry is referenced.
STEP_LABEL_KEYS: dict[str, str] = {
    "metadata": "workflow.step.metadata",
    "changes": "workflow.step.changes",
    "download": "workflow.step.download",
    "checks": "workflow.step.checks",
    "export": "workflow.step.export",
    "respond": "workflow.step.respond",
}


DONE = "done"
CURRENT = "current"
AVAILABLE = "available"
BLOCKED = "blocked"


def step_labels() -> dict[str, str]:
    """Return the step labels, read from the catalogue at call time."""
    return {key: t(catalogue_key) for key, catalogue_key in STEP_LABEL_KEYS.items()}


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
    # Review-signal counts (dv-sce): only the CURATE(D) derivation reads
    # them; the mechanical derivation ignores them. Unresolved findings
    # and incomplete rules — the caller computes them from the report,
    # completeness, and dispositions (no I/O here).
    errors: int = 0
    warnings: int = 0
    required_missing: int = 0
    optional_missing: int = 0


@dataclass(frozen=True)
class Step:
    key: str
    label: str
    state: str
    hint: str
    accessible: str
    # Optional short prefix replacing the step number (dv-sce): the
    # CURATE(D) view badges its steps C/U/R/A/T/E/D.
    badge: str = ""


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


def derive_workflow(inp: WorkflowInput) -> Workflow:  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
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
        (DONE, t("workflow.hint.metadata_loaded"))
        if meta
        else (AVAILABLE, t("workflow.hint.load_metadata"))
    )

    if inp.changes_loaded:
        base["changes"] = (DONE, t("workflow.hint.changes_reviewed"))
    elif meta:
        base["changes"] = (AVAILABLE, t("workflow.hint.review_changes"))
    else:
        base["changes"] = (BLOCKED, t("workflow.hint.load_metadata_first"))

    if download_done:
        hint = (
            t("workflow.hint.no_files") if no_files else t("workflow.hint.all_staged", total=total)
        )
        base["download"] = (DONE, hint)
    elif meta and not inv_ok:
        base["download"] = (AVAILABLE, t("workflow.hint.inventory_unavailable"))
    elif meta:
        base["download"] = (
            (AVAILABLE, t("workflow.hint.staged", staged=staged, total=total))
            if total
            else (AVAILABLE, t("workflow.hint.download_files"))
        )
    else:
        base["download"] = (BLOCKED, t("workflow.hint.load_metadata_first"))

    checks_ready = staged > 0 or no_files
    if inp.report_ready:
        base["checks"] = (DONE, t("workflow.hint.checks_complete"))
    elif checks_ready:
        base["checks"] = (AVAILABLE, t("workflow.hint.run_checks"))
    else:
        base["checks"] = (BLOCKED, t("workflow.hint.download_first"))

    if inp.exported:
        base["export"] = (DONE, t("workflow.hint.reports_exported"))
    elif inp.report_ready:
        base["export"] = (AVAILABLE, t("workflow.hint.export_reports"))
    else:
        base["export"] = (BLOCKED, t("workflow.hint.run_checks_first"))

    if inp.decision_committed:
        base["respond"] = (DONE, t("workflow.hint.decision_recorded"))
    else:
        base["respond"] = (AVAILABLE, t("workflow.hint.draft_response"))

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
    labels = step_labels()
    if current is None:
        hint = t("workflow.hint.complete")
    elif current == "download" and 0 < staged < total:
        hint = t("workflow.hint.staged", staged=staged, total=total)
    elif inp.response_open and current == "respond":
        outstanding = next(
            (key for key in STEP_ORDER if key != "respond" and key not in done),
            None,
        )
        hint = (
            t("workflow.hint.next", label=labels[outstanding])
            if outstanding
            else t("workflow.hint.draft_response")
        )
    else:
        hint = t("workflow.hint.next", label=labels[current])

    steps: list[Step] = []
    for key in STEP_ORDER:
        state, step_hint = base[key]
        if key == current:
            state = CURRENT
        label = labels[key]
        steps.append(
            Step(
                key=key,
                label=label,
                state=state,
                hint=step_hint,
                accessible=t("workflow.accessible.step", label=label, state=state),
            )
        )
    return Workflow(steps=tuple(steps), current=current, hint=hint)


# --------------------------------------------------------------------------
# The CURATE(D) practice view (dv-sce): the same rail, spoken in the DCN's
# shared curation vocabulary (Check, Understand, Request, Augment, Transform,
# Evaluate, Document — z.umn.edu/curate), each step carrying a live
# open-item count. Pure like derive_workflow: no I/O, never acts.

CURATED_ORDER: tuple[str, ...] = (
    "check",
    "understand",
    "request",
    "augment",
    "transform",
    "evaluate",
    "document",
)

CURATED_BADGES: dict[str, str] = {
    "check": "C",
    "understand": "U",
    "request": "R",
    "augment": "A",
    "transform": "T",
    "evaluate": "E",
    "document": "D",
}

# The label keys are literal so the string guard sees every reference.
CURATED_LABEL_KEYS: dict[str, str] = {
    "check": "workflow.curated.label_check",
    "understand": "workflow.curated.label_understand",
    "request": "workflow.curated.label_request",
    "augment": "workflow.curated.label_augment",
    "transform": "workflow.curated.label_transform",
    "evaluate": "workflow.curated.label_evaluate",
    "document": "workflow.curated.label_document",
}


def derive_curated(inp: WorkflowInput) -> Workflow:
    """Derive the seven CURATE(D) step states, current step, and hint."""
    meta = bool(inp.metadata_loaded)
    inv_ok = bool(inp.inventory_ok)
    total = max(0, int(inp.total_files))
    staged = max(0, int(inp.staged))
    no_files = meta and inv_ok and total == 0
    download_done = no_files or (meta and inv_ok and total > 0 and staged >= total)
    download_blocked = meta and not no_files and total > 0 and staged == 0
    outstanding = max(0, int(inp.errors)) + max(0, int(inp.warnings))
    required = max(0, int(inp.required_missing))
    optional = max(0, int(inp.optional_missing))
    report_ready = bool(inp.report_ready)

    base: dict[str, tuple[str, str]] = {}
    base["check"] = (
        (DONE, t("workflow.curated.check_done"))
        if download_done
        else (BLOCKED, t("workflow.hint.load_metadata_first"))
        if not meta
        else (
            AVAILABLE,
            t("workflow.hint.staged", staged=staged, total=total)
            if total
            else t("workflow.curated.check_open"),
        )
    )
    base["understand"] = (
        (DONE, t("workflow.curated.understand_done"))
        if report_ready
        else (BLOCKED, t("workflow.hint.download_first"))
        if download_blocked
        else (AVAILABLE, t("workflow.curated.understand_pending"))
    )
    base["request"] = (
        (DONE, t("workflow.curated.request_done"))
        if meta and required == 0
        else (BLOCKED, t("workflow.hint.load_metadata_first"))
        if not meta
        else (AVAILABLE, t("workflow.curated.request_pending", count=required))
    )
    base["augment"] = (
        (DONE, t("workflow.curated.augment_done"))
        if meta and optional == 0
        else (BLOCKED, t("workflow.hint.load_metadata_first"))
        if not meta
        else (AVAILABLE, t("workflow.curated.augment_pending", count=optional))
    )
    base["transform"] = (
        (DONE, t("workflow.curated.transform_done"))
        if report_ready
        else (BLOCKED, t("workflow.hint.download_first"))
        if download_blocked
        else (AVAILABLE, t("workflow.curated.transform_pending"))
    )
    base["evaluate"] = (
        (DONE, t("workflow.curated.evaluate_done"))
        if report_ready and outstanding == 0
        else (BLOCKED, t("workflow.hint.download_first"))
        if download_blocked
        else (AVAILABLE, t("workflow.curated.evaluate_pending", count=outstanding))
    )
    base["document"] = (
        (DONE, t("workflow.curated.document_done"))
        if inp.decision_committed
        else (AVAILABLE, t("workflow.curated.document_pending"))
    )

    done = {key for key, (state, _hint) in base.items() if state == DONE}
    current: str | None = None
    if inp.response_open and not inp.decision_committed:
        current = "document"
    else:
        for key in CURATED_ORDER:
            if key not in done:
                current = key
                break

    labels = {key: t(CURATED_LABEL_KEYS[key]) for key in CURATED_ORDER}
    if current is None:
        hint = t("workflow.hint.complete")
    else:
        hint = t("workflow.hint.next", label=labels[current])

    steps: list[Step] = []
    for key in CURATED_ORDER:
        state, step_hint = base[key]
        if key == current:
            state = CURRENT
        label = labels[key]
        steps.append(
            Step(
                key=key,
                label=label,
                state=state,
                hint=step_hint,
                accessible=t("workflow.accessible.step", label=label, state=state),
                badge=CURATED_BADGES[key],
            )
        )
    return Workflow(steps=tuple(steps), current=current, hint=hint)
