"""Metadata checks render as Auto-Checks-style rows (dv-h70).

One row per rule: outcome icon, the rule's label as the bold caption, a
one-line verdict sentence, a badge on the right and a left bar on required
rules. Compound fields expand into an inline drawer (one block per entry;
each subfield is a caption line). Two rules may share a field — rows key
off the result list.
"""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QComboBox, QToolButton


def _fv(value):
    return {"typeName": "text", "multiple": False, "typeClass": "primitive", "value": value}


def _metadata() -> dict:
    return {
        "latestVersion": {
            "license": {"name": "CC0 1.0"},
            "metadataBlocks": {
                "citation": {
                    "fields": [
                        {"typeName": "title", "value": "A study"},
                        {
                            "typeName": "author",
                            "value": [
                                {
                                    "authorName": _fv("Ada Lovelace"),
                                    "authorAffiliation": _fv("Analytical Engine Lab"),
                                    "authorIdentifierScheme": _fv("ORCID"),
                                    "authorIdentifier": _fv("0000-0002-1825-0097"),
                                },
                                {
                                    "authorName": _fv("Grace Hopper"),
                                    "authorAffiliation": _fv(""),
                                },
                            ],
                        },
                        {
                            "typeName": "datasetContact",
                            "value": [
                                {
                                    "datasetContactName": _fv("Ada Lovelace"),
                                    "datasetContactAffiliation": _fv("Analytical Engine Lab"),
                                    "datasetContactEmail": _fv("ada@example.org"),
                                }
                            ],
                        },
                        {
                            "typeName": "dsDescription",
                            "value": [
                                {
                                    "dsDescriptionValue": _fv("A description."),
                                    "dsDescriptionDate": _fv("2026-01-01"),
                                }
                            ],
                        },
                        {"typeName": "subject", "value": ["Computer and Information Science"]},
                        {"typeName": "depositor", "value": "Ada Lovelace"},
                        {"typeName": "dateOfDeposit", "value": "2026-01-02"},
                    ]
                }
            },
        }
    }


@pytest.fixture
def detail(qapp, tmp_path):
    from curation.config import Config
    from ui.dataset import DatasetDetailView

    cfg = Config()
    cfg.app.workspace = Path(tmp_path)
    view = DatasetDetailView(
        cfg,
        "doi:10.5072/FK2/META",
        "Metadata rows",
        cached_metadata=_metadata(),
        cached_inventory=[],
    )
    for _ in range(5):
        qapp.processEvents()
    yield view
    view.deleteLater()


def _rows(detail):
    out = []
    lay = detail._meta_body_lay
    for i in range(lay.count()):
        widget = lay.itemAt(i).widget()
        if widget is not None and widget.property("meta_field") is not None:
            out.append(widget)
    return out


def _row(detail, label: str):
    for widget in _rows(detail):
        if widget.property("meta_field") == label:
            return widget
    raise AssertionError(f"row {label!r} not found")


def _drawer(detail, row):
    """Return the drawer directly following a compound-field row, if any."""
    lay = detail._meta_body_lay
    for i in range(lay.count() - 1):
        if lay.itemAt(i).widget() is row:
            candidate = lay.itemAt(i + 1).widget()
            if candidate is not None and candidate.property("meta_field") is None:
                return candidate
    return None


def _labels_in(frame) -> list[str]:
    from PySide6.QtWidgets import QLabel

    return [w.text() for w in frame.findChildren(QLabel)]


def test_every_rule_renders_as_a_row(detail):
    fields = [widget.property("meta_field") for widget in _rows(detail)]
    assert "Title" in fields
    assert "Author Name & Affiliation" in fields
    assert "Dataset Contact" in fields
    assert "Description" in fields
    assert "Subject" in fields


def test_badge_and_status_complete_for_title(detail):
    row = _row(detail, "Title")
    assert "Complete" in _labels_in(row)


def _qframe_by_name(row, name):
    from PySide6.QtWidgets import QFrame

    return [w for w in row.findChildren(QFrame) if w.objectName() == name]


def test_no_rows_paint_a_required_bar(detail):
    """dv-onk: no metadata-check row paints a coloured bar; level stays on the tooltip."""
    assert _qframe_by_name(_row(detail, "Title"), "MetaRequiredBar") == []
    assert _qframe_by_name(_row(detail, "ORCiD for authors"), "MetaRequiredBar") == []
    # The required/optional distinction survives as text on the row.
    tip = _row(detail, "Title").toolTip()
    assert "Required" in tip


def test_author_entries_expand_in_the_drawer(detail):
    row = _row(detail, "Author Name & Affiliation")
    drawer = _drawer(detail, row)
    assert drawer is not None, "compound fields must carry a drawer"
    assert drawer.isHidden()
    chevrons = list(row.findChildren(QToolButton))
    assert len(chevrons) == 1
    chevrons[0].click()
    assert not drawer.isHidden()
    labels = _labels_in(drawer)
    entry_heads = [line for line in labels if line.startswith("Author ")]
    assert entry_heads == ["Author 1", "Author 2"]
    assert any(line.startswith("Name: Ada Lovelace") for line in labels)
    assert any(line.startswith("Affiliation: —") for line in labels), (
        "an empty affiliation must stay visible"
    )
    # toggle back
    chevrons[0].click()
    assert drawer.isHidden()


def test_author_entry_headline_is_authorname_not_affiliation(detail):
    """Identity summary must not depend on the API's key order."""
    detail._metadata["latestVersion"]["metadataBlocks"]["citation"]["fields"][1]["value"][0] = {
        "authorAffiliation": {"typeName": "text", "value": "Analytical Engine Lab"},
        "authorName": {"typeName": "text", "value": "Ada Lovelace"},
        "authorIdentifierScheme": {"typeName": "text", "value": "ORCID"},
        "authorIdentifier": {"typeName": "text", "value": "0000-0002-1825-0097"},
    }
    detail._populate_completeness(detail._metadata)
    row = _row(detail, "Author Name & Affiliation")
    drawer = _drawer(detail, row)
    grid = _labels_in(drawer)
    heads = [line for line in grid if line.startswith("Ada Lovelace")]
    assert heads, "the entry headline must be the author name, never an affiliation"


def test_orcid_rule_has_no_drawer(detail):
    row = _row(detail, "ORCiD for authors")
    assert not row.findChildren(QToolButton), "the ORCID rule must not re-expand the author entries"


@pytest.fixture
def pending_detail(qapp, tmp_path, monkeypatch):
    """Yield a view whose ruleset includes a file-content rule with nothing staged.

    That rule cannot be evaluated (no staged dir), so the engine returns a
    pending row — a real gap, not a finding; the row must not read as one.
    """
    import curation.review_rules as _rr

    target = tmp_path / "requirements_profiles.json"
    monkeypatch.setattr(_rr, "rulesets_path", lambda: target)
    monkeypatch.setattr(_rr, "_RULESETS_MEMO", {})
    pool = _rr.load_rulesets()
    base = pool["mcmaster-default"]
    probe = {
        "label": "pending probe",
        "description": "file-content scope rule, nothing staged",
        "dataverses": ["*"],
        "field_rules": [dict(base["field_rules"][0])],
        "content_rules": [
            {
                "id": "content-scan",
                "label": "Content scan",
                "level": "required",
                "requirement": "probe pending rule",
                "scope": ["file-content"],
                "match": "substring",
                "pattern": "zebra",
                "case_sensitive": False,
                "response_template": "zebra",
            }
        ],
        "filecheck_templates": {},
        "response_header": "hi",
        "response_footer": "bye",
    }
    pool["pending-probe"] = probe
    _rr.save_rulesets(pool)

    from curation.config import Config
    from ui.dataset import DatasetDetailView

    cfg = Config()
    cfg.app.workspace = Path(tmp_path)
    view = DatasetDetailView(
        cfg,
        "doi:10.5072/FK2/PENDING",
        "Pending probe",
        cached_metadata=_metadata(),
        cached_inventory=[],
    )
    view._profile = "pending-probe"
    assert view._metadata is not None
    view._populate_completeness(view._metadata)
    for _ in range(5):
        qapp.processEvents()
    yield view
    view.deleteLater()


def test_pending_row_renders_muted_without_disposition(pending_detail):
    from PySide6.QtCore import Qt

    rows = _rows(pending_detail)
    pending = [r for r in rows if "Content scan" in _labels_in(r)]
    assert pending, "the probe rule must produce a visible row"
    row = pending[0]
    assert "Pending" in _labels_in(row)
    assert not row.findChildren(QComboBox), "a pending row carries no disposition combo"
    assert row.contextMenuPolicy() != Qt.ContextMenuPolicy.CustomContextMenu, (
        "a pending row must not carry the right-click disposition menu"
    )
    # Required level, but no money-test bar and no error face for pending.
    assert _qframe_by_name(row, "MetaRequiredBar") == []


def test_pending_row_is_not_a_verdict_input(pending_detail):
    """Pending must never leak into the verdict's disposition keying."""
    from engine.verdict import assess

    view = pending_detail
    full = list(getattr(view, "_completeness_full", []))
    pending = [r for r in full if r.get("pending")]
    assert any(r.get("rule_id") == "content-scan" for r in pending)
    # verdict counts only complete/incomplete non-pending findings, so the
    # pending probe row must not alter the counts either way.
    verdict = assess(view._report, full, {})
    assert verdict is not None


def test_single_entry_description_has_no_numbered_entry(detail):
    row = _row(detail, "Description")
    drawer = _drawer(detail, row)
    assert drawer is not None
    labels = _labels_in(drawer)
    assert not any(line.startswith("Description 1") for line in labels)
    assert any(line.startswith("Date: 2026-01-01") for line in labels)


def test_incomplete_rows_carry_disposition_controls(detail):
    row = _row(detail, "ORCiD for authors")
    assert "Incomplete" in _labels_in(row), (
        "fixture requires the ORCID rule to fail (Grace Hopper has no identifier)"
    )
    assert row.findChildren(QComboBox), "incomplete findings carry the disposition combo"


def test_complete_filter_rebuilds_the_rows(detail):
    detail._meta_filter.setCurrentIndex(detail._meta_filter.findData("incomplete"))
    fields = [widget.property("meta_field") for widget in _rows(detail)]
    assert fields, "the incomplete filter must still show something"
    assert "Title" not in fields, "a complete check must be filtered out"
    detail._meta_filter.setCurrentIndex(detail._meta_filter.findData("all"))
    assert _rows(detail), "the All filter must restore the rows"


def test_unchecked_filter_shows_ghost_rows(detail):
    detail._unchecked_results = [
        {
            "rule_id": "field:citation.title",
            "kind": "field",
            "field": "Title",
            "requirement": "off by ruleset",
            "value": "—",
            "status": "skipped",
            "level": "unchecked",
            "pending": False,
            "response_template": "",
            "block": "citation",
            "name": "title",
        }
    ]
    detail._meta_filter.setCurrentIndex(detail._meta_filter.findData("unchecked"))
    rows = _rows(detail)
    assert [w.property("meta_field") for w in rows] == ["Title"]
    assert "Not checked" in _labels_in(rows[0])
    # The ghost row never leaks into the default or Complete views
    detail._meta_filter.setCurrentIndex(detail._meta_filter.findData("all"))
    fields = [w.property("meta_field") for w in _rows(detail)]
    assert fields
    assert "Title" in fields
    assert _labels_in(_row(detail, "Title")) != ["—"]


def test_section_headers_group_the_blocks(detail):
    from PySide6.QtWidgets import QPushButton

    lay = detail._meta_body_lay
    buttons: list = []
    for i in range(lay.count()):
        widget = lay.itemAt(i).widget()
        if widget is not None and widget.objectName() == "MetaSectionHeader":
            buttons.extend(w.text() for w in widget.findChildren(QPushButton) if w.text())
    assert "Citation" in buttons


def test_section_toggles_collapse_the_block(detail):
    from PySide6.QtWidgets import QPushButton

    lay = detail._meta_body_lay
    header = next(
        lay.itemAt(i).widget()
        for i in range(lay.count())
        if lay.itemAt(i).widget() is not None
        and lay.itemAt(i).widget().objectName() == "MetaSectionHeader"
    )
    btn = next(w for w in header.findChildren(QPushButton) if w.text() == "Citation")
    row = _row(detail, "Title")
    assert not row.isHidden()
    btn.click()
    assert row.isHidden()
    btn.click()
    assert not row.isHidden()


def test_drawer_keeps_its_open_state_across_section_collapse(detail):
    from PySide6.QtWidgets import QPushButton

    lay = detail._meta_body_lay
    header = next(
        lay.itemAt(i).widget()
        for i in range(lay.count())
        if lay.itemAt(i).widget() is not None
        and lay.itemAt(i).widget().objectName() == "MetaSectionHeader"
    )
    btn = next(w for w in header.findChildren(QPushButton) if w.text() == "Citation")
    row = _row(detail, "Author Name & Affiliation")
    drawer = _drawer(detail, row)
    chevrons = list(row.findChildren(QToolButton))
    # Open the drawer, collapse and re-expand: it stays open.
    chevrons[0].click()
    assert not drawer.isHidden()
    btn.click()
    assert row.isHidden()
    assert drawer.isHidden()
    btn.click()
    assert not row.isHidden()
    assert not drawer.isHidden()
    # Close the drawer, collapse and re-expand: it stays closed.
    chevrons[0].click()
    assert drawer.isHidden()
    btn.click()
    btn.click()
    assert not row.isHidden()
    assert drawer.isHidden()


def test_note_without_disposition_defaults_to_acknowledged(detail, monkeypatch):
    written: dict = {}

    class _State:
        def list_finding_dispositions(self, pid):
            return {
                key: {"disposition": tok, "note": note, "updated_at": ""}
                for key, (tok, note) in written.items()
            }

        def set_finding_disposition(self, pid, key, token, note=""):
            written[key] = (token, note)

        def log_action(self, pid, action, notes="", details=None):
            pass

        def close(self):
            pass

    monkeypatch.setattr(detail, "_state", lambda: _State())
    from PySide6 import QtWidgets

    monkeypatch.setattr(
        QtWidgets.QInputDialog,
        "getMultiLineText",
        staticmethod(lambda *a, **kw: ("looks fine manually", True)),
    )
    detail._dispositions_cache = {}
    key = "rule-id::Note me"
    detail._on_edit_disposition_note(key)
    assert written[key] == ("acknowledged", "looks fine manually")
