"""Check scope: dataset or file, declared and routed by declaration (dv-p1d).

``extensions`` says which files a check reads; ``scope`` says what its
findings are about. These tests pin the declaration for every registered
check, the set of dataset-scoped ids, and — the point of the bead — that the
two axes are independent: a dataset-scoped check *with* extensions is routed
to the dataset list and never to a file entry.
"""

from pathlib import Path

import pytest

from engine.checks import registry
from engine.checks.base import Check, CheckResult
from engine.dispatcher import checks_for_file, dataset_level_checks
from engine.runner import list_planned_checks

# The dataset-scoped checks. Changing this set is a deliberate act: a check
# reclassified by accident (or a new class that forgot its scope) fails here.
DATASET_CHECKS = {
    "inventory.access",
    "inventory.extensions",
    "metadata.readme_sections",
    "metadata.var_coverage",
}


def test_every_registered_check_declares_a_scope():
    """No check may depend on the base class for its scope."""
    bad = sorted(
        f"{cls.__name__} ({check_id})"
        for check_id, cls in registry.items()
        if getattr(cls, "scope", None) not in ("dataset", "file")
    )
    assert not bad, f"checks without a declared scope: {bad}"


def test_every_check_declares_its_scope_in_its_own_body():
    """A declaration, not an inheritance: each class names its scope."""
    missing = sorted(cls.__name__ for cls in registry.values() if "scope" not in vars(cls))
    assert not missing, f"checks that inherit their scope instead of declaring it: {missing}"


def test_the_base_class_has_no_default_scope():
    """The default would be the silent answer this bead removed."""
    assert not hasattr(Check, "scope"), "Check.scope must have no default"


def test_the_registry_refuses_a_check_without_a_scope():
    """Registration is where the contract bites (a new check cannot slip in)."""
    from engine.checks import register_checks

    class _Undecided(Check):
        check_id = "test.no_scope"

        def run(self, files):  # pragma: no cover - never dispatched
            return []

    stub = type("_Stub", (), {"_Undecided": _Undecided})
    target: dict = {}
    with pytest.raises(TypeError, match="must declare scope"):
        register_checks(stub, target)
    assert "test.no_scope" not in target, "the half-built registry is untouched"


def test_the_dataset_check_set_is_exactly_these_four():
    """A re-classification has to be deliberate, not a side effect."""
    assert {cls.check_id for cls in dataset_level_checks()} == DATASET_CHECKS


def test_no_file_check_is_dataset_scoped_and_the_other_way_round():
    """Every non-dataset check is file-scoped, and every file check has extensions."""
    for check_id, cls in registry.items():
        if check_id in DATASET_CHECKS:
            continue
        assert cls.scope == "file", check_id
        assert cls.extensions, f"{check_id} is file-scoped but reads no file type"


def test_a_dataset_scope_with_extensions_never_reaches_a_file_entry():
    """The two axes are independent: extensions no longer imply per-file."""
    from engine.checks import registry as check_registry

    class _CrossFile(Check):
        check_id = "test.cross_file_csv"
        extensions = frozenset({".csv"})
        scope = "dataset"

        def run(self, files):
            return [CheckResult(self.check_id, "info", True, "one finding for the set")]

    # dispatcher imported the same dict object, so mutating it here is visible.
    check_registry["test.cross_file_csv"] = _CrossFile
    try:
        assert "test.cross_file_csv" in {c.check_id for c in dataset_level_checks()}
        assert _CrossFile not in checks_for_file(Path("data.csv")), (
            "a dataset-scoped check with matching extensions must not run per file"
        )
        planned = list_planned_checks([Path("data.csv")])
        entry = next(p for p in planned if p["check_id"] == "test.cross_file_csv")
        assert entry["scope"] == "dataset"
        assert entry["file_types"] == "dataset-level"
    finally:
        check_registry.pop("test.cross_file_csv", None)


def test_list_planned_checks_reports_both_scopes():
    planned = list_planned_checks([Path("data.csv"), Path("notes.txt")])
    scopes = {p["check_id"]: p["scope"] for p in planned}
    for check_id in DATASET_CHECKS:
        assert scopes[check_id] == "dataset", check_id
    assert scopes["format.csv"] == "file"
    assert scopes["format.text"] == "file"
    assert all(p["scope"] in ("dataset", "file") for p in planned)
