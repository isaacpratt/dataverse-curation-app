"""The kit's number field: Lucide stepper, clamped, silent loads (dv-6vv).

``AppNumberField`` mirrors the QSpinBox API it replaces (value/setValue/
setRange) but its ``changed`` signal fires only on user action: the params
loader calls ``setValue`` by hand and relies on it staying quiet. The
native stepper is off; the minus/plus buttons are the kit's 32px ghost icon
buttons, disabled at the bounds.
"""

from typing import Any

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLineEdit

from ui.widgets import AppNumberField, make_number_field


def _press(btn: Any):
    btn.click()


def test_value_clamps_to_the_range(qapp):
    field = make_number_field(5, minimum=0, maximum=10)
    assert field.value() == 5
    field.setValue(99999)
    assert field.value() == 10, "setValue clamps to the maximum"
    field.setValue(-1)
    assert field.value() == 0, "setValue clamps to the minimum"


def test_each_button_steps_one_and_emits_changed_once(qapp):
    field = make_number_field(0, minimum=0, maximum=10)
    seen: list[Any] = []
    field.changed.connect(seen.append)
    _press(field._up)
    assert field.value() == 1
    assert seen == [1], "plus steps by one and emits once"
    _press(field._up)
    assert field.value() == 2
    assert seen == [1, 2]
    _press(field._down)
    assert field.value() == 1
    assert seen == [1, 2, 1]


def test_buttons_are_disabled_at_the_bounds(qapp):
    field = make_number_field(0, minimum=0, maximum=1)
    assert not field._down.isEnabled(), "decrease is off at the minimum"
    assert field._up.isEnabled()
    field.setValue(1)
    assert field._down.isEnabled()
    assert not field._up.isEnabled(), "increase is off at the maximum"


def test_typing_beyond_the_maximum_clamps_on_commit(qapp):
    field = make_number_field(0, minimum=0, maximum=100)
    seen: list[Any] = []
    field.changed.connect(seen.append)
    edit = field._spin.findChild(QLineEdit)
    assert edit is not None, "the spin box owns one line edit"
    edit.setFocus()
    for _ in range(3):
        qapp.processEvents()
    # The focus selects the old text, so the typed digits replace it and the
    # validator holds the value inside the range as it is typed.
    QTest.keyClicks(edit, "1000")
    assert field.value() == 100, "typing past the maximum clamps to the maximum"
    assert 100 in seen, "the clamped value reaches the caller through changed"


def test_set_value_does_not_emit(qapp):
    field = make_number_field(0, minimum=0, maximum=100)
    seen: list[Any] = []
    field.changed.connect(seen.append)
    field.setValue(42)
    assert field.value() == 42
    assert seen == [], "a programmatic load must not look like an edit"


def test_set_range_moves_the_bounds(qapp):
    field = make_number_field(5, minimum=0, maximum=10)
    field.setRange(0, 6)
    assert field.value() == 5
    field.setValue(9)
    assert field.value() == 6


def test_buttons_are_32px_squares_with_icons_and_names(qapp):
    field = make_number_field(0)
    for btn, a11y in ((field._down, "Decrease"), (field._up, "Increase")):
        assert btn.width() == 32
        assert btn.height() == 32, "the 32px hit-target floor"
        assert not btn.icon().isNull(), f"{a11y} wears a Lucide icon, not a fallback"
        assert btn.accessibleName() == a11y, f"{a11y} is named for a screen reader"


def test_the_field_is_an_app_number_field(qapp):
    assert isinstance(make_number_field(3), AppNumberField)
