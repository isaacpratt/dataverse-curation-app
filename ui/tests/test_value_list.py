"""The kit's multi-value field: one chip per phrase, added one at a time (dv-6vv).

``AppValueList`` takes a single phrase at a time - Enter in the field or the
plus button adds it - shows each entry as its own chip with a Lucide x that
deletes just that entry, wraps the chips when narrow, and ignores blanks and
case-insensitive duplicates. ``setValues`` replaces the list wholesale with
one ``changed``, never one per item.
"""

from typing import Any, cast

from PySide6.QtWidgets import QLineEdit

from ui.widgets import AppValueList, make_value_list


def _enter(field: Any, text: Any):
    edit = field._field
    edit.setText(text)
    edit.returnPressed.emit()


def test_add_one_phrase_per_enter_and_per_click(qapp):
    field = make_value_list()
    seen: list[Any] = []
    field.changed.connect(seen.append)
    _enter(field, "CC0 1.0")
    assert field.values() == ["CC0 1.0"]
    assert seen == [["CC0 1.0"]], "one emission per added phrase"
    _enter(field, "CC BY 4.0")
    assert field.values() == ["CC0 1.0", "CC BY 4.0"]
    assert len(seen) == 2
    # The plus button adds too, and clears the field for the next phrase.
    field._field.setText("MIT")
    field._add_btn.click()
    assert field.values() == ["CC0 1.0", "CC BY 4.0", "MIT"]
    assert field._field.text() == ""


def test_blanks_and_duplicates_are_ignored(qapp):
    field = make_value_list(["CC0 1.0"])
    seen: list[Any] = []
    field.changed.connect(seen.append)
    _enter(field, "   ")
    _enter(field, "")
    (_enter(field, "cc0 1.0"),)  # case-insensitive duplicate
    (_enter(field, "  CC0 1.0  "),)  # duplicate after trimming
    assert field.values() == ["CC0 1.0"]
    assert seen == [], "a blank or a duplicate never reaches the caller"


def test_deleting_a_chip_removes_only_that_entry(qapp):
    from PySide6.QtWidgets import QPushButton

    field = make_value_list(["CC0 1.0", "CC BY 4.0", "MIT"])
    seen: list[Any] = []
    field.changed.connect(seen.append)
    chips = cast(list[Any], field._flow.chips())
    assert [c.value for c in chips] == ["CC0 1.0", "CC BY 4.0", "MIT"]
    # Each chip's only button is its Lucide x delete.
    middle = chips[1]
    delete = middle.findChildren(QPushButton)[0]
    delete.click()
    assert field.values() == ["CC0 1.0", "MIT"], "only the deleted chip is gone"
    assert seen == [["CC0 1.0", "MIT"]]


def test_values_preserve_display_order(qapp):
    field = make_value_list(["zeta", "alpha", "Mid"])
    assert field.values() == ["zeta", "alpha", "Mid"]


def test_set_values_replaces_wholesale_without_per_item_signals(qapp):
    field = make_value_list(["one", "two", "three"])
    seen: list[Any] = []
    field.changed.connect(seen.append)
    field.setValues(["alpha", "beta"])
    assert field.values() == ["alpha", "beta"]
    assert seen == [["alpha", "beta"]], "one signal for the whole replace"
    field.setValues([])
    assert field.values() == []
    assert len(seen) == 2


def test_the_empty_state_caption_names_the_list(qapp):
    field = make_value_list(empty_text="No phrases yet")
    empty = field._empty
    assert empty is not None, "the caption is built when empty_text is given"
    field.show()
    for _ in range(3):
        qapp.processEvents()
    assert empty.isVisible(), "the caption names the list while it is empty"
    _enter(field, "CC0 1.0")
    assert not empty.isVisible(), "the caption goes away once a phrase exists"
    field.setValues([])
    assert empty.isVisible(), "the caption returns when the list empties"


def test_chips_wrap_onto_rows_when_narrow(qapp):
    field = make_value_list(
        ["alpha", "beta", "gamma", "delta", "epsilon", "zeta"],
    )
    field.show()
    for _ in range(3):
        qapp.processEvents()
    field.resize(180, field.height())
    for _ in range(4):
        qapp.processEvents()
    rows: dict[Any, Any] = {}
    for chip in field._flow.chips():
        rows.setdefault(round(chip.geometry().top()), []).append(chip)
    assert len(rows) >= 2, "a narrow list wraps its chips onto more than one row"
    for row in rows.values():
        tops = {chip.geometry().top() for chip in row}
        assert len(tops) == 1, "chips on one row share a top edge"


def test_the_field_is_an_app_value_list(qapp):
    assert isinstance(make_value_list(), AppValueList)
    kept = make_value_list(["a"])
    assert isinstance(kept, AppValueList)
    edit = kept._field
    assert isinstance(edit, QLineEdit)
    assert edit.placeholderText() == ""
    field = make_value_list(placeholder="Add a phrase")
    assert field._field.placeholderText() == "Add a phrase"
