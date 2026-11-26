"""Combo popups honor the app's menu row metrics (dv-tkz).

The popup measures items through the delegate, not the QSS — before this
fix the rows painted at ~20px and clipped descenders. The shared kit combo
now installs a row delegate sized from the font at any display scaling.
"""

from pathlib import Path
from typing import Any

import pytest


def _popup_view(combo: Any) -> Any:
    """Materialise the popup view the same way the first open does."""
    combo._ensure_popup_delegate()
    return combo.view()


def test_combo_popup_rows_meet_the_menu_contract(qapp):
    from ui.widgets import make_combo

    combo = make_combo(["Alpha", "Beta", "Gamma"])
    view = _popup_view(combo)
    row = view.sizeHintForRow(0)
    font_h = view.fontMetrics().height()
    assert row >= font_h + 12, f"row {row}px vs font {font_h}px + padding"
    assert row >= 34, "rows never fall below the declared 34px contract"
    model = view.model()
    for i in range(model.rowCount()):
        rect = view.visualRect(model.index(i, 0))
        assert rect.height() == row, "every option is the same height"


def test_kit_combo_variants_share_the_contract(qapp):
    from ui.widgets import make_disposition_combo

    combo = make_disposition_combo()
    view = _popup_view(combo)
    assert view.sizeHintForRow(0) >= max(34, view.fontMetrics().height() + 12)


@pytest.fixture
def view(qapp, tmp_path):
    from curation.config import Config
    from ui.dataset import DatasetDetailView

    def _fv(value):
        return {"typeName": "text", "multiple": False, "typeClass": "primitive", "value": value}

    metadata = {
        "latestVersion": {
            "metadataBlocks": {
                "citation": {
                    "fields": [
                        {"typeName": "title", "value": "A study"},
                        {"typeName": "depositor", "value": "Ada Lovelace"},
                        {"typeName": "dateOfDeposit", "value": "2026-01-02"},
                    ]
                }
            }
        }
    }
    cfg = Config()
    cfg.app.workspace = Path(tmp_path)
    v = DatasetDetailView(
        cfg,
        "doi:10.5072/FK2/COMBOTEST",
        "Combo test",
        cached_metadata=metadata,
        cached_inventory=[],
    )
    v.show()
    for _ in range(5):
        qapp.processEvents()
    yield v
    v.close()
    v.deleteLater()


def test_metadata_pane_combos_meet_the_menu_contract(view):
    for name in ("_meta_filter", "_profile_combo"):
        combo = getattr(view, name, None)
        if combo is None:
            pytest.skip(f"{name} not present in this build")
        popup = _popup_view(combo)
        row = popup.sizeHintForRow(0)
        font_h = popup.fontMetrics().height()
        assert row >= font_h + 12
        assert row >= 34


def test_combo_popup_keeps_rounded_corners_and_no_gap(qapp):
    """A dropdown opens flush: no white strip, no shape change (2026-11-25)."""
    import inspect

    from ui.theme import RADIUS_LG, global_qss
    from ui.widgets import _NoWheelCombo, make_combo

    make_combo(["Alpha", "Beta"])
    sheet = global_qss()
    assert "QComboBox:on" not in sheet, "the field must not square off while open"
    assert f"border-top-left-radius: {RADIUS_LG}" in sheet
    assert f"border-bottom-left-radius: {RADIUS_LG}" in sheet
    # The old kit moved the popup down 4px in showPopup, which left an odd
    # white strip above the options. The override now only installs the row
    # delegate lazily; it must never touch popup geometry.
    source = inspect.getsource(_NoWheelCombo.showPopup)
    assert "move(" not in source
    assert "setGeometry" not in source
    assert "_POPUP_GAP" not in _NoWheelCombo.__dict__


def test_combo_popup_delegate_is_installed_lazily(qapp):
    """Constructing a combo no longer installs a popup row delegate."""
    from typing import Any, cast

    from ui.widgets import _ComboPopupRowDelegate, make_combo

    combo = cast(Any, make_combo(["Alpha", "Beta"]))
    assert combo._popup_delegate is None
    view = combo.view()
    assert not isinstance(view.itemDelegate(), _ComboPopupRowDelegate)
    combo._ensure_popup_delegate()
    assert combo._popup_delegate is not None
    assert view.itemDelegate() is combo._popup_delegate
