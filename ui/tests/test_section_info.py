"""Section headers carry a Lucide (i) button whose tooltip holds the help."""

from PySide6.QtWidgets import QToolButton

from ui.widgets import add_info_tip, make_card


def _tips(widget):
    return [b for b in widget.findChildren(QToolButton) if b.objectName() == "InfoTip"]


def test_info_tip_sits_right_after_the_title(qapp):
    card, _body, _title, header = make_card("Auto-Checks")
    btn = add_info_tip(
        header, "First paragraph.", "✓ pass · ✕ issue", name="Auto-Checks"
    )

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
    from config import Config
    from ui.dataset_detail import DatasetDetailView

    view = DatasetDetailView(
        Config(),
        "doi:10.0000/TEST-INFO",
        "Info tips",
        cached_metadata={"id": 1, "versionNumber": 1},
        cached_inventory=[],
    )
    try:
        for card in (
            view._meta_card,
            view._file_card,
            view._auto_card,
            view._version_card,
            view._dataset_log_card,
        ):
            assert len(_tips(card)) == 1
        auto = _tips(view._auto_card)[0]
        auto_help = " ".join(auto.toolTip().split())
        assert "per-file passes live in File Manifest" in auto_help
        assert "✓ pass · ✕ issue" in auto_help
        assert not hasattr(view, "_auto_legend"), "the inline legend moved to the tooltip"
        assert len(_tips(view._response_page)) == 4
    finally:
        view.deleteLater()
