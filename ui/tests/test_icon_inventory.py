"""Icon inventory: every mark resolves to a bundled Lucide asset (dv-kvb).

A UI mark that stands for an action, a state or a direction is a bundled
Lucide glyph tinted from a theme role. Nothing else may stand in for one:
not a text character (``× ⋯ ✓ ▸ ▾``), not a hand-drawn path. This file is
the guard:

- every name passed to ``icon``/``icon_label``/``role_icon`` anywhere in
  ``ui/``, plus every role in ``ui.icons.ICON_ROLES``, has an asset;
- the assets added for this bead exist and load to a non-null QIcon;
- no button's entire text is an icon character;
- an unresolved name warns once instead of returning a silent null icon.
"""

import ast
import pathlib
import re

import pytest

UI_DIR = pathlib.Path(__file__).resolve().parent.parent
ASSET_DIR = UI_DIR / "assets" / "lucide"

# The icon-call aliases the views use (``from ui.icons import icon as _x``).
_KIT_ALIASES = {"icon", "icon_label", "role_icon", "file_icon", "status_icon"}

# A character that stands in for a mark when it is a button's whole text.
_GLYPHS = set("×⋯✓✔▸▾›‹→←⋮●○–—")


def _ui_files() -> list[pathlib.Path]:
    return sorted([*UI_DIR.glob("*.py"), *UI_DIR.glob("dataset/*.py"), *UI_DIR.glob("tests/*.py")])


def _icon_names(path: pathlib.Path) -> set[str]:
    """Every plain string literal passed to an icon call in one module."""
    names: set[str] = set()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return names
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = ""
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name not in _KIT_ALIASES:
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            names.add(first.value)
    return names


def _asset_exists(name: str) -> bool:
    return (ASSET_DIR / f"{name}.svg").is_file()


def test_every_icon_name_in_the_app_is_bundled():
    """No call site names an asset that is not there."""
    missing = sorted(
        f"{path.name}: {name}"
        for path in _ui_files()
        if path.name != "test_icon_inventory.py"
        for name in _icon_names(path)
        if name and not _asset_exists(name)
    )
    assert not missing, "icon names with no bundled asset:\n  " + "\n  ".join(missing)


def test_every_role_points_at_a_bundled_glyph():
    """The role table is the one list the docs, gallery and tests share."""
    from ui.icons import ICON_ROLES

    assert ICON_ROLES, "the role table is empty"
    missing = sorted(
        f"{role} -> {glyph}" for role, glyph in ICON_ROLES.items() if not _asset_exists(glyph)
    )
    assert not missing, "roles with no bundled glyph:\n  " + "\n  ".join(missing)


@pytest.mark.parametrize(
    "name", ["panel-right-close", "panel-right-open", "ellipsis", "arrow-left"]
)
def test_the_new_assets_exist_and_load(qapp, name):
    from ui.icons import icon

    assert _asset_exists(name), f"ui/assets/lucide/{name}.svg is missing"
    assert not icon(name, size=20).isNull(), f"{name} renders nothing"


def test_every_bundled_asset_renders(qapp):
    """No junk file and no asset that silently fails to draw."""
    from ui.icons import icon

    bad = sorted(path.stem for path in ASSET_DIR.glob("*.svg") if icon(path.stem, size=16).isNull())
    assert not bad, f"assets that do not render: {bad}"


def _button_texts(path: pathlib.Path) -> list[tuple[int, str]]:
    """(line, text) for buttons whose whole label is a glyph character.

    Only constructor arguments are scanned: ``setText`` is how a builder
    writes its last-resort fallback for an environment where the SVG cannot
    be drawn at all, which the icon contract allows.
    """
    out: list[tuple[int, str]] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return out
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        first = node.args[0]
        if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
        if "button" not in name.lower():
            continue
        text = first.value.strip()
        if text and set(text) <= _GLYPHS:
            out.append((node.lineno, text))
    return out


def test_no_button_is_a_text_character():
    """A glyph character is never a button's label: a Lucide icon is."""
    leaves = sorted(
        f"{path.name}:{line}: {text!r}"
        for path in _ui_files()
        if path.name != "test_icon_inventory.py"
        for line, text in _button_texts(path)
    )
    assert not leaves, (
        "buttons whose whole label is an icon character (use "
        "ui.icons.icon / make_icon_button):\n  " + "\n  ".join(leaves)
    )


def test_an_unknown_name_warns_instead_of_failing_silently(qapp):
    """The missing-name warning is the regression guard's other half."""
    from ui.icons import icon

    with pytest.warns(RuntimeWarning, match="not bundled"):
        result = icon("no-such-name-for-the-inventory-test", size=16)
    assert result.isNull()
    # Once per name: a second call stays quiet (it is cached, not re-warned).
    import warnings as _warnings

    with _warnings.catch_warnings():
        _warnings.simplefilter("error")
        icon("no-such-name-for-the-inventory-test", size=16)


def test_the_gallery_shows_every_role_glyph(gallery_without_app_theme, qapp):
    """The icon sheet is the place a missing or ugly mark shows up."""
    from PySide6.QtWidgets import QLabel

    from ui.gallery import build_gallery
    from ui.icons import ICON_ROLES

    window = build_gallery()
    window.show()
    try:
        for _ in range(3):
            qapp.processEvents()
        tiles = window.findChildren(QLabel)
        captions = {
            str(tile.property("glyph_caption")) for tile in tiles if tile.property("glyph_caption")
        }
        expected = set(ICON_ROLES.values())
        assert expected <= captions, f"the icon sheet does not show {sorted(expected - captions)}"
        for name in expected:
            assert re.fullmatch(r"[a-z0-9-]+", name), name
    finally:
        window.close()
        window.deleteLater()
