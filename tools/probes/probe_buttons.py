"""Probe: one button system.

A widget-level stylesheet replaces the application sheet for that
subtree, so every critical action carries its own copy of the button
rules. That copy has to be the *same* rules: the app-level sheet and
the scoped sheet come from one generator, and this probe checks they
still agree - background, colour, radius, padding, weight and size.

It also checks the contrast of the disabled primary label, which is
where the two sheets used to drift (the app rule had no disabled state
at all, and the scoped copy painted white text on a pale blue face).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import Report, boot  # noqa: E402

# The properties two rules must agree on for the button to look the
# same in both places.
_COMPARED = ("background", "color", "border-radius", "padding", "font-weight", "font-size")


def blocks(qss: str) -> list[tuple[str, dict[str, str]]]:
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


def base_rule(rules: list[tuple[str, dict[str, str]]], object_name: str):
    """Find the plain (no pseudo-class) rule for a button object name."""
    for selector, props in rules:
        if selector.endswith(f"#{object_name}") and ":" not in selector:
            return props
    return None


def scoped_rule(rules: list[tuple[str, dict[str, str]]]):
    """Find the plain rule for a bare QPushButton selector."""
    for selector, props in rules:
        if selector == "QPushButton" and ":" not in selector:
            return props
    return None


def main() -> int:
    app, _cfg = boot()
    report = Report("buttons")

    from ui.theme import (
        BUTTON_OBJECTS,
        SURFACE_CARD,
        TEXT_PRIMARY,
        button_qss,
        contrast_ratio,
        global_qss,
    )

    app_sheet = global_qss()

    for kind, object_name in BUTTON_OBJECTS.items():
        app_rule = base_rule(blocks(button_qss(kind)), object_name)
        scoped = scoped_rule(blocks(button_qss(kind, selector="QPushButton")))
        report.check(app_rule is not None, f"{kind}: the app rule exists")
        report.check(scoped is not None, f"{kind}: the scoped rule exists")
        if not app_rule or not scoped:
            continue
        for prop in _COMPARED:
            report.check(
                app_rule.get(prop) == scoped.get(prop),
                f"{kind}: {prop} agrees between the two sheets",
                f"app={app_rule.get(prop)!r} scoped={scoped.get(prop)!r}",
            )

    # The app sheet must not carry a second, hand-written copy of a
    # button rule: one generator, one rule per kind.
    for object_name in set(BUTTON_OBJECTS.values()):
        count = app_sheet.count(f"QPushButton#{object_name} ")
        report.check(
            count <= 1,
            f"{object_name}: one app-level rule",
            f"found {count}",
        )

    # The disabled primary label has to stay readable.
    disabled = button_qss("primary", selector="QPushButton")
    face = None
    text = None
    for selector, props in blocks(disabled):
        if selector.endswith(":disabled"):
            face = props.get("background")
            text = props.get("color")
    report.check(face is not None and text is not None, "the primary button has a disabled state")
    if face and text:
        ratio = contrast_ratio(text, face)
        report.check(
            ratio >= 3.0,
            "the disabled primary label clears 3:1",
            f"{ratio:.2f}:1 ({text} on {face})",
        )
        ratio_on_card = contrast_ratio(text, SURFACE_CARD)
        report.check(
            ratio_on_card >= 3.0,
            "the disabled primary label clears 3:1 on a card",
            f"{ratio_on_card:.2f}:1",
        )
        report.check(
            text == TEXT_PRIMARY,
            "the disabled primary label wears the primary text role",
            f"{text}",
        )

    return report.finish()


if __name__ == "__main__":
    raise SystemExit(main())
