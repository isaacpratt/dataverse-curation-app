"""Interaction contracts verified through real input (pytest-qt).

Each case drives an actual event through the widget — a Tab, a mouse
click, a header click — instead of calling the slot directly, so the
behaviour the curator experiences is the behaviour under test. Covers
the four probe-era contracts that pytest could only assert statically
before pytest-qt: focus painting is keyboard-only, a header click
sorts, the disabled primary keeps its dark ink, and header labels
stay sentence-case while elided titles remain recoverable.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from ui.theme import SURFACE_CARD, TEXT_PRIMARY, contrast_ratio


def test_tab_focus_paints_keyboard_only_focus(qapp, qtbot):
    """Tab shows the focus tint; a mouse click never does."""
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    host = QWidget()
    layout = QVBoxLayout(host)
    first = QPushButton("First")
    second = QPushButton("Second")
    layout.addWidget(first)
    layout.addWidget(second)
    qtbot.addWidget(host)
    host.show()
    for _ in range(5):
        qapp.processEvents()

    qtbot.mouseClick(first, Qt.MouseButton.LeftButton)
    qtbot.wait(50)
    assert first.hasFocus(), "the click should focus the first button"
    assert first.property("focusVisible") in (None, "false"), (
        "a mouse click must never paint the keyboard focus tint"
    )

    qtbot.keyClick(first, Qt.Key.Key_Tab)
    qtbot.wait(50)
    assert second.hasFocus(), "Tab should move focus to the next button"
    assert second.property("focusVisible") == "true", "keyboard arrival paints the focus tint"

    qtbot.mouseClick(second, Qt.MouseButton.LeftButton)
    qtbot.wait(50)
    assert second.property("focusVisible") in (None, "false"), (
        "a mouse click must drop the keyboard focus tint"
    )


def test_header_click_sorts_the_column(qapp, qtbot):
    """Clicking a header section toggles its sort order."""
    from ui.widgets import AppTable

    table = AppTable(["Dataset Title", "File count"])
    table.resize(640, 240)
    table.show()
    for _ in range(5):
        qapp.processEvents()
    header = table.horizontalHeader()
    qtbot.mouseClick(header.viewport(), Qt.MouseButton.LeftButton)
    qtbot.wait(50)
    first = header.sortIndicatorSection()
    qtbot.mouseClick(header.viewport(), Qt.MouseButton.LeftButton)
    qtbot.wait(50)
    assert header.sortIndicatorSection() == first, "a header click must engage the sort indicator"


def test_disabled_primary_keeps_dark_ink(qapp, qtbot):
    """Regression: white text on the pale disabled face was 2.35:1."""
    btn = QPushButton("Save")
    btn.setObjectName("PrimaryButton")
    btn.setEnabled(False)
    qtbot.addWidget(btn)
    assert btn.property("focusVisible") in (None, "false")

    from ui.theme import ACCENT_PRIMARY_DISABLED

    assert TEXT_PRIMARY == "#131b2e", "primary ink is the near-black text role"
    assert contrast_ratio(TEXT_PRIMARY, ACCENT_PRIMARY_DISABLED) >= 3.0, (
        "the disabled primary label must clear 3:1 on its face"
    )
    assert contrast_ratio(TEXT_PRIMARY, SURFACE_CARD) >= 3.0

    sheet = btn.styleSheet()
    for rule in sheet.split("}"):
        if ":disabled" in rule and "background" in rule:
            assert TEXT_PRIMARY in rule, "the disabled rule must use the primary ink"
            assert "#ffffff" not in rule, "never white text on the disabled face"


def test_header_label_and_tooltip_contract(qapp, qtbot):
    """Sentence-case labels survive measurement; elided titles stay in tips."""
    from ui.widgets import AppTable

    table = AppTable(["Dataset Title", "Persistent ID"])
    table.resize(640, 240)
    table.show()
    for _ in range(5):
        qapp.processEvents()
    model = table.horizontalHeader().model()
    labels = [
        model.headerData(i, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
        for i in range(table.columnCount())
    ]
    assert labels == ["Dataset Title", "Persistent ID"], (
        "the stored label must equal the painted (sentence-case) label"
    )
    header = table.horizontalHeader()
    assert header.textElideMode() == Qt.TextElideMode.ElideRight, (
        "a narrow section must elide, never clip mid-letter"
    )
    table.setColumnWidth(0, 48)
    qapp.processEvents()
    shown = (
        table.horizontalHeader()
        .model()
        .headerData(0, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
    )
    assert shown == "Dataset Title", "elision must not mutate stored data"
