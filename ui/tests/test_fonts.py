"""Bundled typography: three faces ship with the app and really resolve.

The old code asked ``QFont('Inter').family()`` whether Inter was installed;
Qt answers with the requested name even when the family is missing, so the
fallback branch never fired and custom-painted text landed on an arbitrary
system substitution. The faces are now bundled in ``ui/assets/fonts`` and
registered through QFontDatabase before the app font and stylesheet are set.
"""

from pathlib import Path

import pytest
from PySide6.QtGui import QFontDatabase, QFontInfo
from PySide6.QtWidgets import QLabel, QWidget

from ui import theme


def test_all_three_faces_and_their_licences_are_bundled():
    for _family, filename in theme.BUNDLED_FONTS:
        assert theme.asset_path(f"fonts/{filename}"), filename
    for name in ("OFL-Inter.txt", "OFL-Fraunces.txt", "OFL-JetBrainsMono.txt"):
        assert theme.asset_path(f"fonts/{name}"), name


def test_register_fonts_loads_every_face(qapp):
    loaded = theme.register_fonts()
    assert loaded == {family: True for family, _ in theme.BUNDLED_FONTS}, loaded
    assert len(theme._REGISTERED_FONTS) == 3
    # The helper caches by file path: Qt hands back a new id for every
    # addApplicationFont call, so re-registering on each apply_theme would
    # leak font entries (and crashed an xdist worker with heap corruption).
    assert theme.register_fonts() == loaded
    assert len(theme._REGISTERED_FONTS) == 3, "a second call must not register more fonts"
    for family in loaded:
        assert family in QFontDatabase.families(), family


def test_apply_theme_sets_a_real_inter_app_font(qapp):
    theme.apply_theme(qapp)
    assert QFontInfo(qapp.font()).family() == "Inter", QFontInfo(qapp.font()).family()
    assert qapp.font().pixelSize() == theme.FONT_BODY


@pytest.mark.parametrize(
    ("token", "family"),
    [
        ("DisplayLG", "Fraunces"),
        ("HeadlineLG", "Fraunces"),
        ("HeadlineMD", "Fraunces"),
        ("CardTitle", "Fraunces"),
        ("BodyMD", "Inter"),
        ("BodySM", "Inter"),
        ("CaptionSM", "Inter"),
        ("HintSM", "Inter"),
    ],
)
def test_each_text_style_resolves_to_its_face(qapp, token, family):
    theme.apply_theme(qapp)
    label = QLabel("Aa 123")
    label.setObjectName(token)
    label.show()
    qapp.processEvents()
    resolved = QFontInfo(label.font()).family()
    assert resolved == family, f"{token}: {resolved!r}, expected {family!r}"
    label.close()
    label.deleteLater()


def test_mono_is_opt_in_and_only_the_raw_metadata_view_uses_it(qapp):
    """Read-only text is Inter; only the raw metadata field asks for mono."""
    from ui.widgets import make_multiline_input, make_plain_text_view

    theme.apply_theme(qapp)
    views: list[QWidget] = [
        make_plain_text_view("a log line"),
        make_multiline_input(mono=True, read_only=True),
    ]
    for view in views:
        view.show()
    qapp.processEvents()
    assert QFontInfo(views[0].font()).family() == "Inter", QFontInfo(views[0].font()).family()
    assert QFontInfo(views[1].font()).family() == "JetBrains Mono", QFontInfo(views[1].font()).family()
    for view in views:
        view.close()
        view.deleteLater()


def test_no_raw_mono_font_outside_the_theme():
    """A view cannot quietly reintroduce a system-dependent mono face."""
    root = Path(__file__).resolve().parents[2]
    hits: set[str] = set()
    for path in sorted(root.glob("ui/**/*.py")):
        if path.name == "theme.py" or "tests" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        if 'QFont("JetBrains Mono")' in source or "mono=True," in source:
            hits.add(path.relative_to(root).as_posix())
    # The raw metadata view is the one deliberate mono field.
    assert hits == {"ui/dataset/page.py"}, hits
