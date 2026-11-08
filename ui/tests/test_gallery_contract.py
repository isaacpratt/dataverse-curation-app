"""Gallery and button-sheet contracts promoted from probe_buttons.

The probe verified two things that pytest could not see: (1) the
app-level button sheet and the scoped (widget-level) copy agree —
because a widget-level stylesheet replaces the app sheet subtree-wide,
so a drifted copy paints a different button inside styled panels;
(2) the gallery exhibits every kit kind with only kit object names.
This file is the same two checks, offscreen and in-repo.
"""

import re

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTextEdit,
    QTreeWidget,
)

from ui.theme import (
    BUTTON_OBJECTS,
    SURFACE_CARD,
    TEXT_PRIMARY,
    button_qss,
    contrast_ratio,
    global_qss,
)

_COMPARED = ("background", "color", "border-radius", "padding", "font-weight", "font-size")


def _blocks(qss: str) -> list[tuple[str, dict[str, str]]]:
    """Split a stylesheet into (selector, properties) pairs."""
    out: list[tuple[str, dict[str, str]]] = []
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", qss):
        selector = match.group(1).strip()
        props: dict[str, str] = {}
        for declaration in match.group(2).split(";"):
            if ":" not in declaration:
                continue
            key, _, value = declaration.partition(":")
            props[key.strip().lower()] = value.strip()
        out.append((selector, props))
    return out


def _base_rule(rules, object_name: str):
    """Find the plain (no pseudo-class) rule for a button object name."""
    for selector, props in rules:
        if selector.endswith(f"#{object_name}") and ":" not in selector:
            return props
    return None


def _scoped_rule(rules):
    """Find the plain rule for a bare QPushButton selector."""
    for selector, props in rules:
        if selector == "QPushButton" and ":" not in selector:
            return props
    return None


def test_app_and_scoped_button_sheets_agree():
    """Regression: the scoped copy drifted (white on pale disabled)."""
    for kind, object_name in BUTTON_OBJECTS.items():
        app_rule = _base_rule(_blocks(button_qss(kind)), object_name)
        scoped = _scoped_rule(_blocks(button_qss(kind, selector="QPushButton")))
        assert app_rule is not None, f"{kind}: the app rule must exist"
        assert scoped is not None, f"{kind}: the scoped rule must exist"
        for prop in _COMPARED:
            assert app_rule.get(prop) == scoped.get(prop), (
                f"{kind}: {prop} must agree between the two sheets "
                f"(app={app_rule.get(prop)!r} scoped={scoped.get(prop)!r})"
            )


def test_one_app_level_rule_per_button_kind():
    """One generator, one rule per kind — no second hand-written copy."""
    rules = _blocks(global_qss())
    for object_name in set(BUTTON_OBJECTS.values()):
        expected = f"QPushButton#{object_name}"
        count = sum(
            1
            for selector, _props in rules
            if selector == expected and ":" not in selector
        )
        assert count <= 1, f"{object_name}: found {count} app-level rules, want <= 1"


def test_disabled_primary_label_stays_readable():
    """The disabled face/clearance the two sheets once broke."""
    disabled = button_qss("primary", selector="QPushButton")
    face = text = None
    for selector, props in _blocks(disabled):
        if selector.endswith(":disabled"):
            face, text = props.get("background"), props.get("color")
    assert face is not None and text is not None, "primary needs a disabled state"
    assert contrast_ratio(text, face) >= 3.0, f"disabled pair fails 3:1 ({text} on {face})"
    assert contrast_ratio(text, SURFACE_CARD) >= 3.0
    assert text == TEXT_PRIMARY, "disabled label wears the primary text role"


def test_gallery_builds_and_exhibits_every_kind(qapp):
    """Promotion of probe_gallery: the kit on one page, offscreen."""
    from ui.gallery import build_gallery
    from ui.theme import SURFACE_PAGE

    window = build_gallery()
    window.show()
    for _ in range(3):
        qapp.processEvents()
    wanted = {
        "button": QPushButton,
        "line edit": QLineEdit,
        "combo": QComboBox,
        "multi-line input": QTextEdit,
        "plain-text view": QPlainTextEdit,
        "list": QListWidget,
        "check box": QCheckBox,
        "progress bar": QProgressBar,
        "table": QTableWidget,
        "tree": QTreeWidget,
    }
    for label, cls in wanted.items():
        assert window.findChildren(cls), f"the gallery must show a {label}"
    names = set(BUTTON_OBJECTS.values())
    buttons = window.findChildren(QPushButton)
    assert buttons, "the gallery must show buttons"
    unknown = sorted(
        {b.objectName() for b in buttons if b.objectName() and b.objectName() not in names}
    )
    assert not unknown, f"every gallery button wears a kit object name (unknown: {unknown})"
    assert SURFACE_PAGE in (window.styleSheet() or ""), (
        "the gallery paints the theme's page role"
    )
    assert any(not b.isEnabled() for b in buttons), (
        "the gallery shows a disabled button"
    )
    window.close()
