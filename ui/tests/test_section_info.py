"""Section headers carry a Lucide (i) button whose tooltip holds the help."""

from typing import Any

from PySide6.QtWidgets import QToolButton

from ui.widgets import add_info_tip, make_card


def _tips(widget: Any):
    return [b for b in widget.findChildren(QToolButton) if b.objectName() == "InfoTip"]


def test_info_tip_sits_right_after_the_title(qapp):
    _card, _body, _title, header = make_card("Auto-Checks")
    btn = add_info_tip(header, "First paragraph.", "✓ pass · ✕ issue", name="Auto-Checks")

    assert header.indexOf(btn) == 1, "the (i) belongs next to the title"
    assert btn.toolTip() == "First paragraph.\n\n✓ pass · ✕ issue"
    assert btn.accessibleName() == "About Auto-Checks"
    assert not btn.icon().isNull(), "the Lucide info glyph must load"


def test_long_help_is_wrapped_for_the_tooltip(qapp):
    _card, _body, _title, header = make_card("File Manifest")
    btn = add_info_tip(header, "word " * 60, name="File Manifest")

    lines = btn.toolTip().splitlines()
    assert len(lines) > 1
    assert max(len(line) for line in lines) <= 76


def test_dataset_sections_get_info_tips_and_no_legend(qapp):
    from curation.config import Config
    from ui.dataset import DatasetDetailView

    view = DatasetDetailView(
        Config(),
        "doi:10.0000/TEST-INFO",
        "Info tips",
        cached_metadata={"id": 1, "versionNumber": 1},
        cached_inventory=[],
    )
    try:
        # The merged card has its own (i) and, while it still builds one, a
        # second from the auto-checks section it swallowed (dv-gfx.5, 9).
        assert len(_tips(view._meta_card)) in (1, 2)
        for card in (
            view._file_card,
            view._version_card,
            view._dataset_log_card,
        ):
            assert len(_tips(card)) == 1
        assert len(_tips(view._auto_card)) in (0, 1)
        assert not hasattr(view, "_auto_legend"), "the inline legend moved to the tooltip"
        assert len(_tips(view._response_page)) == 4
    finally:
        view.deleteLater()