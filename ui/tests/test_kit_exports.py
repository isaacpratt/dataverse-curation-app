"""Kit surface: what the shared component kit promises as importable.

Kept intentionally small — it pins the API the views call, not the
rendering. If a builder is renamed or a kind disappears, a view that
imports it fails here with the name of the missing promise.
"""

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTextEdit,
)

from ui.theme import BUTTON_OBJECTS


def test_kit_public_api_exists(qapp):
    """Every builder a view needs is importable and makes its type."""
    import ui.widgets as kit

    cases = [
        (kit.make_action_button("Save"), QPushButton),
        (kit.make_line_edit("Name"), QLineEdit),
        (kit.make_search_field("Search"), QLineEdit),
        (kit.make_combo(["a", "b"]), QComboBox),
        (kit.make_multiline_input(), QTextEdit),
        (kit.make_plain_text_view(), QPlainTextEdit),
        (kit.make_list(), QFrame),
        (kit.make_checkbox("Required"), QCheckBox),
        (kit.make_progress_bar(), QProgressBar),
        (kit.make_badge("Ready"), QLabel),
        (kit.make_field_label("Decision State"), QLabel),
        ((kit.make_card("Card")[0]), QFrame),
    ]
    for widget, cls in cases:
        assert isinstance(widget, cls), f"expected {cls.__name__}"


def test_app_button_kinds_point_at_theme_objects(qapp):
    """The kit's button kinds and the theme's rules cannot drift apart."""
    from ui.widgets import AppButton

    for kind, object_name in BUTTON_OBJECTS.items():
        btn = AppButton("x", kind=kind)
        assert btn.objectName() == object_name, (
            f"{kind}: kit object name {btn.objectName()!r} != theme {object_name!r}"
        )


def test_button_heights_clear_the_floor(qapp):
    """Every size token clears the 32px hit-target floor."""
    from ui.widgets import BUTTON_HEIGHTS

    for size, px in BUTTON_HEIGHTS.items():
        assert px >= 32, f"{size}: {px}px is below the 32px floor"


def test_table_and_tree_classes_exist(qapp):
    """The standard views a view composes."""
    from ui.widgets import AppTable, AppTree, AppTreeWidget

    table = AppTable(["A", "B"])
    assert isinstance(table, QTableWidget)
    assert AppTree is not None and AppTreeWidget is not None
