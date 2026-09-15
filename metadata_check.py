"""Metadata completeness checking against configurable requirement profiles.

Profiles:
- McMaster (default): derived from CurationLog.pdf + DepositorChecklist.pdf
  (McMaster Dataverse). Mandatory fields are marked ★ Required.
- Minimal: only the Dataverse core mandatory fields.

Each result: {field, requirement, value, status}
"""

import re
from typing import Any, Dict, List

import json as _json
from pathlib import Path as _Path

PROFILES: Dict[str, Dict[str, Any]] = {
    "McMaster": {
        "label": "McMaster — Curation Log + Depositor Checklist",
        "description": "Rules from CurationLog.pdf and DepositorChecklist.pdf (McMaster Dataverse)",
    },
    "Minimal": {
        "label": "Minimal — Dataverse core",
        "description": "Only Dataverse core mandatory fields (Title, Author, Contact, Description, Subject)",
    },
}

DEFAULT_PROFILE = "McMaster"

_FILE_NAME = "requirements_profiles.json"


def profiles_path() -> _Path:
    """Canonical location of the editable requirement profiles.

    Frozen exe: next to the executable (CWD is arbitrary there). Dev runs:
    the current working directory (repo root). One helper so the checker
    and the Requirements dialog always read/write the same file.
    """
    import sys

    if getattr(sys, "frozen", False):
        try:
            return _Path(sys.executable).parent / _FILE_NAME
        except Exception:
            pass
    return _Path(_FILE_NAME)


# Load custom profiles from file if present (written by Requirements dialog)
try:
    _profiles_path = profiles_path()
    if _profiles_path.exists():
        _loaded = _json.loads(_profiles_path.read_text(encoding="utf-8"))
        if isinstance(_loaded, dict):
            for k, v in _loaded.items():
                if k not in PROFILES:
                    PROFILES[k] = v
                else:
                    PROFILES[k].update(v)
        elif _loaded is not None:
            raise ValueError("profiles JSON must be an object")
except Exception as exc:
    try:
        from applog import get_app_log

        get_app_log().error(f"requirements profiles unreadable ({exc}) — using built-ins")
    except Exception:
        pass

ORCID_RE = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")


def _fields_for_block(metadata_blocks: Dict[str, Any], block_name: str) -> List[Dict[str, Any]]:
    return metadata_blocks.get(block_name, {}).get("fields", [])


def _field(metadata_blocks: Dict[str, Any], block_name: str, type_name: str) -> Any:
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
                if any(_nonempty(v.get("value") if isinstance(v, dict) else v) for v in item.values()):
                    return True
            elif _nonempty(item):
                return True
        return False
    if isinstance(value, dict):
        return any(_nonempty(v.get("value") if isinstance(v, dict) else v) for v in value.values())
    return True


def _display_value(value: Any, max_len: int = 120) -> str:
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
                v = item.get("dsDescriptionValue", {}).get("value", "") if isinstance(item.get("dsDescriptionValue"), dict) else ""
                if v:
                    vals.append(str(v))
            s = "; ".join(vals)
            if len(value) > 3:
                s += f" (+{len(value)-3} more)"
            return s[:max_len] or "—"
        parts = []
        for item in value[:3]:
            if isinstance(item, dict):
                # Try known subfields in priority order
                for k in ("value", "datasetContactName", "authorName", "publicationCitation", "title", "subject"):
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
                    for kk, vv in item.items():
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
            s += f" (+{len(value)-3} more)"
        return s[:max_len] or "—"
    if isinstance(value, dict):
        if "value" in value:
            return _display_value(value["value"], max_len)
        # license object: {name, uri}
        if "name" in value:
            return str(value["name"])[:max_len]
        return str(value)[:max_len]
    return str(value)[:max_len]


def _extract_orcid_value(metadata_blocks: Dict[str, Any]) -> str:
    authors = _field(metadata_blocks, "citation", "author") or []
    for author in authors if isinstance(authors, list) else [authors]:
        if isinstance(author, dict):
            id_val = author.get("authorIdentifier", {})
            scheme = author.get("authorIdentifierScheme", {})
            id_str = id_val.get("value", "") if isinstance(id_val, dict) else str(id_val or "")
            scheme_str = scheme.get("value", "") if isinstance(scheme, dict) else str(scheme or "")
            if "orcid" in str(scheme_str).lower() and id_str.strip():
                return id_str.strip()
    return ""


def _check_mcmaster(metadata: dict, blocks: Dict[str, Any], inventory: List[Dict[str, Any]] | None) -> List[Dict[str, Any]]:
    def has(block: str, name: str) -> bool:
        return _nonempty(_field(blocks, block, name))

    def val(block: str, name: str) -> str:
        return _display_value(_field(blocks, block, name))

    # License is in latestVersion.license, not in citation fields
    latest = metadata.get("latestVersion") or {}
    license_obj = latest.get("license") or metadata.get("license")
    license_ok = isinstance(license_obj, dict) and bool(license_obj.get("name"))
    license_val = license_obj.get("name", "") if isinstance(license_obj, dict) else _display_value(license_obj)

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
            path = (f.get("path") or f.get("label") or "").lower()
            if "readme" in path:
                readme_ok = True
                readme_val = f.get("path") or f.get("label") or "found"
                break
        if not readme_ok:
            readme_val = "No README file found"

    results: List[Dict[str, Any]] = []

    def add(field: str, requirement: str, value: str, ok: bool) -> None:
        results.append({"field": field, "requirement": requirement, "value": value or "—", "status": "complete" if ok else "incomplete"})

    add("Title", "McMaster — Required (Depositor Checklist: Basic Metadata; Curation Log: Full Citation)", val("citation", "title"), has("citation", "title"))
    # Description: special handling for dsDescriptionValue
    desc_raw = _field(blocks, "citation", "dsDescription")
    desc_val = _display_value(desc_raw)
    add("Description", "McMaster — Required (Curation Log: Full Citation; Checklist: Basic Metadata)", desc_val, has("citation", "dsDescription"))
    authors_ok = has("citation", "author") and all(
        _nonempty((a or {}).get("authorName", {})) for a in (_field(blocks, "citation", "author") or []) if isinstance(a, dict)
    )
    affil_ok = isinstance(_field(blocks, "citation", "author") or [], list) and all(
        _nonempty((a or {}).get("authorAffiliation", {})) for a in (_field(blocks, "citation", "author") or []) if isinstance(a, dict)
    )
    add("Author Name & Affiliation", "McMaster — Required (Curation Log: Full Citation)", val("citation", "author"), authors_ok and affil_ok)
    add("Dataset Contact", "McMaster — Required (Curation Log + Checklist)", val("citation", "datasetContact"), has("citation", "datasetContact"))
    add("Subject", "McMaster — Required (Checklist: Basic Metadata)", val("citation", "subject"), has("citation", "subject"))
    add("License", "McMaster — Required (Checklist: Data License)", license_val or "—", license_ok)
    # Split depositor and date
    add("Depositor", "McMaster — Required (Checklist: During Deposit)", val("citation", "depositor"), has("citation", "depositor"))
    add("Deposit Date", "McMaster — Required (Checklist: During Deposit)", val("citation", "dateOfDeposit"), has("citation", "dateOfDeposit"))
    # README
    add("README file", "McMaster — Required (Curation Log: Documentation; Checklist: Before Deposit)", readme_val, readme_ok)

    rel_pub = _field(blocks, "citation", "publication") or []
    rel_list = rel_pub if isinstance(rel_pub, list) else ([rel_pub] if rel_pub else [])
    has_pub = len(rel_list) > 0
    pub_complete = False
    pub_val = "—"
    pub_id_val = "—"
    pub_id_ok = False
    if has_pub and isinstance(rel_list[0], dict):
        first = rel_list[0]
        # Prefer citation/journal, fall back to ID for display
        cit = first.get("publicationCitation", {}).get("value", "") if isinstance(first.get("publicationCitation"), dict) else str(first.get("publicationCitation") or "")
        jour = first.get("journal", {}).get("value", "") if isinstance(first.get("journal"), dict) else ""
        id_val = first.get("publicationIDNumber", {}).get("value", "") if isinstance(first.get("publicationIDNumber"), dict) else ""
        if cit or jour:
            pub_val = f"{cit} — {jour}".strip(" —") if cit and jour else (cit or jour)
        elif id_val:
            pub_val = id_val
        else:
            pub_val = _display_value(first)
        title_ok = _nonempty(first.get("publicationCitation", {})) or _nonempty(first.get("title", {}))
        journal_ok = _nonempty(first.get("journal", {}))
        pub_complete = bool(title_ok and journal_ok)
        pub_id_val = id_val or "—"
        pub_id_ok = bool(id_val.strip())
    add("Related Publication (title + journal)", "McMaster — Required (Curation Log + Checklist: *Publication)", pub_val, pub_complete)
    add("Related Publication ID", "McMaster — Required (Curation Log: Pub ID)", pub_id_val, pub_id_ok)

    orcid_val = _extract_orcid_value(blocks)
    orcid_ok = bool(ORCID_RE.match(orcid_val)) if orcid_val else False
    add("ORCiD for authors", "McMaster — Recommended (Checklist: Researcher ID; Curation Log: optional)", orcid_val or "—", orcid_ok)

    time_ok = has("citation", "timePeriodCovered") or has("citation", "dateOfCollection")
    add("Time Period / Date of Collection", "McMaster — Recommended (Checklist: More Metadata — Time)", f"{val('citation','timePeriodCovered')} / {val('citation','dateOfCollection')}".strip(" /") or "—", time_ok)
    geo = _field(blocks, "geospatial", "geographicCoverage") or _field(blocks, "citation", "geographicCoverage")
    add("Geographic Coverage", "McMaster — Recommended (Checklist: More Metadata — Place)", _display_value(geo), _nonempty(geo))

    return results


def _check_minimal(metadata: dict, blocks: Dict[str, Any], inventory: List[Dict[str, Any]] | None) -> List[Dict[str, Any]]:
    def has(block: str, name: str) -> bool:
        return _nonempty(_field(blocks, block, name))

    def val(block: str, name: str) -> str:
        return _display_value(_field(blocks, block, name))

    results: List[Dict[str, Any]] = []
    for field, req in [
        ("title", "Minimal — Required: Title"),
        ("author", "Minimal — Required: Author"),
        ("datasetContact", "Minimal — Required: Contact"),
        ("dsDescription", "Minimal — Required: Description"),
        ("subject", "Minimal — Required: Subject"),
    ]:
        results.append({"field": field, "requirement": req, "value": val("citation", field), "status": "complete" if has("citation", field) else "incomplete"})
    return results


def check_metadata_completeness(metadata: dict, profile: str = DEFAULT_PROFILE, inventory: List[Dict[str, Any]] | None = None) -> List[dict]:
    """Deterministic completeness check for the chosen profile."""
    latest = metadata.get("latestVersion") or {}
    blocks = latest.get("metadataBlocks") or metadata.get("metadataBlocks") or {}
    if profile == "Minimal":
        return _check_minimal(metadata, blocks, inventory)
    return _check_mcmaster(metadata, blocks, inventory)


# Back-compat alias used by older code
def check_completeness(
    metadata: dict,
    profile: str = DEFAULT_PROFILE,
    inventory: List[Dict[str, Any]] | None = None,
) -> List[dict]:
    return check_metadata_completeness(metadata, profile, inventory)
