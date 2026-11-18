"""dv-zhf: the queue's Size cell says "unavailable" when nothing was readable.

A dataset whose every version is refused leaves the row thin. The Size
cell used to read an empty em dash with the tooltip "Size unknown — open
the dataset to load its file inventory" — advice that cannot work for a
dataset this account may not read. The decided policy: the em dash is
dimmed (a visual "not applicable"), and the hover carries the reason the
Access column gives.
"""

from PySide6.QtCore import Qt

from ui.theme import TEXT_MUTED


def _dashboard(tmp_path):
    from curation.config import Config
    from ui.dashboard import DashboardView

    cfg = Config()
    cfg.app.workspace = tmp_path
    return DashboardView(cfg)


def _paint(dash, rows):
    """Paint the rows into the queue and return the Size cells."""
    from ui.dashboard import COLUMNS

    dash._all_datasets = list(rows)
    dash._apply_filter()
    col = [key for key, _h, _v in COLUMNS].index("total_size_bytes")
    return [dash._table.item(r, col) for r in range(dash._table.rowCount())]


def _refused(pid="doi:10.5072/FK2/DENIED"):
    return {
        "persistent_id": pid,
        "title": "Denied dataset",
        "total_size_bytes": None,
        "access": {
            "state": "restricted",
            "reason": "not_readable",
            "detail": "the server said no",
            "status": 403,
        },
    }


def test_refused_row_dims_the_size_cell(qapp, tmp_path):
    dash = _dashboard(tmp_path)
    (item,) = _paint(dash, [_refused()])
    assert item.text() == "—", "the cell stays an em dash"
    brush = item.foreground()
    assert brush.style() != Qt.BrushStyle.NoBrush, "the ink is dimmed, not left at default"
    assert brush.color().name().lower() == TEXT_MUTED.lower()
    dash.deleteLater()


def test_the_hover_says_why_the_size_is_unavailable(qapp, tmp_path):
    dash = _dashboard(tmp_path)
    (item,) = _paint(dash, [_refused()])
    tip = item.toolTip()
    assert "not read" in tip.lower() or "cannot read" in tip.lower(), tip
    assert "the server said no" in tip, "the server's own message rides along"
    dash.deleteLater()


def test_a_readable_row_keeps_its_size_ink(qapp, tmp_path):
    dash = _dashboard(tmp_path)
    (item,) = _paint(
        dash,
        [
            {
                "persistent_id": "doi:10.5072/FK2/OK",
                "title": "Readable dataset",
                "total_size_bytes": 2048,
                "access": {"state": "readable", "reason": "", "detail": ""},
            }
        ],
    )
    assert item.text() != "—", "a readable dataset shows its size"
    assert item.foreground().style() == Qt.BrushStyle.NoBrush, "a real size is not dimmed"
    dash.deleteLater()


def test_a_partial_refusal_still_shows_the_summed_size(qapp, tmp_path):
    """The draft was refused, the published version was read: the size stays."""
    dash = _dashboard(tmp_path)
    (item,) = _paint(
        dash,
        [
            {
                "persistent_id": "doi:10.5072/FK2/PART",
                "title": "Partly readable dataset",
                "total_size_bytes": 512,
                "access": {
                    "state": "readable",
                    "reason": "",
                    "detail": "",
                    "version": ":latest-published",
                },
            }
        ],
    )
    assert item.text() != "—", "one readable version is enough for a size"
    assert item.foreground().style() == Qt.BrushStyle.NoBrush
    dash.deleteLater()


def test_an_unknown_size_is_not_dimmed(qapp, tmp_path):
    """No size and no refusal: the size is merely unknown, not unavailable."""
    dash = _dashboard(tmp_path)
    (item,) = _paint(
        dash,
        [
            {"persistent_id": "doi:10.5072/FK2/NEW", "title": "Not fetched yet"},
        ],
    )
    assert item.text() == "—"
    assert item.foreground().style() == Qt.BrushStyle.NoBrush, "only a refusal dims the cell"
    dash.deleteLater()
