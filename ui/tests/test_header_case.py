"""Column headers are stored in sentence case, exactly as painted."""

from PySide6.QtCore import Qt


def test_table_header_keeps_sentence_case(qapp):
    from ui.widgets import AppTable

    table = AppTable(["Dataset Title", "Persistent ID"])
    model = table.horizontalHeader().model()
    labels = [
        model.headerData(i, Qt.Horizontal, Qt.DisplayRole)
        for i in range(table.columnCount())
    ]
    assert labels == ["Dataset Title", "Persistent ID"]


def test_tree_widget_header_keeps_sentence_case(qapp):
    from ui.widgets import AppTreeWidget

    tree = AppTreeWidget()
    tree.setHeaderLabels(["Field", "Check"])
    assert tree.headerItem().text(0) == "Field"
    assert tree.headerItem().text(1) == "Check"


def test_file_manifest_header_keeps_sentence_case(qapp):
    from ui.checks_tree import COLUMNS, build_tree_model

    model = build_tree_model([], None)
    labels = [
        model.headerData(i, Qt.Horizontal, Qt.DisplayRole)
        for i in range(len(COLUMNS))
    ]
    assert labels == list(COLUMNS)
