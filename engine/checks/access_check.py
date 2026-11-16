"""Dataset-level access restrictions: restricted and embargoed files.

Dataverse exposes access conditions on each file-version entry (and the
dataset's ``termsOfAccess`` on the version surface), but the format checks
only see staged files. This dataset-level check reads the inventory passed
through the runner context, names the restricted/embargoed files, and puts
the embargo date and terms of access in the finding so the review and the
response draft can show them.

Always emits one result per owned check_id, even when no inventory is
available (a staged-only/headless run) — as a skipped result, never a
silent pass.
"""

from pathlib import Path
from typing import Any, ClassVar

from engine.checks.base import Check, CheckResult

_MAX_LISTED = 10


def _path(entry: dict[str, Any]) -> str:
    return str(entry.get("path") or entry.get("label") or "")


def _text(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("value", "termsOfAccess", "text"):
            text = str(value.get(key) or "").strip()
            if text:
                return text
        return ""
    return str(value or "").strip()


def terms_of_access(metadata: dict[str, Any] | None) -> str:
    """Return the dataset's termsOfAccess text (version surface, then top level)."""
    try:
        latest = (metadata or {}).get("latestVersion") or {}
        toa = latest.get("termsOfAccess") or (metadata or {}).get("termsOfAccess") or ""
        return _text(toa)
    except Exception:
        return ""


def collect_restrictions(
    inventory: list[dict[str, Any]] | None,
) -> tuple[list[str], list[dict[str, str]]]:
    """Return (restricted paths, [{path, date}] for embargoed files)."""
    restricted: list[str] = []
    embargoed: list[dict[str, str]] = []
    for entry in inventory or []:
        if not isinstance(entry, dict):
            continue
        path = _path(entry)
        if not path:
            continue
        if entry.get("restricted"):
            restricted.append(path)
        embargo = str(entry.get("embargo_date") or "").strip()[:10]
        if embargo:
            embargoed.append({"path": path, "date": embargo})
    return restricted, embargoed


def _terms_suffix(terms: str) -> str:
    return f" · Terms of access: {terms}" if terms else " · Terms of access: not set"


def _join_listed(items: list[str]) -> str:
    shown = items[:_MAX_LISTED]
    text = ", ".join(shown)
    if len(items) > _MAX_LISTED:
        text += f" (+{len(items) - _MAX_LISTED} more)"
    return text


def access_conditions(
    metadata: dict[str, Any] | None,
    inventory: list[dict[str, Any]] | None,
) -> tuple[bool, str]:
    """(ok, display) for the review row.

    Informational unless access is restricted: restricted/embargoed files
    need terms of access on file, so an empty termsOfAccess is incomplete.
    """
    if inventory is None:
        return True, "— (load file list to check)"
    restricted, embargoed = collect_restrictions(inventory)
    terms = terms_of_access(metadata)
    parts: list[str] = []
    if restricted:
        parts.append(f"{len(restricted)} restricted file(s): {_join_listed(restricted)}")
    if embargoed:
        shown = ", ".join(f"{e['path']} (until {e['date']})" for e in embargoed[:_MAX_LISTED])
        if len(embargoed) > _MAX_LISTED:
            shown += f" (+{len(embargoed) - _MAX_LISTED} more)"
        parts.append(f"{len(embargoed)} embargoed file(s): {shown}")
    if terms:
        parts.append(f"Terms of access: {terms}")
    elif restricted or embargoed:
        parts.append("Terms of access: not set")
    if not parts:
        return True, "No restricted or embargoed files"
    ok = not (restricted or embargoed) or bool(terms)
    return ok, " · ".join(parts)


class AccessCheck(Check):
    """Access restrictions — restricted and embargoed files (dataset-level)."""

    check_id = "inventory.access"
    extensions: ClassVar[set[str]] = set()

    def run(self, files: list[Path]) -> list[CheckResult]:
        return self.run_dataset(files, None)

    def run_dataset(
        self, files: list[Path], context: dict[str, Any] | None = None
    ) -> list[CheckResult]:
        context = context or {}
        inventory = context.get("inventory")
        metadata = context.get("metadata")

        if inventory is None:
            message = "access metadata skipped — no Dataverse inventory (staged-only run)"
            skipped = {"skipped": True, "reason": "inventory not loaded"}
            return [
                CheckResult(
                    check_id="inventory.restricted_files",
                    level="warning",
                    passed=True,
                    message=message,
                    details=dict(skipped),
                ),
                CheckResult(
                    check_id="inventory.embargoed_files",
                    level="warning",
                    passed=True,
                    message=message,
                    details=dict(skipped),
                ),
            ]

        restricted, embargoed = collect_restrictions(inventory)
        terms = terms_of_access(metadata)
        checked = len([e for e in inventory if isinstance(e, dict)])

        if restricted:
            restricted_result = CheckResult(
                check_id="inventory.restricted_files",
                level="warning",
                passed=False,
                message=(
                    f"{len(restricted)} restricted file(s): "
                    f"{_join_listed(restricted)}{_terms_suffix(terms)}"
                ),
                details={
                    "count": len(restricted),
                    "files": restricted[:_MAX_LISTED],
                    "terms_of_access": terms,
                },
            )
        else:
            restricted_result = CheckResult(
                check_id="inventory.restricted_files",
                level="info",
                passed=True,
                message=f"No restricted files ({checked} file(s) checked)",
                details={"count": 0, "files_checked": checked},
            )

        if embargoed:
            shown = ", ".join(f"{e['path']} (until {e['date']})" for e in embargoed[:_MAX_LISTED])
            if len(embargoed) > _MAX_LISTED:
                shown += f" (+{len(embargoed) - _MAX_LISTED} more)"
            embargoed_result = CheckResult(
                check_id="inventory.embargoed_files",
                level="warning",
                passed=False,
                message=(f"{len(embargoed)} embargoed file(s): {shown}{_terms_suffix(terms)}"),
                details={
                    "count": len(embargoed),
                    "files": [e["path"] for e in embargoed[:_MAX_LISTED]],
                    "embargoes": embargoed[:_MAX_LISTED],
                    "dates": sorted({e["date"] for e in embargoed}),
                    "terms_of_access": terms,
                },
            )
        else:
            embargoed_result = CheckResult(
                check_id="inventory.embargoed_files",
                level="info",
                passed=True,
                message=f"No embargoed files ({checked} file(s) checked)",
                details={"count": 0, "files_checked": checked},
            )

        return [restricted_result, embargoed_result]
