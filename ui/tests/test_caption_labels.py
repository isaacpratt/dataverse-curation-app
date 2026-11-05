"""The window caption buttons name the action they perform.

A maximized window shows the restore glyph, so the button must read
"Restore window" to a screen reader — announcing "Maximize window" on a
button that restores it is a trap for keyboard and screen-reader users.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def caption_buttons(qapp):
    from config import Config
    from ui.main_window import MainWindow, _CaptionButton

    window = MainWindow(Config.load(None))
    try:
        yield {btn._kind: btn for btn in window.findChildren(_CaptionButton)}
    finally:
        window.close()


def test_caption_buttons_name_their_action(caption_buttons):
    assert caption_buttons["min"].accessibleName() == "Minimize window"
    assert caption_buttons["max"].accessibleName() == "Maximize window"
    assert caption_buttons["close"].accessibleName() == "Close window"


def test_restore_glyph_renames_the_button(caption_buttons):
    button = caption_buttons["max"]
    try:
        button.set_glyph("restore")
        assert button.toolTip() == "Restore"
        assert button.accessibleName() == "Restore window"

        button.set_glyph("max")
        assert button.toolTip() == "Maximize"
        assert button.accessibleName() == "Maximize window"
    finally:
        button.set_glyph("max")
