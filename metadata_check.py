"""Metadata completeness checking against configurable requirement profiles.

Profiles:
- McMaster (default): derived from the McMaster Curation Log +
  Depositor Checklist (source PDFs retired 2026-10-07; the rules are
  maintained in code). Mandatory fields are marked ★ Required.
- Minimal: only the Dataverse core mandatory fields.

Each result: {field, requirement, value, status}
"""

import json as _json
import re
from pathlib import Path
from typing import Any

PROFILES: dict[str, dict[str, Any]] = {
    "McMaster": {
        "label": "McMaster — Curation Log + Depositor Checklist",
        "description": "Rules from the McMaster Curation Log and Depositor Checklist (McMaster Dataverse)",
        "ruleset": "mcmaster-default",
    },
    "Minimal": {
        "label": "Minimal — Dataverse core",
        "description": "Only Dataverse core mandatory fields (Title, Author, Contact, Description, Subject)",
        "ruleset": "minimal",
    },
}

DEFAULT_PROFILE = "McMaster"

# Legacy profile key -> v2 ruleset key (custom rulesets use their own key).
PROFILE_TO_RULESET = {"McMaster": "mcmaster-default", "Minimal": "minimal"}

_FILE_NAME = "requirements_profiles.json"


def profiles_path() -> Path:
    """Canonical location of the editable requirement profiles.

    Frozen exe: next to the executable (CWD is arbitrary there), falling
    back one level above — the folder holding the build, where onefile-era
    launches kept the file — so an exe inside its own onedir subfolder
    still finds an existing profiles file; with none anywhere, resolve
    above the build folder so a fresh write survives rebuilds (PyInstaller
    wipes its output folder). Dev runs: the current working directory
    (repo root). One helper so the checker and the Requirements dialog
    always read/write the same file.
    """
    import sys

    if getattr(sys, "frozen", False):
        try:
            exe_dir = Path(sys.executable).parent
            for candidate in (exe_dir / _FILE_NAME, exe_dir.parent / _FILE_NAME):
                if candidate.exists():
                    return candidate
            return exe_dir.parent / _FILE_NAME
        except Exception:
            pass
    return Path(_FILE_NAME)


# Keys PROFILES gained from v2 rulesets (tracked so deleted rulesets can be
# removed again on refresh, not just added).
_V2_PROFILE_KEYS: set[str] = set()


# Load custom profiles from file if present (written by Requirements dialog)
# Supports both the legacy flat shape and the v2 {version, rulesets} shape
# (written by the Review-configuration page). v2 rulesets appear as extra
# PROFILES entries so the dataset combo lists them.
def _register_rulesets_in_profiles() -> None:
    try:
        import review_rules as _rr

        pool = _rr.load_rulesets()
        for _key, _rs in pool.items():
            if _key in ("mcmaster-default", "minimal"):
                continue
            PROFILES[_key] = {
                "label": str(_rs.get("label") or _key),
                "description": str(_rs.get("description") or ""),
                "ruleset": _key,
            }
            _V2_PROFILE_KEYS.add(_key)
        # Drop customs that no longer exist (deleted in Review configuration).
        for _stale in [k for k in _V2_PROFILE_KEYS if k not in pool]:
            PROFILES.pop(_stale, None)
            _V2_PROFILE_KEYS.discard(_stale)
    except Exception:
        pass


try:
    _profiles_path = profiles_path()
    if _profiles_path.exists():
        _loaded = _json.loads(_profiles_path.read_text(encoding="utf-8"))
        if (
            isinstance(_loaded, dict)
            and _loaded.get("version") == 2
            and isinstance(_loaded.get("rulesets"), dict)
        ):
            pass  # v2 file: profiles come from review_rules (see below)
        elif isinstance(_loaded, dict):
            for k, v in _loaded.items():
                if k in ("version", "rulesets"):
                    continue
                if not isinstance(k, str) or not isinstance(v, dict):
                    # Skip malformed entries without mutating built-ins.
                    continue
                if k not in PROFILES:
                    PROFILES[k] = dict(v)
                else:
                    PROFILES[k] = {**PROFILES[k], **v}
        elif _loaded is not None:
            raise ValueError("profiles JSON must be an object")
except Exception as exc:
    try:
        from applog import get_app_log

        get_app_log().error(f"requirements profiles unreadable ({exc}) — using built-ins")
    except Exception:
        pass

_register_rulesets_in_profiles()

ORCID_RE = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")


def _fields_for_block(metadata_blocks: dict[str, Any], block_name: str) -> list[dict[str, Any]]:
    block = metadata_blocks.get(block_name, {})
    fields: list[dict[str, Any]] = block.get("fields", []) if isinstance(block, dict) else []
    return fields


def _field(metadata_blocks: dict[str, Any], block_name: str, type_name: str) -> Any:
    for field in _fields_for_block(metadata_blocks, block_name):
        if field.get("typeName") == type_name:
            return field.get("value")
    return None


def _nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                if any(
                    _nonempty(v.get("value") if isinstance(v, dict) else v) for v in item.values()
                ):
                    return True
            elif _nonempty(item):
                return True
        return False
    if isinstance(value, dict):
        return any(_nonempty(v.get("value") if isinstance(v, dict) else v) for v in value.values())
    return True


def _display_value(value: Any, max_len: int = 120) -> str:  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
    if value is None:
        return "—"
    if isinstance(value, str):
        s = value.strip()
        return (s[:max_len] + "…") if len(s) > max_len else s or "—"
    if isinstance(value, list):
        # Special handling for known compound types
        # dsDescription: list of {dsDescriptionValue: {value: "req"}}
        if value and isinstance(value[0], dict) and "dsDescriptionValue" in value[0]:
            vals = []
            for item in value[:3]:
                v = (
                    item.get("dsDescriptionValue", {}).get("value", "")
                    if isinstance(item.get("dsDescriptionValue"), dict)
                    else ""
                )
                if v:
                    vals.append(str(v))
            s = "; ".join(vals)
            if len(value) > 3:
                s += f" (+{len(value) - 3} more)"
            return s[:max_len] or "—"
        parts = []
        for item in value[:3]:
            if isinstance(item, dict):
                # Try known subfields in priority order
                for k in (
                    "value",
                    "datasetContactName",
                    "authorName",
                    "publicationCitation",
                    "title",
                    "subject",
                ):
                    v = item.get(k)
                    if isinstance(v, dict) and "value" in v:
                        parts.append(str(v["value"]))
                        break
                    elif isinstance(v, str) and v.strip():
                        parts.append(v.strip())
                        break
                else:
                    # Fallback: join primitive sub-values
                    sub_vals = []
                    for _kk, vv in item.items():
                        if isinstance(vv, dict) and vv.get("value"):
                            sub_vals.append(str(vv["value"]))
                        elif isinstance(vv, str) and vv.strip():
                            sub_vals.append(vv.strip())
                    if sub_vals:
                        parts.append("; ".join(sub_vals))
            elif isinstance(item, str):
                parts.append(item)
        s = "; ".join(parts)
        if len(value) > 3:
            s += f" (+{len(value) - 3} more)"
        return s[:max_len] or "—"
    if isinstance(value, dict):
        if "value" in value:
            return _display_value(value["value"], max_len)
        # license object: {name, uri}
        if "name" in value:
            return str(value["name"])[:max_len]
        return str(value)[:max_len]
    return str(value)[:max_len]


def _extract_orcid_value(metadata_blocks: dict[str, Any]) -> str:
    authors = _field(metadata_blocks, "citation", "author") or []
    seq = authors if isinstance(authors, list) else [authors]
    fallback = ""
    for author in seq:
        if not isinstance(author, dict):
            continue
        id_val = author.get("authorIdentifier", {})
        scheme = author.get("authorIdentifierScheme", {})
        id_str = id_val.get("value", "") if isinstance(id_val, dict) else str(id_val or "")
        scheme_str = scheme.get("value", "") if isinstance(scheme, dict) else str(scheme or "")
        if "orcid" in str(scheme_str).lower() and id_str.strip():
            cleaned = id_str.strip()
            # Prefer a valid ORCID; keep first found as fallback.
            if ORCID_RE.match(cleaned):
                return cleaned
            fallback = fallback or cleaned
    return fallback


def _check_mcmaster(  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
    metadata: dict[str, Any], blocks: dict[str, Any], inventory: list[Any] | None
) -> list[dict[str, Any]]:
    def has(block: str, name: str) -> bool:
        return _nonempty(_field(blocks, block, name))

    def val(block: str, name: str) -> str:
        return _display_value(_field(blocks, block, name))

    # License is in latestVersion.license, not in citation fields
    latest = metadata.get("latestVersion") or {}
    license_obj = latest.get("license") or metadata.get("license")
    license_ok = isinstance(license_obj, dict) and bool(license_obj.get("name"))
    license_val = (
        license_obj.get("name", "")
        if isinstance(license_obj, dict)
        else _display_value(license_obj)
    )

    # README presence from file inventory.
    # inventory=None → file list not loaded yet; inventory==[] → dataset truly has no files.
    readme_ok = False
    readme_val = "—"
    if inventory is None:
        readme_val = "— (load file list to check)"
    elif len(inventory) == 0:
        readme_val = "No files in dataset — README not applicable"
    else:
        for f in inventory:
            if not isinstance(f, dict):
                continue
            raw_path = str(f.get("path") or f.get("label") or "")
            base = Path(raw_path).name.lower()
            # Match README as a basename (readme, readme.md/txt, readme_*),
            # not any substring (avoids myreadme_data.csv false positives).
            if base == "readme" or base.startswith(("readme.", "readme_", "readme-")):
                readme_ok = True
                readme_val = f.get("path") or f.get("label") or "found"
                break
        if not readme_ok:
            readme_val = "No README file found"

    results: list[dict[str, Any]] = []

    def add(field: str, requirement: str, value: str, ok: bool) -> None:
        results.append(
            {
                "field": field,
                "requirement": requirement,
                "value": value or "—",
                "status": "complete" if ok else "incomplete",
            }
        )

    add(
        "Title",
        "McMaster — Required (Depositor Checklist: Basic Metadata; Curation Log: Full Citation)",
        val("citation", "title"),
        has("citation", "title"),
    )
    # Description: special handling for dsDescriptionValue
    desc_raw = _field(blocks, "citation", "dsDescription")
    desc_val = _display_value(desc_raw)
    add(
        "Description",
        "McMaster — Required (Curation Log: Full Citation; Checklist: Basic Metadata)",
        desc_val,
        has("citation", "dsDescription"),
    )
    _authors_raw = _field(blocks, "citation", "author") or []
    _authors = (
        [a for a in _authors_raw if isinstance(a, dict)] if isinstance(_authors_raw, list) else []
    )
    authors_ok = (
        has("citation", "author")
        and bool(_authors)
        and all(_nonempty((a or {}).get("authorName", {})) for a in _authors)
    )
    # Affiliation: require every listed author to carry one (curation log
    # asks for full citation). Report which authors are missing it.
    _missing_affil = [
        str(
            (a.get("authorName", {}) or {}).get("value", "")
            if isinstance(a.get("authorName", {}), dict)
            else a.get("authorName", "") or f"author {i + 1}"
        )
        for i, a in enumerate(_authors)
        if not _nonempty((a or {}).get("authorAffiliation", {}))
    ]
    affil_ok = bool(_authors) and not _missing_affil
    _author_val = val("citation", "author")
    if _missing_affil:
        _author_val = (
            (_author_val + f" [missing affiliation: {', '.join(_missing_affil[:3])}]"[:200])
            if _author_val != "—"
            else f"missing affiliation: {', '.join(_missing_affil[:3])}"
        )
    add(
        "Author Name & Affiliation",
        "McMaster — Required (Curation Log: Full Citation)",
        _author_val,
        authors_ok and affil_ok,
    )
    add(
        "Dataset Contact",
        "McMaster — Required (Curation Log + Checklist)",
        val("citation", "datasetContact"),
        has("citation", "datasetContact"),
    )
    add(
        "Subject",
        "McMaster — Required (Checklist: Basic Metadata)",
        val("citation", "subject"),
        has("citation", "subject"),
    )
    add("License", "McMaster — Required (Checklist: Data License)", license_val or "—", license_ok)
    # Split depositor and date
    add(
        "Depositor",
        "McMaster — Required (Checklist: During Deposit)",
        val("citation", "depositor"),
        has("citation", "depositor"),
    )
    add(
        "Deposit Date",
        "McMaster — Required (Checklist: During Deposit)",
        val("citation", "dateOfDeposit"),
        has("citation", "dateOfDeposit"),
    )
    # README
    add(
        "README file",
        "McMaster — Required (Curation Log: Documentation; Checklist: Before Deposit)",
        readme_val,
        readme_ok,
    )

    rel_pub = _field(blocks, "citation", "publication") or []
    rel_list = rel_pub if isinstance(rel_pub, list) else ([rel_pub] if rel_pub else [])
    rel_list = [r for r in rel_list if isinstance(r, dict)]
    has_pub = len(rel_list) > 0
    pub_complete = False
    pub_val = "—"
    pub_id_val = "—"
    pub_id_ok = False
    if has_pub:
        # Pass when ANY related publication is complete (not just first).
        displays: list[str] = []
        for entry in rel_list:
            cit = (
                entry.get("publicationCitation", {}).get("value", "")
                if isinstance(entry.get("publicationCitation"), dict)
                else str(entry.get("publicationCitation") or "")
            )
            jour = (
                entry.get("journal", {}).get("value", "")
                if isinstance(entry.get("journal"), dict)
                else ""
            )
            id_val = (
                entry.get("publicationIDNumber", {}).get("value", "")
                if isinstance(entry.get("publicationIDNumber"), dict)
                else str(entry.get("publicationIDNumber") or "")
            )
            if cit or jour:
                displays.append(f"{cit} — {jour}".strip(" —") if cit and jour else (cit or jour))
            elif id_val:
                displays.append(id_val)
            else:
                displays.append(_display_value(entry))
            title_ok = _nonempty(entry.get("publicationCitation", {})) or _nonempty(
                entry.get("title", {})
            )
            journal_ok = _nonempty(entry.get("journal", {}))
            if title_ok and journal_ok:
                pub_complete = True
            if id_val and str(id_val).strip():
                pub_id_ok = True
                if pub_id_val == "—":
                    pub_id_val = str(id_val)
        pub_val = displays[0] if displays else "—"
        if len(displays) > 1:
            pub_val += f" (+{len(displays) - 1} more)"
    add(
        "Related Publication (title + journal)",
        "McMaster — Required (Curation Log + Checklist: *Publication)",
        pub_val,
        pub_complete,
    )
    add(
        "Related Publication ID",
        "McMaster — Required (Curation Log: Pub ID)",
        pub_id_val,
        pub_id_ok,
    )

    orcid_val = _extract_orcid_value(blocks)
    orcid_ok = bool(ORCID_RE.match(orcid_val)) if orcid_val else False
    # Per-author ORCID (matches review_rules orcid handler): every author
    # must carry a valid ORCID; display mirrors the rule engine (first valid
    # IDs + missing names, or "—" when none found).
    _orcid_authors = _field(blocks, "citation", "author") or []
    _orcid_list = (
        [a for a in _orcid_authors if isinstance(a, dict)]
        if isinstance(_orcid_authors, list)
        else []
    )
    _orcid_found: list[str] = []
    _orcid_missing: list[str] = []
    for _i, _oa in enumerate(_orcid_list):
        _on = (
            str(
                (_oa.get("authorName") or {}).get("value", "")
                if isinstance(_oa.get("authorName"), dict)
                else _oa.get("authorName") or ""
            ).strip()
            or f"author {_i + 1}"
        )
        _oid = _oa.get("authorIdentifier", {})
        _osch = _oa.get("authorIdentifierScheme", {})
        _oid_s = _oid.get("value", "") if isinstance(_oid, dict) else str(_oid or "")
        _osch_s = _osch.get("value", "") if isinstance(_osch, dict) else str(_osch or "")
        if "orcid" in str(_osch_s).lower() and _oid_s.strip() and ORCID_RE.match(_oid_s.strip()):
            _orcid_found.append(f"{_on}: {_oid_s.strip()}")
        else:
            _orcid_missing.append(_on)
    if _orcid_list:
        orcid_ok = not _orcid_missing
        if _orcid_found:
            orcid_val = "; ".join(_orcid_found[:3])
            if len(_orcid_found) > 3:
                orcid_val += f" (+{len(_orcid_found) - 3} more)"
            if _orcid_missing:
                orcid_val += f" [missing: {', '.join(_orcid_missing[:3])}]"
        else:
            orcid_val = ""
    add(
        "ORCiD for authors",
        "McMaster — Recommended (Checklist: Researcher ID; Curation Log: optional)",
        orcid_val or "—",
        orcid_ok,
    )

    # Author count (optional): mirrors the review_rules author_count handler.
    _raw_authors = _field(blocks, "citation", "author") or []
    _author_list = (
        [a for a in _raw_authors if isinstance(a, dict)] if isinstance(_raw_authors, list) else []
    )
    _n_auth = len(_author_list)
    _auth_names = []
    for _a in _author_list[:3]:
        _nm = _a.get("authorName", {})
        _auth_names.append(
            str(_nm.get("value", "") if isinstance(_nm, dict) else _nm or "").strip()
        )
    _auth_names = [x for x in _auth_names if x]
    if _n_auth <= 3:
        _count_val = f"{_n_auth} author(s)" + (f": {'; '.join(_auth_names)}" if _auth_names else "")
    else:
        _count_val = (
            f"{_n_auth} authors: {'; '.join(_auth_names)} (+{_n_auth - len(_auth_names)} more)"
        )
    add(
        "Author count",
        "McMaster — Recommended (check the number of authors)",
        _count_val or "—",
        _n_auth > 0,
    )

    # License + Terms of Use / Access (optional): latestVersion surface.
    _tou = latest.get("termsOfUse") or metadata.get("termsOfUse") or ""
    _toa = latest.get("termsOfAccess") or metadata.get("termsOfAccess") or ""
    _tou_s = _tou.get("value", "") if isinstance(_tou, dict) else str(_tou or "")
    _toa_s = _toa.get("value", "") if isinstance(_toa, dict) else str(_toa or "")
    _lt_parts = [p for p in (license_val, _tou_s, _toa_s) if p]
    _lt_val = " · ".join(_lt_parts) if _lt_parts else "—"
    add(
        "License and Terms of Use",
        "McMaster — Recommended (Checklist: Data License)",
        _lt_val,
        bool(license_val),
    )

    # Access restrictions / embargo (same handler as the ruleset engine so
    # the legacy fallback and the default ruleset stay in parity).
    from engine.checks.access_check import access_conditions

    _access_ok, _access_val = access_conditions(metadata, inventory)
    add(
        "Access, Embargo & Terms of Access",
        "McMaster — Recommended (Checklist: Data License / Access)",
        _access_val,
        _access_ok,
    )

    time_ok = has("citation", "timePeriodCovered") or has("citation", "dateOfCollection")
    add(
        "Time Period / Date of Collection",
        "McMaster — Recommended (Checklist: More Metadata — Time)",
        f"{val('citation', 'timePeriodCovered')} / {val('citation', 'dateOfCollection')}".strip(
            " /"
        )
        or "—",
        time_ok,
    )
    geo = _field(blocks, "geospatial", "geographicCoverage") or _field(
        blocks, "citation", "geographicCoverage"
    )
    add(
        "Geographic Coverage",
        "McMaster — Recommended (Checklist: More Metadata — Place)",
        _display_value(geo),
        _nonempty(geo),
    )

    return results


def _check_minimal(
    metadata: dict[str, Any], blocks: dict[str, Any], inventory: list[Any] | None
) -> list[dict[str, Any]]:
    def has(block: str, name: str) -> bool:
        return _nonempty(_field(blocks, block, name))

    def val(block: str, name: str) -> str:
        return _display_value(_field(blocks, block, name))

    results: list[dict[str, Any]] = []
    for field, req in [
        ("title", "Minimal — Required: Title"),
        ("author", "Minimal — Required: Author"),
        ("datasetContact", "Minimal — Required: Contact"),
        ("dsDescription", "Minimal — Required: Description"),
        ("subject", "Minimal — Required: Subject"),
    ]:
        results.append(
            {
                "field": field,
                "requirement": req,
                "value": val("citation", field),
                "status": "complete" if has("citation", field) else "incomplete",
            }
        )
    return results


def check_metadata_completeness(
    metadata: dict[str, Any],
    profile: str = DEFAULT_PROFILE,
    inventory: list[dict[str, Any]] | None = None,
    staged_dir: Any = None,
) -> list[dict[str, Any]]:
    """Deterministic completeness check for the chosen profile/ruleset.

    Profiles `McMaster`/`Minimal` and any custom v2 ruleset key all evaluate
    through the programmatic rule engine, so the Review-configuration page
    controls the rows. Legacy hard-coded checks remain as the fallback when
    the rule engine is unavailable.
    """
    try:
        import review_rules as _rr

        pool = _rr.load_rulesets()
        key = PROFILE_TO_RULESET.get(profile, profile)
        if key in pool or profile in ("McMaster", "Minimal"):
            ruleset = _rr.get_ruleset(key, pool)
            evaluated = _rr.evaluate_ruleset(metadata or {}, ruleset, inventory, staged_dir)
            # Strip engine-only keys for the legacy {field, requirement,
            # value, status} contract (callers that need rule ids use
            # check_with_ruleset below).
            return [
                {
                    "field": r["field"],
                    "requirement": r["requirement"],
                    "value": r.get("value", "—"),
                    "status": r["status"],
                }
                for r in evaluated
            ]
    except Exception as exc:
        from applog import get_app_log

        get_app_log().error(
            f"ruleset engine failed for profile={profile!r} ({exc}); using legacy fallback"
        )
    latest = metadata.get("latestVersion") or {}
    blocks = latest.get("metadataBlocks") or metadata.get("metadataBlocks") or {}
    if profile == "Minimal":
        return _check_minimal(metadata, blocks, inventory)
    return _check_mcmaster(metadata, blocks, inventory)


def check_with_ruleset(
    metadata: dict[str, Any],
    ruleset_key: str = "mcmaster-default",
    inventory: list[dict[str, Any]] | None = None,
    staged_dir: Any = None,
    rulesets: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Full rule evaluation (keeps rule_id/level/pending for the Response pane)."""
    import review_rules as _rr

    pool = rulesets if isinstance(rulesets, dict) else _rr.load_rulesets()
    # get_ruleset resolves legacy profile names ("McMaster"/"Minimal") and
    # falls back to the default for unknown keys.
    ruleset = _rr.get_ruleset(ruleset_key, pool)
    return _rr.evaluate_ruleset(metadata or {}, ruleset, inventory, staged_dir), ruleset


def refresh_profiles_from_rulesets() -> None:
    """Re-list custom rulesets in PROFILES (call after saving rules)."""
    try:
        _register_rulesets_in_profiles()
    except Exception:
        pass


# Back-compat alias used by older code
def check_completeness(
    metadata: dict[str, Any],
    profile: str = DEFAULT_PROFILE,
    inventory: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Citation-block completeness against a McMaster/Minimal profile."""
    return check_metadata_completeness(metadata, profile, inventory)
