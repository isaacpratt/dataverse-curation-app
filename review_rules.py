"""Versioned review rulesets: programmatic metadata completeness + response templates.

Schema (requirements_profiles.json v2):
{
  "version": 2,
  "rulesets": {
    "<key>": {
      "label": str, "description": str,
      "dataverses": ["*"] or [base_url, ...],
      "field_rules": [
        {"block": "citation", "field": "title", "label": "Title",
         "level": "required|optional|unchecked",
         "requirement": "human text", "handler": "nonempty|...",
         "response_template": "..."}
      ],
      "content_rules": [
        {"id": "readme-present", "label": "README file",
         "level": "required|optional",
         "requirement": "human text",
         "scope": ["filenames", "metadata", "file-content"],
         "match": "filename-glob|substring|regex",
         "pattern": "readme*",
         "case_sensitive": false,
         "response_template": "..."}
      ],
      "filecheck_templates": {"<check_id>": "...", "*": "..."},
      "response_header": "...", "response_footer": "..."
    }
  }
}

Built-ins (mcmaster-default, minimal) reproduce the legacy hard-coded
McMaster/Minimal checks exactly (same labels + requirement strings), so a
fresh install behaves identically until the curator edits rules.
"""

from __future__ import annotations

import fnmatch
import json as _json
import re
from pathlib import Path as _Path
from typing import Any

RULESETS_VERSION = 2

# Memo for load_rulesets(): {"sig": (path, mtime_ns, size), "pool": {...}}.
# Shared read-only result — see load_rulesets docstring.
_RULESETS_MEMO: dict[str, Any] = {}

FIELD_LEVELS = ("required", "optional", "unchecked")
CONTENT_SCOPES = ("filenames", "metadata", "file-content")
CONTENT_MATCHES = ("filename-glob", "substring", "regex")

DEFAULT_RULESET_KEY = "mcmaster-default"

# Fallback catalog used when the live metadatablocks schema is unavailable
# (offline / no permission). The Review-config page prefers the live schema.
FIELD_CATALOG: list[dict[str, str]] = [
    {"block": "citation", "field": "title", "label": "Title"},
    {"block": "citation", "field": "author", "label": "Author Name & Affiliation"},
    {"block": "citation", "field": "datasetContact", "label": "Dataset Contact"},
    {"block": "citation", "field": "dsDescription", "label": "Description"},
    {"block": "citation", "field": "subject", "label": "Subject"},
    {"block": "citation", "field": "depositor", "label": "Depositor"},
    {"block": "citation", "field": "dateOfDeposit", "label": "Deposit Date"},
    {"block": "citation", "field": "publication", "label": "Related Publication"},
    {"block": "citation", "field": "timePeriodCovered", "label": "Time Period Covered"},
    {"block": "citation", "field": "dateOfCollection", "label": "Date of Collection"},
    {"block": "citation", "field": "geographicCoverage", "label": "Geographic Coverage (citation)"},
    {"block": "citation", "field": "keyword", "label": "Keyword"},
    {"block": "citation", "field": "topicClassification", "label": "Topic Classification"},
    {"block": "citation", "field": "language", "label": "Language"},
    {"block": "citation", "field": "producer", "label": "Producer"},
    {"block": "citation", "field": "productionDate", "label": "Production Date"},
    {"block": "citation", "field": "productionPlace", "label": "Production Place"},
    {"block": "citation", "field": "contributor", "label": "Contributor"},
    {"block": "citation", "field": "grantNumber", "label": "Grant Number"},
    {"block": "citation", "field": "distributor", "label": "Distributor"},
    {"block": "citation", "field": "notesText", "label": "Notes"},
    {"block": "dataset", "field": "license", "label": "License"},
    {"block": "license", "field": "license", "label": "License"},
    {"block": "license", "field": "termsOfUse", "label": "Terms of Use"},
    {"block": "license", "field": "termsOfAccess", "label": "Terms of Access"},
    {"block": "geospatial", "field": "geographicCoverage", "label": "Geographic Coverage"},
    {"block": "geospatial", "field": "geographicBoundingBox", "label": "Geographic Bounding Box"},
    {"block": "socialscience", "field": "unitOfAnalysis", "label": "Unit of Analysis"},
    {"block": "socialscience", "field": "universe", "label": "Universe"},
    {"block": "socialscience", "field": "dataCollector", "label": "Data Collector"},
]


def _file_name() -> str:
    return "requirements_profiles.json"


def rulesets_path() -> _Path:
    """Return the same location as the legacy profiles file (exe dir when frozen)."""
    try:
        from metadata_check import profiles_path as _legacy

        return _legacy()
    except Exception:
        import sys

        if getattr(sys, "frozen", False):
            try:
                return _Path(sys.executable).parent / _file_name()
            except Exception:
                pass
        return _Path(_file_name())


# --------------------------------------------------------------------------
# Built-ins (mirror the legacy hard-coded checks)


def _mc_req(text: str) -> str:
    return text


def _builtin_mcmaster() -> dict[str, Any]:
    def fr(block: str, field: str, label: str, level: str, req: str,
           handler: str = "nonempty", template: str = "") -> dict[str, Any]:
        return {
            "block": block, "field": field, "label": label, "level": level,
            "requirement": req, "handler": handler,
            "response_template": template,
        }

    field_rules = [
        fr("citation", "title", "Title", "required",
           _mc_req("McMaster — Required (Depositor Checklist: Basic Metadata; Curation Log: Full Citation)"),
           "nonempty",
           "The dataset is missing a Title. Please provide a clear, descriptive title."),
        fr("citation", "dsDescription", "Description", "required",
           _mc_req("McMaster — Required (Curation Log: Full Citation; Checklist: Basic Metadata)"),
           "nonempty",
           "The dataset is missing a Description. Please add a brief summary of the data, methods, and contents."),
        fr("citation", "author", "Author Name & Affiliation", "required",
           _mc_req("McMaster — Required (Curation Log: Full Citation)"),
           "author_affiliation",
           "Author information is incomplete ({value}). Please ensure every author has a name and affiliation."),
        fr("citation", "datasetContact", "Dataset Contact", "required",
           _mc_req("McMaster — Required (Curation Log + Checklist)"),
           "nonempty",
           "The dataset is missing a Dataset Contact. Please add a contact name and email."),
        fr("citation", "subject", "Subject", "required",
           _mc_req("McMaster — Required (Checklist: Basic Metadata)"),
           "nonempty",
           "The dataset is missing a Subject classification. Please select at least one subject area."),
        fr("dataset", "license", "License", "required",
           _mc_req("McMaster — Required (Checklist: Data License)"),
           "license",
           "No data license is set. Please choose an appropriate license for the dataset."),
        fr("citation", "depositor", "Depositor", "required",
           _mc_req("McMaster — Required (Checklist: During Deposit)"),
           "nonempty",
           "The Depositor field is empty. Please confirm who deposited the dataset."),
        fr("citation", "dateOfDeposit", "Deposit Date", "required",
           _mc_req("McMaster — Required (Checklist: During Deposit)"),
           "nonempty",
           "The Deposit Date is missing. Please provide the date of deposit."),
        fr("citation", "publication", "Related Publication (title + journal)", "required",
           _mc_req("McMaster — Required (Curation Log + Checklist: *Publication)"),
           "related_pub",
           "Related publication details are incomplete ({value}). Please add the publication title and journal."),
        fr("citation", "publication", "Related Publication ID", "required",
           _mc_req("McMaster — Required (Curation Log: Pub ID)"),
           "related_pub_id",
           "The related publication ID (e.g. DOI) is missing. Please add it so the dataset links to the article."),
        fr("citation", "author", "ORCiD for authors", "optional",
           _mc_req("McMaster — Recommended (Checklist: Researcher ID; Curation Log: optional)"),
           "orcid",
           "Consider adding ORCiDs for the authors to improve attribution ({value})."),
        fr("citation", "author", "Author count", "optional",
           _mc_req("McMaster — Recommended (check the number of authors)"),
           "author_count",
           "The dataset has {value} authors — confirm this is the expected list."),
        fr("license", "license", "License and Terms of Use", "optional",
           _mc_req("McMaster — Recommended (Checklist: Data License)"),
           "license_terms",
           "No data license is set. Please choose an appropriate license for the dataset."),
        fr("citation", "timePeriodCovered", "Time Period / Date of Collection", "optional",
           _mc_req("McMaster — Recommended (Checklist: More Metadata — Time)"),
           "time_anyof",
           "Consider adding the time period covered or the date of collection."),
        fr("geospatial", "geographicCoverage", "Geographic Coverage", "optional",
           _mc_req("McMaster — Recommended (Checklist: More Metadata — Place)"),
           "geo",
           "Consider adding geographic coverage information for the dataset."),
    ]
    content_rules = [
        {
            "id": "readme-present",
            "label": "README file",
            "level": "required",
            "requirement": "McMaster — Required (Curation Log: Documentation; Checklist: Before Deposit)",
            "scope": ["filenames"],
            "match": "filename-glob",
            "pattern": "readme*",
            "case_sensitive": False,
            "response_template": "No README file was found in the dataset. Please add a README describing the files, formats, and how to reuse the data.",
        }
    ]
    return {
        "label": "McMaster — Curation Log + Depositor Checklist",
        "description": "Rules from docs/CurationLog.pdf and docs/DepositorChecklist.pdf (McMaster Dataverse)",
        "dataverses": ["*"],
        "field_rules": field_rules,
        "content_rules": content_rules,
        "filecheck_templates": {
            "*": "{check_id}: {message}",
            "inventory.zero_byte": "The file '{path}' is empty (0 bytes). Please remove it or upload the complete file.",
            "inventory.unchecked_types": "Some files need manual review: {message}",
        },
        "response_header": (
            "Hello,\n\nThank you for depositing your dataset ({dataset_title}, {persistent_id}). "
            "During curation we found a few items that need your attention:"
        ),
        "response_footer": (
            "Please update the deposit in Dataverse and let us know if you have questions.\n\nThank you."
        ),
    }


def _builtin_minimal() -> dict[str, Any]:
    # Legacy Minimal rows use raw typeNames + short requirement suffixes —
    # preserved exactly for back-compat.
    specs = [
        ("citation", "title", "title", "Minimal — Required: Title"),
        ("citation", "author", "author", "Minimal — Required: Author"),
        ("citation", "datasetContact", "datasetContact", "Minimal — Required: Contact"),
        ("citation", "dsDescription", "dsDescription", "Minimal — Required: Description"),
        ("citation", "subject", "subject", "Minimal — Required: Subject"),
    ]
    field_rules = [
        {"block": b, "field": f, "label": lbl, "level": "required",
         "requirement": req, "handler": "nonempty",
         "response_template": f"The dataset is missing {lbl}. Please provide it."}
        for b, f, lbl, req in specs
    ]

    return {
        "label": "Minimal — Dataverse core",
        "description": "Only Dataverse core mandatory fields (Title, Author, Contact, Description, Subject)",
        "dataverses": ["*"],
        "field_rules": field_rules,
        "content_rules": [],
        "filecheck_templates": {"*": "{check_id}: {message}"},
        "response_header": "Hello,\n\nYour dataset ({dataset_title}) needs the following before approval:",
        "response_footer": "Thank you.",
    }


def builtin_rulesets() -> dict[str, dict[str, Any]]:
    return {"mcmaster-default": _builtin_mcmaster(), "minimal": _builtin_minimal()}


# --------------------------------------------------------------------------
# Load / save


def _normalize_ruleset(key: str, raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    builtin = builtin_rulesets().get(key, {})
    out: dict[str, Any] = {
        "label": str(raw.get("label") or builtin.get("label") or key),
        "description": str(raw.get("description") or builtin.get("description") or ""),
        "dataverses": raw.get("dataverses", builtin.get("dataverses", ["*"])),
        "field_rules": raw.get("field_rules", builtin.get("field_rules", [])),
        "content_rules": raw.get("content_rules", builtin.get("content_rules", [])),
        "filecheck_templates": raw.get("filecheck_templates", builtin.get("filecheck_templates", {})),
        "response_header": str(raw.get("response_header") or builtin.get("response_header") or ""),
        "response_footer": str(raw.get("response_footer") or builtin.get("response_footer") or ""),
    }
    if not isinstance(out["dataverses"], list) or not out["dataverses"]:
        out["dataverses"] = ["*"]
    if not isinstance(out["field_rules"], list):
        out["field_rules"] = []
    if not isinstance(out["content_rules"], list):
        out["content_rules"] = []
    if not isinstance(out["filecheck_templates"], dict):
        out["filecheck_templates"] = {}
    # Copy rule dicts: normalization fills defaults in place and must never
    # mutate the caller's structures (or the built-in singletons).
    out["field_rules"] = [dict(r) for r in out["field_rules"] if isinstance(r, dict) and r.get("field")]
    out["content_rules"] = [dict(r) for r in out["content_rules"] if isinstance(r, dict) and r.get("id")]
    out["filecheck_templates"] = dict(out["filecheck_templates"])
    out["dataverses"] = list(out["dataverses"])
    for r in out["field_rules"]:
        if r.get("level") not in FIELD_LEVELS:
            r["level"] = "required"
        r.setdefault("block", "citation")
        r.setdefault("label", str(r.get("field") or ""))
        r.setdefault("handler", "nonempty")
        r.setdefault("response_template", "")
    for r in out["content_rules"]:
        if r.get("level") not in ("required", "optional"):
            r["level"] = "required"
        scope = r.get("scope") if isinstance(r.get("scope"), list) else ["filenames"]
        r["scope"] = [s for s in scope if s in CONTENT_SCOPES] or ["filenames"]
        if r.get("match") not in CONTENT_MATCHES:
            r["match"] = "filename-glob" if "filenames" in r["scope"] else "substring"
        r.setdefault("pattern", "")
        r.setdefault("case_sensitive", False)
        r.setdefault("response_template", "")
    return out


def load_rulesets() -> dict[str, dict[str, Any]]:
    """Built-ins overlaid with the v2 file when present. Never raises.

    Memoized by file identity (path + mtime + size): completeness evaluates
    on every metadata load/profile switch, so this must not hit disk each
    time. Saving rewrites the file (new mtime) which invalidates the memo.
    Callers must treat the result as read-only (the Review-config page works
    on its own deep copy).
    """
    base = builtin_rulesets()
    try:
        path = rulesets_path()
        try:
            st = path.stat()
            sig = (str(path), st.st_mtime_ns, st.st_size)
        except OSError:
            sig = (str(path), None, None)
        if _RULESETS_MEMO.get("sig") == sig and isinstance(_RULESETS_MEMO.get("pool"), dict):
            return _RULESETS_MEMO["pool"]
        if sig[1] is None:
            _RULESETS_MEMO["sig"] = sig
            _RULESETS_MEMO["pool"] = base
            return base
        raw = _json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and isinstance(raw.get("rulesets"), dict) and raw.get("version") == 2:
            for key, val in raw["rulesets"].items():
                norm = _normalize_ruleset(str(key), val)
                if norm is not None:
                    base[str(key)] = norm
            _RULESETS_MEMO["sig"] = sig
            _RULESETS_MEMO["pool"] = base
            return base
        # Legacy file shape (flat profiles written by the old dialog):
        # keep built-ins; the Review-config page migrates on save.
        return base
    except Exception:
        return base


def save_rulesets(rulesets: dict[str, dict[str, Any]]) -> _Path:
    import os
    import tempfile

    path = rulesets_path()
    clean: dict[str, Any] = {}
    for key, val in (rulesets or {}).items():
        norm = _normalize_ruleset(str(key), val)
        if norm is not None:
            clean[str(key)] = norm
    payload = {"version": RULESETS_VERSION, "rulesets": clean}
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _json.dumps(payload, indent=2, ensure_ascii=False)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(data)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return path


def get_ruleset(key: str, rulesets: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    pool = rulesets if isinstance(rulesets, dict) else load_rulesets()
    if key in pool:
        return pool[key]
    # Legacy profile names map onto the built-ins.
    if key == "McMaster":
        return pool.get("mcmaster-default", builtin_rulesets()["mcmaster-default"])
    if key == "Minimal":
        return pool.get("minimal", builtin_rulesets()["minimal"])
    return pool.get(DEFAULT_RULESET_KEY, builtin_rulesets()["mcmaster-default"])


def _norm_base(url: str) -> str:
    try:
        return (url or "").rstrip("/").lower()
    except Exception:
        return ""


def rulesets_for_dataverse(base_url: str,
                            rulesets: dict[str, dict[str, Any]] | None = None) -> list[tuple[str, dict[str, Any]]]:
    """(key, ruleset) usable for an instance: '*' matches all. Never raises."""
    try:
        pool = rulesets if isinstance(rulesets, dict) else load_rulesets()
        want = _norm_base(base_url)
        out: list[tuple[str, dict[str, Any]]] = []
        for key, rs in pool.items():
            dvs = rs.get("dataverses") or ["*"]
            norms = {_norm_base(d) for d in dvs if isinstance(d, str)}
            if "*" in norms or (want and want in norms):
                out.append((key, rs))
        return out or [(DEFAULT_RULESET_KEY, get_ruleset(DEFAULT_RULESET_KEY, pool))]
    except Exception:
        b = builtin_rulesets()
        return [(DEFAULT_RULESET_KEY, b[DEFAULT_RULESET_KEY])]


# --------------------------------------------------------------------------
# Evaluation (imports metadata_check lazily to avoid a cycle)


def _mc() -> Any:
    import metadata_check as _m

    return _m


def _blocks(metadata: dict[str, Any]) -> dict[str, Any]:
    try:
        latest = metadata.get("latestVersion") or {}
        return latest.get("metadataBlocks") or metadata.get("metadataBlocks") or {}
    except Exception:
        return {}


def _eval_handler(handler: str, metadata: dict[str, Any], blocks: dict[str, Any],
                  block: str, field: str, rule: dict[str, Any] | None = None) -> tuple[bool, str]:
    m = _mc()
    rule = rule if isinstance(rule, dict) else {}
    if handler == "nonempty":
        raw = m._field(blocks, block, field)
        return m._nonempty(raw), m._display_value(raw)
    if handler == "license":
        latest = metadata.get("latestVersion") or {}
        lic = latest.get("license") or metadata.get("license")
        ok = isinstance(lic, dict) and bool(lic.get("name"))
        val = lic.get("name", "") if isinstance(lic, dict) else m._display_value(lic)
        return ok, val or "—"
    if handler == "author_affiliation":
        raw = m._field(blocks, "citation", "author") or []
        authors = [a for a in raw if isinstance(a, dict)] if isinstance(raw, list) else []
        ok_names = m._nonempty(m._field(blocks, "citation", "author")) and bool(authors) and all(
            m._nonempty((a or {}).get("authorName", {})) for a in authors
        )
        missing = [
            str((a.get("authorName", {}) or {}).get("value", "")
                if isinstance(a.get("authorName", {}), dict) else a.get("authorName", "")
                or f"author {i+1}")
            for i, a in enumerate(authors)
            if not m._nonempty((a or {}).get("authorAffiliation", {}))
        ]
        affil_ok = bool(authors) and not missing
        val = m._display_value(m._field(blocks, "citation", "author"))
        if missing:
            suffix = f" [missing affiliation: {', '.join(missing[:3])}]"[:200]
            val = (val + suffix) if val != "—" else f"missing affiliation: {', '.join(missing[:3])}"
        return bool(ok_names and affil_ok), val
    if handler == "related_pub":
        rel = m._field(blocks, "citation", "publication") or []
        rel_list = rel if isinstance(rel, list) else ([rel] if rel else [])
        rel_list = [r for r in rel_list if isinstance(r, dict)]
        if not rel_list:
            return False, "—"
        complete = False
        displays: list[str] = []
        for entry in rel_list:
            cit = entry.get("publicationCitation", {}).get("value", "") \
                if isinstance(entry.get("publicationCitation"), dict) else str(entry.get("publicationCitation") or "")
            jour = entry.get("journal", {}).get("value", "") if isinstance(entry.get("journal"), dict) else ""
            idv = entry.get("publicationIDNumber", {}).get("value", "") \
                if isinstance(entry.get("publicationIDNumber"), dict) else str(entry.get("publicationIDNumber") or "")
            if cit or jour:
                displays.append(f"{cit} — {jour}".strip(" —") if cit and jour else (cit or jour))
            elif idv:
                displays.append(idv)
            else:
                displays.append(m._display_value(entry))
            if (m._nonempty(entry.get("publicationCitation", {})) or m._nonempty(entry.get("title", {}))) \
                    and m._nonempty(entry.get("journal", {})):
                complete = True
        val = displays[0] if displays else "—"
        if len(displays) > 1:
            val += f" (+{len(displays)-1} more)"
        return complete, val
    if handler == "related_pub_id":
        rel = m._field(blocks, "citation", "publication") or []
        rel_list = rel if isinstance(rel, list) else ([rel] if rel else [])
        for entry in ([r for r in rel_list if isinstance(r, dict)]):
            idv = entry.get("publicationIDNumber", {}).get("value", "") \
                if isinstance(entry.get("publicationIDNumber"), dict) else str(entry.get("publicationIDNumber") or "")
            if idv and str(idv).strip():
                return True, str(idv)
        return False, "—"
    if handler == "orcid":
        # Per-author ORCID: every author must carry a valid ORCID when the
        # rule is enabled (empty author list → incomplete, value "—").
        raw = m._field(blocks, "citation", "author") or []
        authors = [a for a in raw if isinstance(a, dict)] if isinstance(raw, list) else []
        if not authors:
            return False, "—"
        missing: list[str] = []
        found: list[str] = []
        for i, author in enumerate(authors):
            name = str(
                (author.get("authorName") or {}).get("value", "")
                if isinstance(author.get("authorName"), dict)
                else author.get("authorName") or ""
            ).strip() or f"author {i + 1}"
            id_val = author.get("authorIdentifier", {})
            scheme = author.get("authorIdentifierScheme", {})
            id_str = id_val.get("value", "") if isinstance(id_val, dict) else str(id_val or "")
            scheme_str = scheme.get("value", "") if isinstance(scheme, dict) else str(scheme or "")
            if "orcid" in str(scheme_str).lower() and id_str.strip() and m.ORCID_RE.match(id_str.strip()):
                found.append(f"{name}: {id_str.strip()}")
            else:
                missing.append(name)
        val = "; ".join(found[:3]) if found else "—"
        if len(found) > 3:
            val += f" (+{len(found) - 3} more)"
        if missing and found:
            val += f" [missing: {', '.join(missing[:3])}]"
        elif missing and not found:
            # Preserve the legacy single-value display ("—") for parity when
            # no author has an ORCID yet; the ok flag still tracks per-author.
            val = "—"
        return (not missing), val
    if handler == "author_count":
        raw = m._field(blocks, "citation", "author") or []
        authors = [a for a in raw if isinstance(a, dict)] if isinstance(raw, list) else []
        n = len(authors)
        names: list[str] = []
        for a in authors[:3]:
            nm = a.get("authorName", {})
            names.append(
                str(nm.get("value", "") if isinstance(nm, dict) else nm or "").strip()
            )
        names = [x for x in names if x]
        if n <= 3:
            val = f"{n} author(s)" + (f": {'; '.join(names)}" if names else "")
        else:
            val = f"{n} authors: {'; '.join(names)} (+{n - len(names)} more)"
        # Optional bounds via rule config (min/max keys on the field rule).
        min_authors = rule.get("min")
        max_authors = rule.get("max")
        ok = n > 0
        if min_authors is not None:
            try:
                if n < int(min_authors):
                    ok = False
            except (TypeError, ValueError):
                pass
        if max_authors is not None:
            try:
                if n > int(max_authors):
                    ok = False
            except (TypeError, ValueError):
                pass
        return ok, val or "—"
    if handler == "license_terms":
        # License + Terms of Use / Access from latestVersion (API surface).
        latest = metadata.get("latestVersion") or {}
        lic = latest.get("license") or metadata.get("license")
        lic_name = lic.get("name", "") if isinstance(lic, dict) else m._display_value(lic)
        tou = latest.get("termsOfUse") or metadata.get("termsOfUse") or ""
        toa = latest.get("termsOfAccess") or metadata.get("termsOfAccess") or ""
        tou_s = tou.get("value", "") if isinstance(tou, dict) else str(tou or "")
        toa_s = toa.get("value", "") if isinstance(toa, dict) else str(toa or "")
        parts = [p for p in (lic_name, tou_s, toa_s) if p]
        val = " · ".join(parts) if parts else "—"
        ok = bool(lic_name)  # license required; terms are optional context
        return ok, val
    if handler == "terms_of_use":
        latest = metadata.get("latestVersion") or {}
        tou = latest.get("termsOfUse") or metadata.get("termsOfUse") or ""
        val = tou.get("value", "") if isinstance(tou, dict) else str(tou or "")
        return bool(val.strip()), val or "—"
    if handler == "terms_of_access":
        latest = metadata.get("latestVersion") or {}
        toa = latest.get("termsOfAccess") or metadata.get("termsOfAccess") or ""
        val = toa.get("value", "") if isinstance(toa, dict) else str(toa or "")
        return bool(val.strip()), val or "—"
    if handler == "time_anyof":
        has = m._nonempty(m._field(blocks, "citation", "timePeriodCovered")) or \
            m._nonempty(m._field(blocks, "citation", "dateOfCollection"))
        val = f"{m._display_value(m._field(blocks, 'citation', 'timePeriodCovered'))} / " \
              f"{m._display_value(m._field(blocks, 'citation', 'dateOfCollection'))}".strip(" /") or "—"
        return has, val
    if handler == "geo":
        geo = m._field(blocks, "geospatial", "geographicCoverage") or \
            m._field(blocks, "citation", "geographicCoverage")
        return m._nonempty(geo), m._display_value(geo)
    # Unknown handler: plain nonempty on the configured block/field.
    raw = m._field(blocks, block, field)
    return m._nonempty(raw), m._display_value(raw)


def _iter_metadata_strings(metadata: dict[str, Any]) -> list[str]:
    out: list[str] = []

    def _walk(v: Any) -> None:
        if isinstance(v, str):
            if v.strip():
                out.append(v)
        elif isinstance(v, dict):
            for vv in v.values():
                _walk(vv)
        elif isinstance(v, list):
            for vv in v:
                _walk(vv)

    try:
        _walk(_blocks(metadata))
    except Exception:
        pass
    return out


def _match_filenames(rule: dict[str, Any], inventory: list[dict[str, Any]] | None) -> tuple[bool | None, str]:
    """(found | None=pending, evidence). None when the file list is not loaded."""
    if inventory is None:
        return None, "— (load file list to check)"
    if len(inventory) == 0:
        # No files at all: a README-style rule is not applicable; any other
        # filename rule simply finds nothing.
        pat = str(rule.get("pattern") or "")
        if str(rule.get("id") or "") == "readme-present" or "readme" in pat.lower():
            return True, "No files in dataset — README not applicable"
        return False, "No files in dataset"
    pattern = str(rule.get("pattern") or "")
    match = rule.get("match") or "filename-glob"
    case = bool(rule.get("case_sensitive"))
    for f in inventory:
        if not isinstance(f, dict):
            continue
        raw_path = str(f.get("path") or f.get("label") or "")
        base = _Path(raw_path).name
        target = raw_path if match != "filename-glob" else base
        if match == "filename-glob":
            # A glob containing "/" matches the full inventory path,
            # otherwise the basename (so "readme*" is not defeated by folders).
            if "/" in pattern:
                hay, pat = (raw_path, pattern) if case else (raw_path.lower(), pattern.lower())
            else:
                hay, pat = (base, pattern) if case else (base.lower(), pattern.lower())
            # NOTE: fnmatch.fnmatch applies os.path.normcase (lowercasing on
            # Windows), so case-sensitive matching must use fnmatchcase.
            matched = fnmatch.fnmatchcase(hay, pat) if case else fnmatch.fnmatch(hay, pat)
            if matched:
                return True, f.get("path") or f.get("label") or "found"
            # Legacy README behavior: readme, readme.*, readme_* all count
            # (case-insensitive by nature, like the original check).
            if not case and "readme" in pat and (
                hay == "readme" or hay.startswith(("readme.", "readme_", "readme-"))
            ):
                return True, f.get("path") or f.get("label") or "found"
        elif match == "regex":
            try:
                flags = 0 if case else re.IGNORECASE
                if re.search(pattern, target, flags):
                    return True, f.get("path") or f.get("label") or "found"
            except re.error:
                continue
        else:  # substring over the full path
            hay, ndl = (target, pattern) if case else (target.lower(), pattern.lower())
            if ndl and ndl in hay:
                return True, f.get("path") or f.get("label") or "found"
    return False, "No matching file found"


def _match_metadata(rule: dict[str, Any], metadata: dict[str, Any],
                    _strings: list[str] | None = None) -> tuple[bool, str]:
    pattern = str(rule.get("pattern") or "")
    if not pattern:
        return False, "—"
    match = rule.get("match") or "substring"
    case = bool(rule.get("case_sensitive"))
    strings = _strings if _strings is not None else _iter_metadata_strings(metadata)
    for text in strings:
        if match == "regex":
            try:
                if re.search(pattern, text, 0 if case else re.IGNORECASE):
                    return True, text[:120]
            except re.error:
                return False, "— (invalid pattern)"
        else:
            hay, ndl = (text, pattern) if case else (text.lower(), pattern.lower())
            if ndl in hay:
                return True, text[:120]
    return False, "No matching text in metadata"


def _match_file_content(rule: dict[str, Any], staged_dir: Any) -> tuple[bool | None, str]:
    """(found | None=pending, evidence). Pending when nothing is staged.

    Runs synchronously (called from the completeness evaluation on the UI
    thread), so it is deliberately bounded: skips known-binary formats,
    caps files/bytes, and memoizes by directory signature + pattern.
    """
    from pathlib import Path as _P

    pattern = str(rule.get("pattern") or "")
    if not pattern:
        return False, "—"
    try:
        root = _P(str(staged_dir)) if staged_dir else None
    except Exception:
        root = None
    if root is None or not root.exists():
        return None, "— (download dataset to check file contents)"
    match = rule.get("match") or "substring"
    case = bool(rule.get("case_sensitive"))
    try:
        sig = _staged_signature(root)
    except Exception:
        return None, "— (download dataset to check file contents)"
    if sig is None:
        return None, "— (download dataset to check file contents)"
    memo_key = (str(root), sig, pattern, match, case)
    hit = _CONTENT_MEMO.get(memo_key)
    if hit is not None:
        return hit
    result = _scan_staged_files(root, pattern, match, case)
    try:
        if len(_CONTENT_MEMO) >= 64:
            _CONTENT_MEMO.clear()
        _CONTENT_MEMO[memo_key] = result
    except Exception:
        pass
    return result


# Suffixes never worth decoding as text (checked by byte search instead of
# burning time on decoded binary mush that also risks false positives).
_BINARY_SUFFIXES = frozenset({
    ".sav", ".dta", ".sas7bdat", ".por", ".nc", ".h5", ".hdf5", ".h5ad",
    ".xlsx", ".xls", ".xlsm", ".pdf", ".png", ".jpg", ".jpeg", ".tif",
    ".tiff", ".gif", ".bmp", ".webp", ".zip", ".tar", ".gz", ".bz2",
    ".xz", ".7z", ".rar", ".exe", ".dll", ".so", ".bin", ".o", ".class",
    ".mp3", ".mp4", ".avi", ".mov", ".wav", ".ogg", ".rds", ".rdata",
    ".pyc", ".sqlite", ".db", ".gpkg", ".shp",
})

_MAX_CONTENT_FILES = 100
_MAX_CONTENT_BYTES = 1 << 20
_MAX_CONTENT_FILE_SIZE = 5 * 1024 * 1024

# Memo for _match_file_content: {(root, sig, pattern, match, case): result}.
_CONTENT_MEMO: dict[Any, tuple[bool | None, str]] = {}


def _staged_signature(root: Any) -> tuple[int, int, int] | None:
    """Cheap (count, bytes, max-mtime) fingerprint of a staged tree."""
    try:
        n = total = newest = 0
        for p in root.rglob("*"):
            try:
                if p.is_file():
                    st = p.stat()
                    n += 1
                    total += st.st_size
                    mt = st.st_mtime_ns
                    if mt > newest:
                        newest = mt
            except OSError:
                continue
        if n == 0:
            return None
        return (n, total, newest)
    except OSError:
        return None


def _scan_staged_files(root: Any, pattern: str, match: str, case: bool) -> tuple[bool | None, str]:

    candidates = []
    try:
        for p in sorted(root.rglob("*")):
            try:
                if not p.is_file():
                    continue
                if p.suffix.lower() in _BINARY_SUFFIXES:
                    continue
                candidates.append(p)
            except OSError:
                continue
    except OSError:
        return None, "— (download dataset to check file contents)"
    if not candidates:
        return None, "— (no searchable text files staged)"
    checked = 0
    for path in candidates[:_MAX_CONTENT_FILES]:
        try:
            size = path.stat().st_size
            if size == 0 or size > _MAX_CONTENT_FILE_SIZE:
                continue
            raw = path.read_bytes()[:_MAX_CONTENT_BYTES]
        except OSError:
            continue
        try:
            text = raw.decode("utf-8", errors="ignore")
        except Exception:
            continue
        checked += 1
        if match == "regex":
            try:
                if re.search(pattern, text, 0 if case else re.IGNORECASE):
                    return True, f"{path.name}: match"
            except re.error:
                return False, "— (invalid pattern)"
        else:
            hay, ndl = (text, pattern) if case else (text.lower(), pattern.lower())
            if ndl in hay:
                return True, f"{path.name}: match"
    if checked == 0:
        return None, "— (no searchable text files staged)"
    return False, f"No matching text in {checked} staged file(s)"


def evaluate_content_rule(rule: dict[str, Any], metadata: dict[str, Any],
                           inventory: list[dict[str, Any]] | None,
                           staged_dir: Any = None,
                           _metadata_strings: list[str] | None = None) -> dict[str, Any]:
    """Evaluate one content rule across its chosen scopes (OR semantics)."""
    scope = rule.get("scope") if isinstance(rule.get("scope"), list) else ["filenames"]
    scope = [s for s in scope if s in CONTENT_SCOPES] or ["filenames"]
    label = str(rule.get("label") or rule.get("id") or "Content check")
    req = str(rule.get("requirement") or "Custom content rule")
    level = rule.get("level") if rule.get("level") in ("required", "optional") else "required"
    strings = _metadata_strings
    if strings is None and "metadata" in scope:
        strings = _iter_metadata_strings(metadata or {})
    pending_bits: list[str] = []
    evidences: list[str] = []
    for s in scope:
        try:
            if s == "filenames":
                found, ev = _match_filenames(rule, inventory)
            elif s == "metadata":
                found, ev = _match_metadata(rule, metadata or {}, strings)
            else:
                found, ev = _match_file_content(rule, staged_dir)
        except Exception:
            found, ev = False, "—"
        if found is True:
            return {"rule_id": str(rule.get("id") or label), "kind": "content",
                    "field": label, "requirement": req, "value": ev or "found",
                    "status": "complete", "level": level, "pending": False,
                    "response_template": str(rule.get("response_template") or "")}
        if found is None:
            pending_bits.append(ev)
        elif ev and ev not in ("No matching file found", "No matching text in metadata"):
            evidences.append(ev)
    if pending_bits and not evidences:
        # Nothing searchable yet (e.g. file list not loaded): surface the
        # pending note like the legacy README row did. The Response assembler
        # skips pending findings so no draft text is generated for them.
        return {"rule_id": str(rule.get("id") or label), "kind": "content",
                "field": label, "requirement": req,
                "value": pending_bits[0], "status": "incomplete",
                "level": level, "pending": True,
                "response_template": str(rule.get("response_template") or "")}
    # Special-case the legacy no-files README row: not applicable, not a failure.
    for ev in evidences:
        if "not applicable" in ev.lower():
            return {"rule_id": str(rule.get("id") or label), "kind": "content",
                    "field": label, "requirement": req, "value": ev,
                    "status": "complete", "level": level, "pending": False,
                    "response_template": str(rule.get("response_template") or "")}
    return {"rule_id": str(rule.get("id") or label), "kind": "content",
            "field": label, "requirement": req,
            "value": evidences[0] if evidences else "No match found",
            "status": "incomplete", "level": level, "pending": False,
            "response_template": str(rule.get("response_template") or "")}


def evaluate_ruleset(metadata: dict[str, Any], ruleset: dict[str, Any],
                      inventory: list[dict[str, Any]] | None = None,
                      staged_dir: Any = None) -> list[dict[str, Any]]:
    """Run every enabled rule. 'unchecked' field rules are skipped. Never raises."""
    results: list[dict[str, Any]] = []
    try:
        blocks = _blocks(metadata or {})
    except Exception:
        blocks = {}
    # One metadata-string walk shared by every content rule with that scope.
    try:
        content_rules = [cr for cr in ((ruleset or {}).get("content_rules") or []) if isinstance(cr, dict)]
        metadata_strings = _iter_metadata_strings(metadata or {}) if any(
            "metadata" in (cr.get("scope") if isinstance(cr.get("scope"), list) else ["filenames"])
            for cr in content_rules
        ) else []
    except Exception:
        metadata_strings = []
    for fr in (ruleset or {}).get("field_rules") or []:
        try:
            if not isinstance(fr, dict):
                continue
            if (fr.get("level") or "required") == "unchecked":
                continue
            block = str(fr.get("block") or "citation")
            field = str(fr.get("field") or "")
            label = str(fr.get("label") or field)
            req = str(fr.get("requirement") or "")
            level = fr.get("level") if fr.get("level") in ("required", "optional") else "required"
            handler = str(fr.get("handler") or "nonempty")
            ok, val = _eval_handler(handler, metadata or {}, blocks, block, field, fr)
            # rule_id carries the handler: several rules may share one field
            # (author names vs ORCiDs both live on citation.author) and the
            # Response findings list keys off rule_id.
            rule_id = f"field:{block}.{field}"
            if handler != "nonempty":
                rule_id += f":{handler}"
            results.append({
                "rule_id": rule_id,
                "kind": "field", "field": label, "requirement": req,
                "value": val or "—", "status": "complete" if ok else "incomplete",
                "level": level, "pending": False,
                "response_template": str(fr.get("response_template") or ""),
                "block": block, "name": field,
            })
        except Exception:
            continue
    for cr in (ruleset or {}).get("content_rules") or []:
        try:
            if not isinstance(cr, dict):
                continue
            results.append(evaluate_content_rule(cr, metadata or {}, inventory, staged_dir,
                                                 _metadata_strings=metadata_strings))
        except Exception:
            continue
    return results
