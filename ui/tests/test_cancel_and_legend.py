"""Step-5 behavioral minors: mid-download Cancel + log severity legend.

Promoted from the same critique flag as the busy-cancel P3: the detail
view needs a Cancel affordance wired to the worker's `cancelled` signal,
and the log page's severity colours need a visible, non-hover legend
whose chips use the highlighter's exact fills (WYSIWYG).
"""

import pytest
from PySide6.QtWidgets import QLabel

from dataverse_client import DownloadCancelled
from ui.workers import DownloadWorker


@pytest.fixture(scope="module")
def det(win, qapp):
    win._open_dataset("doi:10.5072/FK2/CANCELUI", "Cancel UI (tests)")
    detail = None
    for _ in range(100):
        qapp.processEvents()
        detail = getattr(win, "_detail", None)
        if detail is not None and getattr(detail, "_dl_cancel_btn", None) is not None:
            break
    assert detail is not None, "detail view did not open"
    return detail


class _FakeWorker:
    def __init__(self):
        self.cancel_called = False

    def cancel(self):
        self.cancel_called = True


def test_cancel_button_hidden_until_download_starts(det):
    assert det._dl_cancel_btn.isHidden(), "idle action row must not show Cancel"


def test_cancel_click_signals_worker_and_disables(det):
    fake = _FakeWorker()
    det._dl_worker = fake
    det._dl_cancel_btn.setEnabled(True)
    try:
        det._on_download_cancel_click()
        assert fake.cancel_called, "click must reach the worker's stop flag"
        assert not det._dl_cancel_btn.isEnabled(), "disable until acknowledged"
        assert "Cancelling" in det._status.text()
    finally:
        det._dl_worker = None
        det._dl_cancel_btn.setEnabled(True)
        det._set_status("")


def test_cancelled_handler_resets_action_row(det, monkeypatch):
    logged = {}

    def _record(action, notes="", details=None):
        logged.update(action=action, notes=notes, details=details or {})

    monkeypatch.setattr(det, "_log_action", _record)
    det._dl_worker = _FakeWorker()
    det._progress.setVisible(True)
    det._dl_btn.setEnabled(False)
    det._dl_cancel_btn.setEnabled(False)
    det._dl_cancel_btn.setVisible(True)
    try:
        det._on_download_cancelled()
        assert det._dl_worker is None
        assert det._progress.isHidden()
        assert det._dl_btn.isEnabled()
        assert det._dl_cancel_btn.isHidden()
        assert det._dl_cancel_btn.isEnabled()
        assert "Download cancelled" in det._status.text()
        assert logged.get("action") == "downloaded"
        assert "Cancelled" in logged.get("notes", "")
    finally:
        det._set_status("")


def test_worker_cancel_from_client_stream_emits_cancelled(qapp, tmp_path):
    class _CancelClient:
        def download_dataset_zip(self, identifier, dest, version="draft", progress=None,
                                 is_cancelled=None, guestbook_response=None):
            raise DownloadCancelled("bundle")

        def inventory(self, persistent_id):
            return []

    hits = []
    worker = DownloadWorker(_CancelClient(), tmp_path, "doi:10.5072/FK2/W1")
    worker.cancelled.connect(lambda: hits.append("cancelled"))
    worker.error.connect(lambda msg: hits.append("error"))
    worker.run()  # synchronous — no thread needed for the contract
    assert hits == ["cancelled"], f"expected cancelled only, got {hits}"


def test_worker_cancel_before_start_never_touches_network(qapp, tmp_path):
    class _NeverClient:
        def __getattr__(self, name):
            raise AssertionError("client touched after pre-run cancel")

    hits = []
    worker = DownloadWorker(_NeverClient(), tmp_path, "doi:10.5072/FK2/W2")
    worker.cancelled.connect(lambda: hits.append("cancelled"))
    worker.error.connect(lambda msg: hits.append("error"))
    worker.cancel()  # pre-run: Python-side flag must still stop the run
    worker.run()
    assert hits == ["cancelled"], f"expected cancelled only, got {hits}"


def test_log_legend_is_selectable_and_coloured(win, qapp):
    from PySide6.QtCore import Qt

    from ui.theme import STATE_ERROR_GRAPHIC, STATE_WARNING_GRAPHIC, TEXT_MUTED

    win._on_log_toggled(True)
    try:
        for _ in range(20):
            qapp.processEvents()
        page = win._log_page
        labels = {lbl.text(): lbl for lbl in page.findChildren(QLabel)}
        assert "Error" in labels and "Warning" in labels, "severity legend missing"

        # Verify selectability
        for text in ["Error", "Warning", "Info · Debug"]:
            lbl = labels[text]
            assert lbl.textInteractionFlags() & Qt.TextSelectableByMouse, f"Label {text} should be selectable"

        # Verify colors (as per dv-2e7 requirements)
        err, warn, info = labels["Error"], labels["Warning"], labels["Info · Debug"]
        assert STATE_ERROR_GRAPHIC in err.styleSheet()
        assert STATE_WARNING_GRAPHIC in warn.styleSheet()
        assert TEXT_MUTED in info.styleSheet()

    finally:
        win._on_log_toggled(False)
        for _ in range(10):
            qapp.processEvents()
