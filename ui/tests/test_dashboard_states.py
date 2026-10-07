"""P2 named metric states + the Docent status-bar contract.

Promoted from probe33/34 (pre-crawl state machine: Not fetched /
Checking… / digits, 12px vs 22px styles, Last-refresh tooltips) and
probe40 (status bar `base[/<alias>]: n/m datasets shown`, scope header
removed, footer Open Settings link replaced by the Docent mark).
"""

import re

import pytest
from PySide6.QtWidgets import QAbstractButton, QLabel

DASH = "\u2014"
ELL = "\u2026"
STATUS_RE = re.compile(r"^https?://\S+: \d+/\d+ datasets shown$")


class _FakeWorker:
    def isRunning(self):
        return True


def _mval(card):
    lbl = card.findChild(QLabel, "metricValue")
    return lbl.text() if lbl else None


def test_idle_metrics_read_not_fetched(win, monkeypatch):
    dash = win._dashboard
    monkeypatch.setattr(dash, "_crawled", False)
    monkeypatch.setattr(dash, "_worker", None)
    dash._update_metrics()
    vals = [_mval(c) for c in dash._metric_cards]
    assert vals == ["Not fetched"] * 3, vals
    assert "Last refresh: never" in dash._metric_cards[0].toolTip()


def test_loading_metrics_read_checking(win, monkeypatch):
    dash = win._dashboard
    monkeypatch.setattr(dash, "_crawled", False)
    monkeypatch.setattr(dash, "_worker", _FakeWorker())
    dash._update_metrics()
    vals = [_mval(c) for c in dash._metric_cards]
    assert vals == ["Checking" + ELL] * 3, vals


def test_crawled_metrics_read_digits_at_22px(win, monkeypatch):
    dash = win._dashboard
    monkeypatch.setattr(dash, "_crawled", True)
    monkeypatch.setattr(dash, "_worker", None)
    dash._update_metrics()
    vals = [_mval(c) for c in dash._metric_cards]
    assert all(v.isdigit() for v in vals), vals
    style = dash._metric_cards[0].findChild(QLabel, "metricValue").styleSheet()
    assert "font-size: 22px" in style


def test_state_switch_restores_12px_muted_style(win, monkeypatch):
    dash = win._dashboard
    monkeypatch.setattr(dash, "_crawled", True)
    dash._update_metrics()
    monkeypatch.setattr(dash, "_crawled", False)
    monkeypatch.setattr(dash, "_worker", None)
    dash._update_metrics()
    style = dash._metric_cards[0].findChild(QLabel, "metricValue").styleSheet()
    assert "font-size: 12px" in style


def test_metric_tooltips_always_carry_last_refresh(win, monkeypatch):
    dash = win._dashboard
    monkeypatch.setattr(dash, "_crawled", False)
    monkeypatch.setattr(dash, "_worker", None)
    dash._update_metrics()
    tips = [c.toolTip() for c in dash._metric_cards]
    assert all("Last refresh: " in t for t in tips), tips


@pytest.fixture
def seeded_dash(win, monkeypatch):
    dash = win._dashboard
    monkeypatch.setattr(
        dash,
        "_all_datasets",
        [
            {"title": "Alpha", "persistent_id": "doi:10.5072/FK2/A", "state": "DRAFT"},
            {"title": "Beta", "persistent_id": "doi:10.5072/FK2/B", "state": "RELEASED"},
        ],
    )
    dash._filter_edit.setText("")
    dash._apply_filter()
    return dash


def test_status_bar_format_and_count(seeded_dash):
    text = seeded_dash._status_lbl.text()
    assert STATUS_RE.match(text), text
    assert text.endswith(": 2/2 datasets shown"), text
    assert "dataset(s)" not in text


def test_status_bar_honours_filter(seeded_dash):
    seeded_dash._filter_edit.setText("zzzz")
    try:
        seeded_dash._apply_filter()
        assert seeded_dash._status_lbl.text().endswith(": 0/2 datasets shown")
        assert seeded_dash._progress.text() != "Double-click a row to open it"
    finally:
        seeded_dash._filter_edit.setText("")
        seeded_dash._apply_filter()
    assert seeded_dash._status_lbl.text().endswith(": 2/2 datasets shown")
    assert seeded_dash._progress.text() == "Double-click a row to open it"


def test_status_bar_shows_alias_when_configured(seeded_dash, monkeypatch):
    monkeypatch.setattr(
        seeded_dash._config.dataverse, "collection", "mcmaster", raising=False
    )
    seeded_dash._sync_status_bar()
    text = seeded_dash._status_lbl.text()
    assert re.match(r"^https?://\S+/mcmaster: \d+/\d+ datasets shown$", text), text


def test_scope_header_removed(win):
    dash = win._dashboard
    assert not hasattr(dash, "_title_lbl")
    headers = [
        lbl.text() for lbl in dash.findChildren(QLabel) if lbl.text().startswith("Datasets:")
    ]
    assert headers == []


def test_footer_open_settings_link_removed(win):
    dash = win._dashboard
    near = [
        b
        for b in dash.findChildren(QAbstractButton)
        if b.text() == "Open Settings" and abs(b.y() - dash._progress.y()) < 40
    ]
    assert near == []


def test_docent_mark_sits_bottom_right(win):
    dash = win._dashboard
    mark = dash.findChild(QLabel, "DocentMark")
    assert mark is not None, "docent mark missing from dashboard"
    assert not mark.pixmap().isNull()
    assert mark.y() > dash._progress.y()
    assert mark.x() > dash._status_lbl.x()
