"""Guard: the dataset detail page is assembled from focused sections.

`ui/dataset_detail.py` was one 4,400-line module (dv-hcg.22).  It is now
a package of sections over a shared contract (`ui/dataset/state.py`).
These tests pin the shape of that split, so a later change cannot quietly
undo it:

- the facade really is assembled from every section;
- every call the contract declares is implemented by a section, so a
  stub in the contract can never swallow a call at runtime;
- no section module has grown back into a monolith.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from ui.dataset import DatasetDetailView
from ui.dataset.state import DetailState

_PACKAGE = pathlib.Path(__file__).resolve().parents[1] / "dataset"

_SECTIONS = (
    "WorkflowSection",
    "MetadataSection",
    "MetadataLoadSection",
    "ChecksSection",
    "FilesSection",
    "VersionsSection",
    "LogRail",
    "ResponseSection",
    "ActionsSection",
    "HeaderSection",
)


def _contract_stubs() -> list[str]:
    """Return the contract methods that only raise — the cross-section API."""
    tree = ast.parse((_PACKAGE / "state.py").read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    out: list[str] = []
    for node in cls.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        body = [n for n in node.body if not isinstance(n, ast.Expr)]
        if len(body) == 1 and isinstance(body[0], ast.Raise):
            out.append(node.name)
    return out


def test_the_facade_is_assembled_from_every_section():
    """Each section must be a base of the facade, or its methods vanish."""
    bases = {base.__name__ for base in DatasetDetailView.__mro__}
    missing = [name for name in _SECTIONS if name not in bases]
    assert missing == [], f"sections missing from the facade: {missing}"
    assert issubclass(DatasetDetailView, DetailState)


def test_every_contract_call_is_implemented_by_a_section():
    """A contract stub that nobody implements would silently swallow a call."""
    stubs = _contract_stubs()
    assert stubs, "the contract should declare the cross-section API"
    unimplemented = [
        name for name in stubs if getattr(DatasetDetailView, name) is DetailState.__dict__[name]
    ]
    assert unimplemented == [], f"contract calls with no implementation: {unimplemented}"


@pytest.mark.parametrize(
    "module",
    sorted(p.name for p in _PACKAGE.glob("*.py") if p.name != "__init__.py"),
)
def test_no_section_module_is_a_monolith(module: str):
    """The split's point: every section is a readable slice of the page."""
    path = _PACKAGE / module
    lines = len(path.read_text(encoding="utf-8").splitlines())
    assert lines <= 1000, f"{module} grew to {lines} lines"
