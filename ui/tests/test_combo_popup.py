"""Combo popups honor the app's menu row metrics (dv-tkz).

The popup measures items through the delegate, not the QSS — before this
fix the rows painted at ~20px and clipped descenders. The shared kit combo
now installs a row delegate sized from the font at any display scaling.
"""

from pathlib import Path

import pytest


def test_combo_popup_rows_meet_the_menu_contract(qapp):
    from ui.widgets import make_combo

    combo = make_combo(["Alpha", "Beta", "Gamma"])
    view = combo.view()
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
    view = combo.view()
    assert view.sizeHintForRow(0) >= max(34, view.fontMetrics().height() + 12)


@pytest.fixture
def view(qapp, tmp_path):
    from config import Config
    from ui.dataset_detail import DatasetDetailView

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
    v = DatasetDetailView(cfg, "doi:10.5072/FK2/COMBOTEST", "Combo test",
                          cached_metadata=metadata, cached_inventory=[])
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
        popup = combo.view()
        row = popup.sizeHintForRow(0)
        font_h = popup.fontMetrics().height()
        assert row >= font_h + 12
        assert row >= 34
