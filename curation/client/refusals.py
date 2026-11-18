"""Refusal classification for the Native API.

A 4xx answer is not always a bug: a dataset may have no published version, a
draft may be outside this account's curation scope, a collection may not
expose curation labels at all. This module turns such an answer into a
machine code plus a plain explanation, so the app can say what happened
instead of showing a stack trace.
"""

from __future__ import annotations

from typing import Any

from curation.client.constants import (
    _REFUSAL_COMPARE,
    _REFUSAL_VERSIONS,
    _VERSION_DRAFT,
)
from curation.client.parsers import is_draft_dataset


def _refusal(path: str, status: int, body: str = "") -> tuple[str, str]:  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
    """Classify a 4xx answer: (machine code, explanation) or ("", "") when unexpected."""
    p = str(path or "").lower()
    text = str(body or "").lower()
    if status not in (400, 401, 403, 404):
        return "", ""
    is_versions = _REFUSAL_VERSIONS in p
    is_draft = "/versions/:draft" in p
    is_published = "/versions/:latest" in p
    is_compare = _REFUSAL_COMPARE in p
    is_curation = "curationstatus" in p
    is_labels = "allowedcurationlabels" in p
    # The server's own words disambiguate: "not found" means the version
    # does not exist, "not permitted" means this account may not read it.
    says_missing = "not found" in text or "does not exist" in text

    if status in (401, 403):
        if says_missing and is_versions:
            # The version is gone (not hidden): answer as the 404 case.
            if is_draft:
                return (
                    "no_draft_version",
                    "the dataset has no draft version — the author is not working on an update",
                )
            return (
                "no_published_version",
                "the dataset has no published version — deaccessioned versions are "
                "excluded from the version endpoints by default",
            )
        if is_compare:
            return (
                "versions_not_readable",
                "this account may not compare this dataset's versions",
            )
        if is_draft or (is_versions and not is_published):
            return (
                "draft_not_readable",
                "this account may not read the draft version of this dataset "
                "— Dataverse grants draft access only inside the dataset's "
                "curation scope",
            )
        if is_published:
            return (
                "version_not_readable",
                "this account may not read this dataset's published version",
            )
        if is_curation:
            return (
                "not_under_curation",
                "curation status is readable only for datasets under curation "
                "and for accounts in their curation scope",
            )
        if is_labels:
            return (
                "labels_not_readable",
                "this account is not allowed to read curation labels for this collection",
            )
        return "", ""

    if status == 400:
        # A bad request is our mistake, not the server's answer.
        return "", ""

    # 404
    if is_compare:
        return (
            "no_versions_to_compare",
            "there is no published/draft version pair to compare",
        )
    if is_draft:
        return (
            "no_draft_version",
            "the dataset has no draft version — the author is not working on an update",
        )
    if is_published:
        return (
            "no_published_version",
            "the dataset has no published version — deaccessioned versions are "
            "excluded from the version endpoints by default",
        )
    if is_versions:
        return ("no_visible_versions", "the dataset has no visible versions")
    if is_curation:
        return ("not_under_curation", "the dataset is not under curation — it has no draft")
    if is_labels:
        return ("labels_unavailable", "this collection does not expose curation labels")
    if "listcurationstates" in p:
        return ("curation_states_unavailable", "this instance does not expose curation states")
    if "timestamps" in p:
        return ("timestamps_unavailable", "this instance does not expose dataset timestamps")
    return "", ""


def expected_api_reason(path: str, status: int, body: str = "") -> str:
    """Why a refusal from this endpoint is the documented answer ("" = a bug)."""
    try:
        return _refusal(path, status, body)[1]
    except Exception:
        return ""


def refusal_code(path: str, status: int, body: str = "") -> str:
    """Machine code for an expected refusal ("" when the answer is unexpected)."""
    try:
        return _refusal(path, status, body)[0]
    except Exception:
        return ""


def version_probe_order(ds: Any) -> list[str]:
    """Which version specifiers to probe for a crawl row (empty = read the dataset once).

    The Native API's dataset read returns the version the account may see:
    the draft for a dataset under curation, the published version for a
    published dataset, and no version at all for a deaccessioned one. One
    call therefore answers what the dashboard needs.

    A version-specific probe is only worth sending when the search payload
    says a draft exists — a :draft probe on a published dataset is refused
    every time ("not permitted"), and :latest / :latest-published are 404
    for a deaccessioned dataset.
    """
    try:
        if not isinstance(ds, dict):
            return []
        if is_draft_dataset(ds):
            return [_VERSION_DRAFT]
        return []
    except Exception:
        return []


def probe_skip_reason(ds: Any) -> str:
    """Why a version probe was skipped for this row ("" when nothing was skipped)."""
    try:
        if not isinstance(ds, dict):
            return ""
        if is_draft_dataset(ds):
            return ""
        state = str(ds.get("state") or "").upper()
        if state == "DEACCESSIONED":
            return (
                "the search payload lists this dataset as deaccessioned — its "
                "record answers, but it has no version to ask for"
            )
        return (
            "the search payload lists this dataset as published with no draft — "
            "the dataset read answers with the published version in one call"
        )
    except Exception:
        return ""
