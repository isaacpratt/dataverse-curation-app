"""Access facts recorded on a crawled dataset row.

The dashboard's Access column only speaks when the server refused something:
a row that read fine carries no access fact at all. These helpers record
what the account could read (and why not) without dropping the row.
"""

from __future__ import annotations

from typing import Any

from curation.applog import get_app_log
from curation.client.constants import _VERSION_DRAFT, _VERSION_PUBLISHED
from curation.client.http import _error_message

#: Row facts about what the account could read. Deliberately facts, not
#: interface copy: the dashboard renders them through ui/assets/strings.json.
_ACCESS_STATE_READABLE = "readable"
_ACCESS_STATE_RESTRICTED = "restricted"
_ACCESS_STATE_METADATA_ONLY = "metadata_only"


def _set_access(
    ds: dict[str, Any],
    state: str,
    reason: str = "",
    detail: str = "",
    status: int = 0,
    version: str = "",
) -> None:
    """Record what the account could read for this dataset."""
    try:
        ds["access"] = {
            "state": str(state or ""),
            "reason": str(reason or ""),
            "detail": str(detail or ""),
            "status": int(status or 0),
            "version": str(version or ""),
        }
    except Exception:
        pass


def _mark_readable(ds: dict[str, Any], used_version: str, state: str = "") -> None:
    """Record which version of a dataset the account could read."""
    try:
        version = str(used_version or "")
        version_state = str(state or "").upper()
        if version == "unversioned":
            # The dataset read answers with the version the account may
            # see: the draft for a dataset under curation, the published
            # version otherwise.
            if version_state == "DRAFT":
                version = _VERSION_DRAFT
            elif version_state in ("RELEASED", "PUBLISHED"):
                version = _VERSION_PUBLISHED
        if version == "unversioned":
            # The dataset answered, but no version of it did. A
            # deaccessioned dataset has no published version at all — that
            # is a fact about the dataset, not about the account.
            deaccessioned = str(state or "").upper() == "DEACCESSIONED"
            _set_access(
                ds,
                _ACCESS_STATE_METADATA_ONLY,
                reason=("no_published_version" if deaccessioned else "no_readable_version"),
                detail=(
                    "the dataset is deaccessioned — it has no published version"
                    if deaccessioned
                    else "the dataset answered, but none of its versions did"
                ),
            )
        else:
            _set_access(ds, _ACCESS_STATE_READABLE, version=version)
    except Exception:
        pass


def _mark_restricted(ds: dict[str, Any], exc: BaseException) -> None:
    """Record that the server refused every version of this dataset."""
    try:
        resp = getattr(exc, "response", None)
        status = resp.status_code if resp is not None else 0
        code = str(getattr(exc, "refusal_code", "") or "")
        detail = str(getattr(exc, "refusal_detail", "") or "")
        if not detail and resp is not None:
            detail = _error_message(resp)
        _set_access(
            ds,
            _ACCESS_STATE_RESTRICTED,
            reason=code or "not_readable",
            detail=detail,
            status=int(status or 0),
        )
    except Exception:
        pass


def size_unavailable(ds: dict[str, Any]) -> bool:
    """Return True when no version of this dataset could be read.

    The size is not missing — it cannot be had (dv-zhf). The dashboard
    dims the Size cell's em dash for these rows; the Access column says
    why. A row that was read keeps its size, even when only some of its
    versions were refused.
    """
    access = ds.get("access")
    if not isinstance(access, dict):
        return False
    return str(access.get("state") or "") in (
        _ACCESS_STATE_RESTRICTED,
        _ACCESS_STATE_METADATA_ONLY,
    )


def _log_enrichment_refusal(ds: dict[str, Any], exc: BaseException) -> None:
    """Say in the Log page that a dataset's size could not be read.

    The refusal is the server's documented answer for a dataset outside
    the account's curation scope, so the line is EXPECTED (muted in the
    Log page), not an error. Without it, a batch that left rows thin is
    invisible after the fact.
    """
    try:
        resp = getattr(exc, "response", None)
        status = int(getattr(resp, "status_code", 0) or 0)
        code = str(getattr(exc, "refusal_code", "") or "") or "not_readable"
        pid = str(ds.get("persistent_id") or "")
        get_app_log().expected(
            f"Enrichment refused for {pid}: every version was refused "
            f"(HTTP {status}, {code}) — the size stays unavailable"
        )
    except Exception:
        pass
