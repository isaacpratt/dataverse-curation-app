"""README section checklist in the Auto-Checks card (dv-81q)."""


def _view():
    from ui.dataset_detail import DatasetDetailView

    v = DatasetDetailView.__new__(DatasetDetailView)
    return v


def test_auto_row_renders_section_checklist(qapp):
    from PySide6.QtWidgets import QLabel

    row = _view()._auto_row(
        "metadata.readme_sections",
        "README is missing 2 of 5 standard section(s): Methodology, Sharing, access & licensing",
        False,
        "warning",
        detail_lines=[("Dataset & file overview", True), ("Methodology", False)],
    )
    texts = [w.text() for w in row.findChildren(QLabel)]
    assert any("✓ Dataset & file overview" in text for text in texts)
    assert any("○ Methodology" in text for text in texts)
    assert any("2 of 5 standard section" in text for text in texts)


def test_auto_row_without_detail_lines_is_unchanged(qapp):
    from PySide6.QtWidgets import QLabel

    row = _view()._auto_row("inventory.zero_byte", "1 empty file", False, "error")
    texts = [w.text() for w in row.findChildren(QLabel)]
    assert not any("✓" in text or "○" in text for text in texts)
