"""Review configuration: Borealis fields — the Author block nests (dv-bhv).

The catalog parser and the field tree must list the citation Author's
children (Name, Affiliation, Identifier Type, Identifier) as they appear
in Borealis, and the McMaster ORCID rule must target the identifier
subfield — not a bolt-on handler on the composite.
"""

import json
from pathlib import Path


def _citation_group(rc):
    tree = rc._field_tree
    for i in range(tree.topLevelItemCount()):
        top = tree.topLevelItem(i)
        if top.text(0).lower().startswith("citation"):
            return top
    return None


def _find_child(item, text):
    for i in range(item.childCount()):
        child = item.child(i)
        if child.text(0) == text:
            return child
    return None


def test_author_child_rows_nest_under_author_group(win):
    win._show_review_config()
    rc = win._review_config
    top = _citation_group(rc)
    assert top is not None
    author = _find_child(top, "Author")
    assert author is not None, "Author must appear as a nested group row"
    labels = [author.child(i).text(0) for i in range(author.childCount())]
    assert "Name" in labels and "Affiliation" in labels
    assert "Identifier Type" in labels
    # McMaster's ORCID rule lives on the identifier subfield.
    assert "ORCiD for authors" in labels


def test_orcid_rule_targets_the_identifier_subfield(win):
    win._show_review_config()
    rc = win._review_config
    rs = rc._current_ruleset()
    rules = rs.get("field_rules") or []
    orcid = [r for r in rules if str(r.get("handler") or "") == "orcid"]
    assert orcid, "the built-in ruleset must carry an ORCID rule"
    assert orcid[0]["field"] == "author.authorIdentifier"


def test_parse_metadatablock_fields_fixture_roundtrip():
    from dataverse_client import parse_metadatablock_fields

    repo = Path(__file__).resolve().parents[2]
    payload = json.loads(
        (repo / "engine" / "tests" / "fixtures" / "metadatablocks_citation.json").read_text(
            encoding="utf-8"
        )
    )
    rows = parse_metadatablock_fields(payload)
    fields = {r["field"] for r in rows}
    assert "author.authorName" in fields
    assert "author.authorIdentifier" in fields
