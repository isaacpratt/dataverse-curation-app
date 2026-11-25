"""Every exported kit builder must have a gallery exhibit (dv-ufu.3).

A builder that nobody paints is a component nobody can review. The test
parses source rather than instantiating widgets, so a new builder fails the
build the moment it is exported, before a view happens to use it.
"""

from __future__ import annotations

import ast
import pathlib

PACKAGE = pathlib.Path(__file__).resolve().parents[1]


def _kit_builders() -> set[str]:
    tree = ast.parse((PACKAGE / "widgets.py").read_text(encoding="utf-8"))
    exported: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        is_all = any(
            isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
        )
        if is_all and isinstance(node.value, (ast.List, ast.Tuple)):
            exported = {
                element.value
                for element in node.value.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            }
    return {name for name in exported if name.startswith("make_")}


def _gallery_names() -> set[str]:
    tree = ast.parse((PACKAGE / "gallery.py").read_text(encoding="utf-8"))
    return {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "ui.widgets"
        for alias in node.names
    }


def test_every_exported_builder_is_exhibited() -> None:
    builders = _kit_builders()
    assert builders, "the kit must export builders"
    missing = sorted(builders - _gallery_names())
    assert missing == [], f"kit builders with no gallery exhibit: {missing}"


def test_gallery_exhibits_are_called() -> None:
    """An import alone is not an exhibit: each builder must appear in a call."""
    source = (PACKAGE / "gallery.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    missing = sorted(_kit_builders() - called)
    assert missing == [], f"imported builders never rendered in the gallery: {missing}"
