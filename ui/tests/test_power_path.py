"""Power path for the queue loop (dv-9m2).

The per-dataset loop binds Ctrl+Enter (run checks / commit on the
Response page), Ctrl+D (download all) and Ctrl+Shift+O (open the staged
folder) as real key events inside the detail view; the queue's right-click
menu enqueues a background file-checks pass for exactly the rows the
table paints — never more than the 2,000-row painting window — and logs
the count.
"""

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest


def _fv(value):
    return {"typeName": "text", "multiple": False, "typeClass": "primitive", "value": value}


def _metadata() -> dict:
    return {
        "latestVersion": {
            "license": {"name": "CC0 1.0"},
            "metadataBlocks": {
                "citation": {
                    "fields": [
                        {"typeName": "title", "value": "A study"},
                        {"typeName": "author", "value": [
                            {
                                "authorName": _fv("Ada Lovelace"),
                                "authorAffiliation": _fv("Lab"),
                                "authorIdentifierScheme": _fv("ORCID"),
                                "authorIdentifier": _fv("0000-0002-1825-0097"),
                            },
                        ]},
                        {"typeName": "datasetContact", "value": [
                            {"datasetContactName": _fv("Ada Lovelace")},
                        ]},
                        {"typeName": "dsDescription", "value": [
                            {"dsDescriptionValue": _fv("Desc."), "dsDescriptionDate": _fv("2026-01-01")},
                        ]},
                        {"typeName": "subject", "value": ["Computer and Information Science"]},
                        {"typeName": "depositor", "value": "Ada Lovelace"},
                        {"typeName": "dateOfDeposit", "value": "2026-01-02"},
                    ]
                }
            },
        }
    }


@pytest.fixture
def view(qapp, tmp_path):
    from config import Config
    from ui.dataset_detail import DatasetDetailView

    cfg = Config()
    cfg.app.workspace = Path(tmp_path)
    v = DatasetDetailView(
        cfg,
        "doi:10.5072/FK2/KEYS",
        "Keys test",
        cached_metadata=_metadata(),
        cached_inventory=[],
    )
    v.show()
    v._check_btn.setFocus()
    for _ in range(5):
        qapp.processEvents()
    yield v
    v.close()
    v.deleteLater()


def test_ctrl_enter_runs_checks(view):
    calls = []
    view._on_run_checks = lambda: calls.append("run")
    QTest.keyClick(view._check_btn, Qt.Key_Return, Qt.ControlModifier)
    assert calls == ["run"]


def test_ctrl_enter_commits_on_the_response_page(view):
    view._show_response_page()
    committed, ran = [], []
    view._on_commit = lambda: committed.append("commit")
    view._on_run_checks = lambda: ran.append("run")
    QTest.keyClick(view._check_btn, Qt.Key_Return, Qt.ControlModifier)
    assert committed == ["commit"]
    assert ran == [], "Ctrl+Enter on the Response page must not re-run checks"


def test_ctrl_enter_runs_checks_back_on_the_review_page(view):
    view._show_response_page()
    view._show_review_page()
    calls = []
    view._on_run_checks = lambda: calls.append("run")
    view._on_commit = lambda: calls.append("commit")
    QTest.keyClick(view._check_btn, Qt.Key_Return, Qt.ControlModifier)
    assert calls == ["run"]


def test_ctrl_d_downloads_all(view):
    calls = []
    view._on_download = lambda: calls.append("download")
    QTest.keyClick(view._check_btn, Qt.Key_D, Qt.ControlModifier)
    assert calls == ["download"]


def test_ctrl_shift_o_opens_the_staged_folder(view):
    calls = []
    view._on_open_folder = lambda: calls.append("open")
    QTest.keyClick(view._check_btn, Qt.Key_O, Qt.ControlModifier | Qt.ShiftModifier)
    assert calls == ["open"]


def test_shortcuts_stay_inside_the_view(view):
    assert getattr(view, "_shortcuts", None), "the detail view must register its chords"
    for sc in view._shortcuts:
        assert sc.context() == Qt.WidgetWithChildrenShortcut, (
            "the chord fires with focus anywhere in the app; it must stay in the view"
        )


def test_run_button_tooltip_lists_the_chords(view):
    tip = view._check_btn.toolTip()
    assert "Ctrl+Enter" in tip
    assert "Ctrl+D" in tip
    assert "Ctrl+Shift+O" in tip


def _fake_datasets(n):
    return [
        {"persistent_id": f"doi:10.5072/FK2/T{i:04d}", "title": f"dataset {i}"}
        for i in range(n)
    ]


class _FakeBulk:
    """Stand-in for BulkCheckWorker: records the jobs, never starts a thread."""

    instances = []

    def __init__(self, jobs, workspace, parent=None):
        from PySide6.QtCore import QObject, Signal

        class _Signals(QObject):
            progress = Signal(str)
            progressFraction = Signal(float)
            finished = Signal(object)
            cancelled = Signal()
            error = Signal(str)

        self._signals = _Signals()
        self.jobs = list(jobs)
        self.workspace = workspace
        self.started = False
        _FakeBulk.instances.append(self)

    def start(self):
        self.started = True

    def __getattr__(self, name):
        if name in ("progress", "progressFraction", "finished", "cancelled", "error"):
            return getattr(self._signals, name)
        raise AttributeError(name)


def test_context_menu_enqueues_up_to_the_painting_cap(win, qapp, monkeypatch):
    import applog

    dash = win._dashboard
    win._show_dashboard()
    for _ in range(6):
        qapp.processEvents()

    original_datasets = dash._datasets
    original_worker = dash._bulk_worker
    _FakeBulk.instances = []
    applog.clear()
    monkeypatch.setattr("ui.dashboard.BulkCheckWorker", _FakeBulk)
    try:
        dash._datasets = _fake_datasets(2100)
        menu = dash._build_queue_context_menu()
        actions = [a for a in menu.actions() if not a.isSeparator()]
        assert len(actions) == 1, "one item: bulk checks for the visible rows"
        assert "2,000" in actions[0].text()
        actions[0].trigger()

        assert len(_FakeBulk.instances) == 1
        worker = _FakeBulk.instances[0]
        assert worker.started
        assert len(worker.jobs) == 2000, "the painting window caps the enqueue"
        assert len(dash._bulk_enqueued) == 2000
        logged = "\n".join(applog.lines())
        assert "2,000" in logged and "Bulk checks enqueued" in logged
    finally:
        dash._datasets = original_datasets
        dash._bulk_worker = original_worker


def test_context_menu_enqueues_every_row_below_the_cap(win, qapp, monkeypatch):
    dash = win._dashboard
    win._show_dashboard()
    for _ in range(6):
        qapp.processEvents()

    original_datasets = dash._datasets
    original_worker = dash._bulk_worker
    _FakeBulk.instances = []
    monkeypatch.setattr("ui.dashboard.BulkCheckWorker", _FakeBulk)
    try:
        dash._datasets = _fake_datasets(3)
        menu = dash._build_queue_context_menu()
        actions = [a for a in menu.actions() if not a.isSeparator()]
        assert "3" in actions[0].text()
        actions[0].trigger()
        assert [pid for pid, _ in _FakeBulk.instances[0].jobs] == [
            ds["persistent_id"] for ds in dash._datasets
        ]
        assert len(dash._bulk_enqueued) == 3
    finally:
        dash._datasets = original_datasets
        dash._bulk_worker = original_worker


def test_context_menu_is_disabled_when_nothing_is_painted(win, qapp):
    dash = win._dashboard
    win._show_dashboard()
    for _ in range(6):
        qapp.processEvents()

    original_datasets = dash._datasets
    original_worker = dash._bulk_worker
    try:
        dash._datasets = []
        menu = dash._build_queue_context_menu()
        actions = [a for a in menu.actions() if not a.isSeparator()]
        assert actions and not actions[0].isEnabled()
    finally:
        dash._datasets = original_datasets
        dash._bulk_worker = original_worker
