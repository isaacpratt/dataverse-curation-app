"""Record-export button (dv-vwt): the handler composes the record from the view's state and reports it in the log + status strip."""

import pytest


@pytest.fixture()
def view(qapp, tmp_path):
    """Create a bare DatasetDetailView with stubs for the export inputs."""
    from config import Config
    from ui.dataset_detail import DatasetDetailView

    try:
        cfg = Config.load(None)
    except Exception:
        cfg = Config()
    cfg.app.workspace = tmp_path
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    staged = dataset_dir / "files"
    staged.mkdir()
    (staged / "a.csv").write_text("a,b\n1,2\n", encoding="utf-8")

    v = DatasetDetailView.__new__(DatasetDetailView)
    v._pid = "doi:10.5072/FK2/REC"
    v._config = cfg
    v._ruleset = {}
    v._report = None
    v._inventory = []
    v._curation = {"label": "Approved"}
    v._logged = []

    class _StubDl:
        def dataset_dir(self, pid):
            return dataset_dir

        def files_dir(self, pid):
            return staged

    class _StubEdit:
        def toPlainText(self):
            return "Dear depositor…"

    v._dl_mgr = _StubDl()
    v._response_edit = _StubEdit()
    v._state = lambda: __import__("storage").open_state(cfg.app.workspace)

    def _log(action, notes="", details=None):
        v._logged.append((action, notes, details))

    v._log_action = _log
    v._status_msgs = []
    v._set_status = lambda msg, **_kw: v._status_msgs.append(msg)
    return v


def test_button_handler_writes_record(view):
    view._on_export_record()
    base = view._dl_mgr.dataset_dir(view._pid) / "curation-record"
    records = sorted(p for p in base.iterdir() if p.is_dir())
    assert len(records) == 1
    record = records[0]
    index = __import__("json").loads((record / "index.json").read_text(encoding="utf-8"))
    assert index["curation_label"] == "Approved"
    assert index["staged_files"] == 1
    assert any(a == "curation_record_exported" for a, _n, _d in view._logged)
    assert view._status_msgs and "Curation record written" in view._status_msgs[-1]


def test_handler_survives_missing_response_edit(view):
    del view._response_edit
    view._on_export_record()
    base = view._dl_mgr.dataset_dir(view._pid) / "curation-record"
    record = next(iter(base.iterdir()))
    assert not (record / "depositor_response.md").exists()


def test_decision_notes_flow_into_the_record(view):
    st = view._state()
    st.log_action(view._pid, "decision", notes="Revisions — add README")
    view._on_export_record()
    base = view._dl_mgr.dataset_dir(view._pid) / "curation-record"
    record = next(iter(base.iterdir()))
    decision = __import__("json").loads(
        (record / "decision.json").read_text(encoding="utf-8")
    )
    assert "Revisions" in decision["decision"]
