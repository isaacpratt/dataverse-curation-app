"""Depositor follow-up tracking (dv-5eg) — pure logic, no Qt / no I/O.

When a curation decision asks for revisions the dataset enters a
"waiting on the depositor" state. This module holds the pieces that are
worth testing on their own: which decisions open a follow-up, how a
server ``lastUpdateTime`` compares against the decision timestamp
(timezone-tolerant), and what the queue should say.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# Decision wording that means "the depositor must act". Instance curation
# labels are free text, so match on substrings as well as the built-in
# generic label.
REVISION_HINTS = ("revision", "revise", "changes requested", "needs changes")

STATE_AWAITING = "awaiting_depositor"
STATE_UPDATED = "depositor_updated"


def is_revision_decision(decision: str, revision_label: str = "") -> bool:
    """Return True when ``decision`` asks the depositor for changes."""
    text = str(decision or "").strip().lower()
    if not text:
        return False
    label = str(revision_label or "").strip().lower()
    if label and text == label:
        return True
    return any(hint in text for hint in REVISION_HINTS)


def parse_ts(value: Any) -> datetime | None:
    """Parse an ISO timestamp to an aware UTC datetime; None when unusable.

    Accepts the shapes Dataverse returns (``2026-10-14T12:00:00Z``,
    ``...+00:00``) plus space-separated and naive forms (assumed UTC), so a
    comparison never raises on a stray format.
    """
    text = str(value or "").strip()
    if not text:
        return None
    candidate = text.replace("Z", "+00:00").replace("z", "+00:00")
    if "T" not in candidate and " " in candidate:
        candidate = candidate.replace(" ", "T", 1)
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def newer_than(last_update: Any, decision_ts: Any) -> bool:
    """Return True when ``last_update`` is strictly after ``decision_ts``.

    A missing or unparsable value on either side is not a change: the queue
    must never claim "depositor updated" on a tie or missing data.
    """
    left = parse_ts(last_update)
    right = parse_ts(decision_ts)
    if left is None or right is None:
        return False
    return left > right


def state_for(opened_at: Any, last_update: Any = None) -> str:
    """Derive the follow-up state: depositor_updated when the draft moved on."""
    return STATE_UPDATED if newer_than(last_update, opened_at) else STATE_AWAITING
