"""P2 named metric states + the Docent status-bar contract.

Promoted from probe33/34 (pre-crawl state machine: Not fetched /
Checking… / digits, 12px vs 22px styles, Last-refresh tooltips) and
probe40 (status bar `base[/<alias>]: n/m datasets shown`, scope header
removed, footer Open Settings link replaced by the Docent mark).
"""

import re

import pytest
from PySide6.QtWidgets import QAbstractButton, QFrame, QLabel

DASH = "\u2014"
ELL = "\u2026"
STATUS_RE = re.compile(r"^https?://\S+: \d+/\d+ datasets shown$")


class _FakeWorker:
    def isRunning(self):
        return True


def _mval(card):
    # The value label carries its theme token as its object name
    # (DisplayLG / StateMD), so it is found by type, not by a fixed name.
    labels = [
        lbl
        for lbl in card.findChildren(QLabel)
        if lbl.objectName() in ("DisplayLG", "StateMD")
    ]
    return labels[0].text() if labels else None


def test_idle_metrics_read_not_fetched(win, monkeypatch):
    dash = win._dashboard
    monkeypatch.setattr(dash, "_crawled", False)
    monkeypatch.setattr(dash, "_worker", None)
    # The shared window may hold a real cache entry ("restoring" is a named
    # pre-crawl state now); an idle, empty dashboard is the case here.
    monkeypatch.setattr(dash, "_restoring", False)
    dash._update_metrics()
    vals = [_mval(c) for c in dash._metric_cards]
    assert vals == ["Not fetched"] * 3, vals
    assert dash._metric_cards[0].toolTip() == "", "cards carry no tooltip (dv-1k4)"


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
    # The value wears the theme's DisplayLG token (22px bold) -- not an
    # inline stylesheet, so the page cannot drift from the type scale.
    label = dash._metric_value_labels[0]
    assert label.objectName() == "DisplayLG"
    assert label.styleSheet() == ""
    assert label.font().pixelSize() == 22


def test_state_switch_restores_12px_muted_style(win, monkeypatch):
    dash = win._dashboard
    monkeypatch.setattr(dash, "_crawled", True)
    dash._update_metrics()
    monkeypatch.setattr(dash, "_crawled", False)
    monkeypatch.setattr(dash, "_worker", None)
    dash._update_metrics()
    label = dash._metric_value_labels[0]
    assert label.objectName() == "StateMD"
    assert label.styleSheet() == ""
    assert label.font().pixelSize() == 12


def test_metric_cards_have_no_tooltip(win, monkeypatch):
    """The cards are filter controls, not a tooltip target (dv-1k4)."""
    dash = win._dashboard
    monkeypatch.setattr(dash, "_crawled", False)
    monkeypatch.setattr(dash, "_worker", None)
    dash._update_metrics()
    assert [c.toolTip() for c in dash._metric_cards] == ["", "", ""]


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
    dash._state_filter.setCurrentIndex(0)
    dash._labelled_only = False
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
    from PySide6.QtCore import QPoint

    dash = win._dashboard
    # Dashboard coordinates for both sides — the message label now lives
    # inside the bar strip, so its local y() is parent-relative.
    prog_y = dash._progress.mapTo(dash, QPoint(0, 0)).y()
    near = [
        b
        for b in dash.findChildren(QAbstractButton)
        if b.text() == "Open Settings"
        and abs(b.mapTo(dash, QPoint(0, 0)).y() - prog_y) < 40
    ]
    assert near == []


def test_docent_mark_sits_bottom_right(win):
    from PySide6.QtCore import QPoint

    dash = win._dashboard
    mark = dash.findChild(QLabel, "DocentMark")
    assert mark is not None, "docent mark missing from dashboard"
    assert not mark.pixmap().isNull()
    # Compare in dashboard coordinates — the labels now live inside the
    # bar, so their local y() values are parent-relative.
    mark_pt = mark.mapTo(dash, QPoint(0, 0))
    prog_pt = dash._progress.mapTo(dash, QPoint(0, 0))
    scope_pt = dash._status_lbl.mapTo(dash, QPoint(0, 0))
    # On the status-bar row, to the right of both labels — the bar ends
    # just before the mark (2026-10-07 unified bar).
    assert abs(mark_pt.y() - prog_pt.y()) < 30
    assert mark_pt.x() > prog_pt.x()
    assert mark_pt.x() > scope_pt.x()


def test_status_pill_is_single_unified_row(win):
    """Scope + message share the one status pill; its row ends before the mark.

    The flat full-bleed strip was rejected — the status bar lives in the
    pill that previously existed (2026-10-07).
    """
    from PySide6.QtCore import QPoint

    dash = win._dashboard
    pill = dash._status_lbl.parentWidget()
    assert pill is not None
    assert pill is dash._progress.parentWidget(), "message lives outside the pill"
    assert pill.objectName() == "StatusPill"
    # Exactly one pill — the old second status bar is gone.
    assert len(dash.findChildren(QFrame, "StatusPill")) == 1
    mark = dash.findChild(QLabel, "DocentMark")
    assert mark is not None
    pill_right = pill.mapTo(dash, QPoint(pill.width(), 0)).x()
    mark_x = mark.mapTo(dash, QPoint(0, 0)).x()
    assert pill_right <= mark_x, "pill row must end before the mark"
    # The pill stretches its row across the content width.
    assert pill.width() > dash.width() * 0.6, pill.width()
