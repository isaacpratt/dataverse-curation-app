"""Pure parse/normalize helpers for Dataverse payloads.

No network, no clock, no threading: a function here is safe to call
from any context with just the payload in hand.
"""

from typing import Any

from client.constants import STATE_IN_REVIEW


def _field_value(dataset_version: dict[str, Any], type_name: str) -> Any:
    fields = dataset_version.get("metadataBlocks", {}).get("citation", {}).get("fields", [])
    for field in fields:
        if field.get("typeName") == type_name:
            return field.get("value")
    return None


def extract_title(dataset_version: dict[str, Any]) -> str:
    """Return the dataset title from a version payload (first titleValue)."""
    value = _field_value(dataset_version, "title")
    return value if isinstance(value, str) else ""


def _extract_contact(dataset_version: dict[str, Any]) -> str:
    value = _field_value(dataset_version, "datasetContact")
    if isinstance(value, list) and value:
        first = value[0] or {}
        name = (
            first.get("datasetContactName", {}).get("value", "")
            if isinstance(first.get("datasetContactName"), dict)
            else first.get("datasetContactName", "")
        )
        email = (
            first.get("datasetContactEmail", {}).get("value", "")
            if isinstance(first.get("datasetContactEmail"), dict)
            else first.get("datasetContactEmail", "")
        )
        if name and email:
            return f"{name} <{email}>"
        return name or email or ""
    if isinstance(value, str):
        return value
    return ""


def normalize_files(dataset_version: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize a datasetVersion.files array into flat file records."""
    records: list[dict[str, Any]] = []
    for entry in dataset_version.get("files", []):
        data_file = entry.get("dataFile", {}) or {}
        checksum_type = ""
        checksum_value = ""
        checksum = data_file.get("checksum")
        if isinstance(checksum, dict):
            checksum_type = str(checksum.get("type", "")).lower()
            checksum_value = checksum.get("value", "")
        else:
            for candidate in ("sha1", "md5"):
                if data_file.get(candidate):
                    checksum_type = candidate
                    checksum_value = data_file[candidate]
                    break
        directory = entry.get("directoryLabel") or ""
        filename = entry.get("filename") or data_file.get("filename") or ""
        restrictions = extract_file_restrictions(entry, data_file)
        # Tabular ingest products (.tab): field names verified against
        # JsonPrinter (UNF is uppercase there). The UNF is the stable
        # fingerprint when the server regenerates .tab bytes.
        unf = (
            data_file.get("UNF")
            or data_file.get("unf")
            or entry.get("UNF")
            or entry.get("unf")
            or ""
        )
        # Tabular ingest status/errors surfaced from the API (when present).
        ingest_status = str(data_file.get("ingestStatus") or entry.get("ingestStatus") or "")
        ingest_error = str(
            data_file.get("ingestErrorMessage")
            or data_file.get("ingestError")
            or entry.get("ingestErrorMessage")
            or entry.get("ingestError")
            or ""
        )
        # Access restrictions (restricted files, embargo, retention).
        restricted = bool(entry.get("restricted", data_file.get("restricted", False)))
        try:
            original_size = int(
                data_file.get("originalFileSize") or entry.get("originalFileSize") or 0
            )
        except (TypeError, ValueError):
            original_size = 0
        try:
            size_bytes = int(data_file.get("filesize") or 0)
        except (TypeError, ValueError):
            size_bytes = 0
        records.append(
            {
                "id": str(data_file.get("id", "")),
                "path": f"{directory}/{filename}" if directory else filename,
                "size_bytes": size_bytes,
                "mime_type": data_file.get("contentType") or "",
                "checksum_type": checksum_type.lower(),
                "checksum_value": checksum_value,
                "embargo_date": restrictions["embargo_date"],
                "retention": restrictions["retention"],
                "restricted": restricted,
                "tabular": bool(data_file.get("tabularData", entry.get("tabularData", False))),
                "unf": str(unf or ""),
                "ingest_status": ingest_status,
                "ingest_error": ingest_error,
                "original_format": str(
                    data_file.get("originalFileFormat") or entry.get("originalFileFormat") or ""
                ),
                "original_name": str(
                    data_file.get("originalFileName") or entry.get("originalFileName") or ""
                ),
                "original_size": original_size,
            }
        )
    return records


_DATE_RE = None  # lazy compiled in _scan_restriction_dates


def _scan_restriction_dates(obj: Any, depth: int = 0) -> dict[str, str]:
    """Collect {dotted.key.path: YYYY-MM-DD} for embargo/retention-ish keys."""
    import re

    global _DATE_RE
    if _DATE_RE is None:
        _DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
    found: dict[str, str] = {}
    if isinstance(obj, dict):
        items = obj.items()
    elif isinstance(obj, list) and depth < 2:
        for value in obj:
            found.update(_scan_restriction_dates(value, depth + 1))
        return found
    else:
        return found
    for key, value in items:
        key_lower = str(key).lower()
        interesting = (
            "embargo" in key_lower or "retention" in key_lower or "dateavailable" in key_lower
        )
        if isinstance(value, str):
            if interesting:
                match = _DATE_RE.search(value)
                if match:
                    found[key_lower] = match.group(0)
        elif isinstance(value, (dict, list)) and depth < 2:
            for sub_key, sub_val in _scan_restriction_dates(value, depth + 1).items():
                found[f"{key_lower}.{sub_key}"] = sub_val
    return found


def extract_file_restrictions(entry: dict[str, Any], data_file: dict[str, Any]) -> dict[str, str]:
    """Pull embargo/retention dates out of a file-version entry.

    Field names vary by Dataverse version, so both the entry-level and
    dataFile-level dicts are scanned (two levels deep) for embargo /
    retention / dateAvailable keys holding a YYYY-MM-DD date. Returns
    {"embargo_date": ..., "retention": ...} with "" when absent.
    """
    found: dict[str, str] = {}
    for source in (entry or {}, data_file or {}):
        if isinstance(source, dict):
            for path, date in _scan_restriction_dates(source).items():
                found.setdefault(path, date)
    embargo_date = ""
    for path, date in found.items():
        if "embargo" in path or path == "dateavailable":
            embargo_date = date
            break
    retention = ""
    for path, date in found.items():
        if "retention" in path:
            retention = date
            break
    return {"embargo_date": embargo_date, "retention": retention}


def parse_timestamps(payload: dict[str, Any]) -> dict[str, str]:
    """Normalize a /timestamps response data object to known date fields."""
    data = (payload or {}).get("data")
    if not isinstance(data, dict):
        return {}
    keys = (
        "createTime",
        "publicationTime",
        "lastMetadataExportTime",
        "lastMajorVersionReleaseTime",
        "lastUpdateTime",
        "lastIndexTime",
        "lastPermissionUpdateTime",
        "globalIdCreateTime",
    )
    return {key: str(data.get(key) or "") for key in keys}


# Notification types that mark a dataset submitted for review (exact enum
# values from UserNotification.Type — verified against source).
REVIEW_SUBMIT_TYPES = frozenset({"SUBMITTEDDS"})


def note_review_submission(pid: str, note: Any) -> dict[str, str] | None:
    """Structured review-submission match (in-app notification format).

    Matches when the note's type is a review-submission type AND its
    datasetPersistentIdentifier equals this dataset's persistent ID
    (case-insensitive). No text comparison anywhere: identity comes from
    the structured fields, and the collection name from ownerDisplayName
    as pulled from the API. Returns {time, dataverse, dataset, requestor}
    or None.
    """
    if not isinstance(note, dict):
        return None
    if str(note.get("type") or "").upper() not in REVIEW_SUBMIT_TYPES:
        return None
    note_pid = str(note.get("datasetPersistentIdentifier") or "").strip()
    wanted = (pid or "").strip()
    if not note_pid or not wanted or note_pid.casefold() != wanted.casefold():
        return None
    requestor = " ".join(
        part
        for part in (
            str(note.get("requestorFirstName") or "").strip(),
            str(note.get("requestorLastName") or "").strip(),
        )
        if part
    )
    return {
        "time": str(note.get("sentTimestamp") or ""),
        "dataverse": str(note.get("ownerDisplayName") or "").strip(),
        "dataset": str(note.get("datasetDisplayName") or "").strip(),
        "requestor": requestor,
    }


def locks_indicate_review(locks: list[Any]) -> bool:
    """Return True when any lock's type/reason indicates an in-review lock."""
    import re as _re

    # Match "review" (InReview, in_review, in-review, "In Review") but not
    # "Preview": the 'r' must not be preceded by 'p' (case-insensitive).
    _review_re = _re.compile(r"(?<!p)review", _re.IGNORECASE)
    for lock in locks:
        if not isinstance(lock, dict):
            continue
        # Prefer lockType; fall back to reason only when lockType is empty.
        kind = lock.get("lockType") or lock.get("reason", "")
        if kind and _review_re.search(str(kind)):
            return True
    return False


def search_item_state(item: dict[str, Any]) -> tuple[str, bool]:
    """Derive (state, has_draft) from a Search API dataset doc.

    A dataset with a published version plus a new draft version can surface
    as a RELEASED doc that still carries "Draft" in publicationStatuses —
    without this, the in-progress draft is invisible to draft filtering.
    Draft/review markers anywhere win over the headline versionState.
    """
    statuses = [str(s or "") for s in (item.get("publicationStatuses") or [])]
    lowered = [s.lower() for s in statuses]
    vs = str(item.get("versionState") or "")
    has_draft = vs.upper() == "DRAFT" or any("draft" in s or "review" in s for s in lowered)
    if any("review" in s for s in lowered):
        return STATE_IN_REVIEW, True
    if has_draft:
        return "DRAFT", True
    if vs:
        return vs, False
    if statuses:
        return statuses[0], False
    return "", False


def parse_allowed_labels(data: Any) -> list[str]:
    """Parse the allowedCurationLabels `data` payload.

    Shapes seen in the wild: a comma-separated string, a JSON array of
    strings, or (Dataverse 6.8) an envelope object carrying either under
    "message". All shapes yield the same deduped list — previously the
    array shape was silently dropped to [], and the envelope shape with it
    (every probe against such servers returned [] while the log still said
    "received", so the allowed set NEVER populated and only in-use labels
    ever showed).
    """
    seen: list[str] = []
    if isinstance(data, dict):
        data = data.get("message", "")
    if isinstance(data, str):
        parts = data.split(",")
    elif isinstance(data, (list, tuple)):
        parts = list(data)
    else:
        return []
    for part in parts:
        label = str(part).strip() if isinstance(part, str) else str(part or "").strip()
        if label and label not in seen:
            seen.append(label)
    return seen


def top_level_collection(collection: str | None) -> str:
    """First path segment of a collection alias.

    Allowed curation labels are shared across a first-level collection and
    everything under it ("mcmaster/x" uses "mcmaster"'s list), so the
    allowed-set cache is keyed by this segment, not the full alias.
    "" means the whole repository.
    """
    try:
        seg = (collection or "").strip().strip("/")
    except Exception:
        return ""
    if not seg:
        return ""
    return seg.split("/")[0].strip()


def is_draft_dataset(ds: Any) -> bool:
    """Check whether a crawl row is under curation (draft or in review).

    Curation labels/status exist only for datasets under curation — the
    shared predicate for per-draft label reads and probe ordering, so
    published/deaccessioned rows are never probed.
    """
    try:
        if not isinstance(ds, dict):
            return False
        state = str(ds.get("state") or "").upper()
        return state == "DRAFT" or "REVIEW" in state or bool(ds.get("has_draft"))
    except Exception:
        return False


def _version_files_data(data: Any) -> dict[str, Any]:
    """Extract the files-carrying version dict from a version `data` payload.

    Dataverse versions API puts files at data.files (not
    data.datasetVersion.files); metadata reads put them under
    data.datasetVersion or data.latestVersion.
    """
    try:
        if not isinstance(data, dict):
            return {}
        # Prefer version docs that actually carry files; fall back through
        # the known shapes in order (mirrors get_file_inventory history).
        for key in ("datasetVersion", "latestVersion"):
            try:
                candidate = data.get(key)
            except Exception:
                candidate = None
            if isinstance(candidate, dict) and candidate.get("files"):
                return candidate
        try:
            dataset_version = data.get("datasetVersion")
        except Exception:
            dataset_version = None
        if isinstance(dataset_version, dict):
            return dataset_version
        try:
            data_files = data.get("files")
        except Exception:
            data_files = None
        if data_files:
            return {"files": data_files if isinstance(data_files, list) else []}
        try:
            latest = data.get("latestVersion")
        except Exception:
            latest = None
        if isinstance(latest, dict):
            return latest
        return {}
    except Exception:
        return {}


def _summarize_version_data(data: Any) -> tuple[list[dict[str, Any]], str, str, bool]:
    """Best-effort (files, depositor, versionState, files_known) from a payload.

    Never raises. `files_known` is False when the payload carried no
    `files` key at all — that means "the server did not tell us", which
    is different from "this dataset has zero files" and must not be
    rendered as a size of 0.
    """
    try:
        version_data = _version_files_data(data)
        files = normalize_files(version_data)
    except Exception:
        files = []
    depositor = ""
    state = ""
    files_known = False
    try:
        if isinstance(version_data, dict):
            if "files" in version_data:
                files_known = True
            dep = _field_value(version_data, "depositor")
            if isinstance(dep, str):
                depositor = dep
            if not depositor and isinstance(data, dict):
                depositor = str(data.get("depositorName") or "")
            state = str(version_data.get("versionState") or "")
        if not state and isinstance(data, dict):
            # Flat version shape: versionState sits beside files.
            state = str(data.get("versionState") or "")
        if not files_known and isinstance(data, dict) and "files" in data:
            files_known = True
    except Exception:
        pass
    return files, depositor, state, files_known


def parse_metadatablock_names(payload: dict[str, Any]) -> list[str]:
    """Block names from a GET /api/metadatablocks payload. Never raises."""
    try:
        data = (payload or {}).get("data")
        items = data if isinstance(data, list) else []
        out = []
        for entry in items:
            if isinstance(entry, dict) and str(entry.get("name") or "").strip():
                out.append(str(entry["name"]).strip())
        return out
    except Exception:
        return []


def parse_metadatablock_display_names(payload: dict[str, Any]) -> dict[str, str]:
    """{block name: display name} from a GET /api/metadatablocks payload."""
    out: dict[str, str] = {}
    try:
        data = (payload or {}).get("data")
        items = data if isinstance(data, list) else []
        for entry in items:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "").strip()
            if not name:
                continue
            out[name] = str(entry.get("displayName") or name).strip() or name
    except Exception:
        pass
    return out


def parse_metadatablock_fields(payload: dict[str, Any]) -> list[dict[str, Any]]:  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
    """Return [{block, field, label, parent?, ...}] from a metadatablocks payload.

    Values are mostly strings, but ``is_subfield`` is a bool — hence Any.
    Field map lives under data.metadataFields on older servers and under
    data.fields (dict keyed by field name, or a list) on newer ones
    (verified on 6.8: {"name": ..., "fields": {"geographicCoverage":
    {"name": ..., "displayName": ...}}}). Missing/unknown shapes yield [].
    """
    out: list[dict[str, Any]] = []
    try:
        data = (payload or {}).get("data") or {}
        block = str(data.get("name") or "").strip()
        fields = data.get("metadataFields")
        if fields is None:
            fields = data.get("fields")
        fields = fields or {}
        if isinstance(fields, dict):
            for fname, spec in fields.items():
                if not isinstance(fname, str) or not fname.strip():
                    continue
                label = fname.strip()
                if isinstance(spec, dict):
                    label = str(spec.get("displayName") or spec.get("displayname") or label)
                block_name = block or "citation"
                out.append(
                    {
                        "block": block_name,
                        "field": fname.strip(),
                        "label": label.strip() or fname.strip(),
                    }
                )
                if isinstance(spec, dict):
                    sub = spec.get("childFields") or spec.get("subFields") or spec.get("fields")
                    if isinstance(sub, dict):
                        parent_label = label.strip() or fname.strip()
                        for sname, sspec in sub.items():
                            if not isinstance(sname, str) or not sname.strip():
                                continue
                            slabel = sname.strip()
                            if isinstance(sspec, dict):
                                slabel = str(
                                    sspec.get("title")
                                    or sspec.get("displayName")
                                    or sspec.get("displayname")
                                    or slabel
                                )
                            out.append(
                                {
                                    "block": block_name,
                                    "field": f"{fname.strip()}.{sname.strip()}",
                                    "label": slabel.strip() or sname.strip(),
                                    "parent": fname.strip(),
                                    "parent_label": parent_label,
                                    "is_subfield": True,
                                }
                            )
        elif isinstance(fields, list):
            for spec in fields:
                if not isinstance(spec, dict):
                    continue
                fname = str(spec.get("name") or spec.get("typeName") or "").strip()
                if not fname:
                    continue
                label = str(spec.get("displayName") or spec.get("displayname") or fname)
                block_name = block or "citation"
                out.append({"block": block_name, "field": fname, "label": label})
                sub = spec.get("childFields") or spec.get("subFields") or spec.get("fields")
                if isinstance(sub, dict):
                    parent_label = label.strip() or fname
                    for sname, sspec in sub.items():
                        if not isinstance(sname, str) or not sname.strip():
                            continue
                        slabel = sname.strip()
                        if isinstance(sspec, dict):
                            slabel = str(
                                sspec.get("title")
                                or sspec.get("displayName")
                                or sspec.get("displayname")
                                or slabel
                            )
                        out.append(
                            {
                                "block": block_name,
                                "field": f"{fname}.{sname.strip()}",
                                "label": slabel.strip() or sname.strip(),
                                "parent": fname,
                                "parent_label": parent_label,
                                "is_subfield": True,
                            }
                        )
    except Exception:
        pass
    return out


def parse_curation_status(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Parse a curationStatus response into {label, time, assigner} or None.

    Handles both the single-object form and the includeHistory=true array
    form (newest entry wins). Returns None when no label is assigned.
    """
    data = (payload or {}).get("data")
    if isinstance(data, list):
        if not data:
            return None
        # History is chronological; the current label is the last entry
        data = data[-1]
    if not isinstance(data, dict):
        return None
    label = str(data.get("label") or "").strip()
    if not label:
        return None
    return {
        "label": label,
        "time": str(data.get("createTime") or ""),
        "assigner": str(data.get("assigner") or data.get("user") or ""),
    }


# Values in the listCurationStates CSV that mean "no label assigned":
# "" (never set), "null"/"none"/"<none>" (bundle "dataset.curationstatus.none").
_CURATION_NONE_VALUES = frozenset({"", "null", "none", "<none>"})


def _clean_curation_value(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in _CURATION_NONE_VALUES else text


def parse_curation_states_csv(text: str) -> list[dict[str, Any]]:
    """Parse the superuser listCurationStates CSV report.

    Columns (by position — header labels are localized bundle strings):
    0 title-as-hyperlink formula =HYPERLINK("...persistentId=<PID>...","<title>"),
    1 draft creation date, 2 draft modification date, 3 assigned label
    ("" never set; none-ish when set-then-removed), 4 setter, 5 set time,
    6+ role-assignee columns (ignored).
    Returns [{persistent_id, title, creation_date, modification_date,
    label, label_time, assigner}]. Rows without an extractable PID are kept
    with persistent_id="" so callers can fall back to title matching.
    """
    import csv
    import io
    import re

    rows: list[dict[str, Any]] = []
    try:
        reader = csv.reader(io.StringIO(text or ""))
    except Exception:
        return rows
    link_re = re.compile(r'^=HYPERLINK\("(.+?)","(.*)"\)$', re.DOTALL)
    pid_re = re.compile(r"persistentId=([^\"]+)")
    for cells in reader:
        if not cells:
            continue
        first = (cells[0] or "").strip()
        pid = ""
        title = ""
        m = link_re.match(first)
        if m:
            url, title = m.group(1), m.group(2)
            pm = pid_re.search(url)
            if pm:
                pid = pm.group(1).strip()
            title = title.strip()
        else:
            # Header row or unexpected shape — keep the raw text as a
            # title candidate only if it cannot be the localized header.
            title = first

        def _cell(i: int, _cells: list[str] = cells) -> str:
            return _cells[i].strip() if len(_cells) > i else ""

        label = _clean_curation_value(_cell(3))
        rows.append(
            {
                "persistent_id": pid,
                "title": title,
                "creation_date": _cell(1),
                "modification_date": _cell(2),
                "label": label,
                # When no label is assigned the setter/time cells carry the
                # same none-ish bundle value — normalize those too.
                "label_time": _clean_curation_value(_cell(5)) if label else "",
                "assigner": _clean_curation_value(_cell(4)) if label else "",
            }
        )
    # Drop only the leading header row (no PID and no hyperlink). Other
    # PID-less rows are kept for title fallback per the docstring — a
    # format change to plain-title cells must not silently vanish.
    if rows and not rows[0]["persistent_id"] and not rows[0]["title"].startswith("=HYPERLINK"):
        rows = rows[1:]
    rows = [r for r in rows if r["persistent_id"] or r["title"]]
    return rows


def _summarize_file_entry(entry: Any) -> dict[str, str]:
    """Condense a compare-API file object to {name, path, id, kind}."""
    if not isinstance(entry, dict):
        return {"name": str(entry or ""), "path": "", "id": "", "kind": ""}
    name = str(entry.get("fileName") or entry.get("label") or entry.get("name") or "")
    path = str(entry.get("filePath") or entry.get("directoryLabel") or "")
    fid = str(entry.get("fileId") or entry.get("id") or "")
    kind = str(entry.get("type") or entry.get("contentType") or "")
    return {"name": name, "path": path, "id": fid, "kind": kind}


def parse_version_compare(payload: dict[str, Any]) -> dict[str, Any] | None:  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
    """Parse a versions/compare response into a normalized diff.

    Mirrors DatasetVersionDifference.compareVersionsAsJson: oldVersion /
    newVersion headers, metadataChanges (per block), TermsOfAccess, and
    filesAdded / filesRemoved / filesReplaced / fileChanges. Absent keys
    mean "no changes of that kind". Returns None when the payload has no
    usable data object.
    """
    data = (payload or {}).get("data")
    if not isinstance(data, dict):
        return None

    def _ver(key: str) -> dict[str, str]:
        v = data.get(key) or {}
        if not isinstance(v, dict):
            v = {}
        return {
            "number": str(v.get("versionNumber") or ""),
            "state": str(v.get("versionState") or ""),
            "note": str(v.get("versionNote") or ""),
            "updated": str(v.get("lastUpdatedDate") or ""),
        }

    def _field_changes(items: Any) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            out.append(
                {
                    "field": str(item.get("fieldName") or ""),
                    "old": "" if item.get("oldValue") is None else str(item.get("oldValue")),
                    "new": "" if item.get("newValue") is None else str(item.get("newValue")),
                }
            )
        return out

    metadata_changes: list[dict[str, str]] = []
    for block in data.get("metadataChanges") or []:
        if not isinstance(block, dict):
            continue
        block_name = str(block.get("blockName") or "")
        for change in _field_changes(block.get("changed")):
            change["block"] = block_name
            metadata_changes.append(change)

    toa = data.get("TermsOfAccess") or {}
    terms_changes = _field_changes((toa or {}).get("changed") if isinstance(toa, dict) else [])

    files_added = [_summarize_file_entry(f) for f in (data.get("filesAdded") or [])]
    files_removed = [_summarize_file_entry(f) for f in (data.get("filesRemoved") or [])]
    files_replaced = []
    for pair in data.get("filesReplaced") or []:
        if not isinstance(pair, dict):
            continue
        files_replaced.append(
            {
                "old": _summarize_file_entry(pair.get("oldFile")),
                "new": _summarize_file_entry(pair.get("newFile")),
            }
        )
    file_changes = []
    for entry in data.get("fileChanges") or []:
        if not isinstance(entry, dict):
            continue
        file_changes.append(
            {
                "file": str(entry.get("fileName") or ""),
                "id": str(entry.get("fileId") or ""),
                "changes": _field_changes(entry.get("changed")),
            }
        )

    total = (
        len(metadata_changes)
        + len(terms_changes)
        + len(files_added)
        + len(files_removed)
        + len(files_replaced)
        + sum(len(f["changes"]) for f in file_changes)
    )
    return {
        "old": _ver("oldVersion"),
        "new": _ver("newVersion"),
        "metadata_changes": metadata_changes,
        "terms_changes": terms_changes,
        "files_added": files_added,
        "files_removed": files_removed,
        "files_replaced": files_replaced,
        "file_changes": file_changes,
        "total_changes": total,
    }


def parse_dataset_versions(data: Any) -> list[dict[str, str]]:
    """Normalize a versions-list payload into version timeline entries.

    Each entry: {number ("1.0" or "Draft"), state, create_time,
    last_update, release_time, note}. Tolerates missing keys and
    non-list payloads (returns []).
    """
    out: list[dict[str, str]] = []
    if isinstance(data, dict):
        data = (
            [data]
            if any(k in data for k in ("versionState", "versionNumber", "createTime"))
            else []
        )
    items = data if isinstance(data, list) else []
    for v in items:
        if not isinstance(v, dict):
            continue
        state = str(v.get("versionState") or "").upper()
        num = v.get("versionNumber")
        minor = v.get("versionMinorNumber")
        try:
            number = "Draft" if state == "DRAFT" or num is None else f"{int(num)}.{int(minor or 0)}"
        except Exception:
            number = "Draft" if state == "DRAFT" else str(num or "")
        out.append(
            {
                "number": number,
                "state": state,
                "create_time": str(v.get("createTime") or ""),
                "last_update": str(v.get("lastUpdateTime") or ""),
                "release_time": str(v.get("releaseTime") or ""),
                "note": str(v.get("versionNote") or ""),
            }
        )
    return out
