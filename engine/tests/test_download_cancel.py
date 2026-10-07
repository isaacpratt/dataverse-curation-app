"""Mid-download Cancel contract (step-5 behavioral minor).

The stop flag must stop both stream loops, never be retried, never be
swallowed by the originals "never-raises" handler, and leave no
truncated `_bundle.zip.part` behind — all offline, against fake clients.
"""

import io
import zipfile
from pathlib import Path

import pytest

from dataverse_client import DataverseClient, DownloadCancelled
from download_manager import DownloadManager

PID = "doi:10.5072/FK2/TESTCANCEL"


class _ChunkedResponse:
    """Minimal streaming response: yields 5 chunks, tracks how many."""

    status_code = 200
    url = "http://example.test/stream"
    headers: dict = {}

    def __init__(self):
        self.chunks_yielded = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        for _ in range(5):
            self.chunks_yielded += 1
            yield b"x" * 64


class _FakeSession:
    def __init__(self, response):
        self.calls = 0
        self._response = response

    def get(self, url, **kwargs):
        self.calls += 1
        return self._response


def _client_with_session(session):
    client = DataverseClient.__new__(DataverseClient)
    client._session = session
    client._api_token = None
    client._timeout = 5

    def _api(path):
        return "http://example.test" + path

    client._api = _api
    return client


def test_stream_cancel_mid_chunk_writes_one_chunk_and_never_retries(tmp_path):
    resp = _ChunkedResponse()
    session = _FakeSession(resp)
    client = _client_with_session(session)
    dest = tmp_path / "_bundle.zip.part"

    def is_cancelled():
        return resp.chunks_yielded >= 2

    with pytest.raises(DownloadCancelled):
        client._stream_download("/zip", {}, {}, dest, None, "test-zip", is_cancelled)

    assert session.calls == 1, "cancel must not trigger the retry loop"
    assert dest.read_bytes() == b"x" * 64, "exactly one chunk before stop"


def test_datafile_original_cancel_mid_chunk_never_retries(tmp_path):
    resp = _ChunkedResponse()
    session = _FakeSession(resp)
    client = _client_with_session(session)
    dest = tmp_path / "a.sav"

    def is_cancelled():
        return resp.chunks_yielded >= 2

    with pytest.raises(DownloadCancelled):
        client.download_datafile_original("7", dest, is_cancelled=is_cancelled)

    assert session.calls == 1, "cancel must not trigger the retry loop"


def test_bundle_cancel_unlinks_partial_part(tmp_path):
    class _CancelBundle:
        def download_dataset_zip(self, identifier, dest, version="draft", progress=None,
                                 is_cancelled=None):
            dest = Path(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"partial-zip")
            raise DownloadCancelled("bundle")

    mgr = DownloadManager(_CancelBundle(), tmp_path)
    with pytest.raises(DownloadCancelled):
        mgr.approve_and_download(PID, is_cancelled=lambda: False)

    staging = mgr.dataset_dir(PID)
    assert not (staging / "_bundle.zip.part").exists(), ".part must be cleaned up"
    assert not (staging / "_bundle.zip").exists(), "partial bundle must not publish"


def test_originals_cancel_propagates_and_removes_partial(tmp_path):
    class _CancelOriginals:
        def download_datafile_original(self, file_id, dest, progress=None, is_cancelled=None):
            Path(dest).write_bytes(b"partial-bytes")
            raise DownloadCancelled(f"datafile {file_id}")

    inv = [{
        "tabular": True, "id": "7", "original_name": "a.sav",
        "path": "a.sav", "original_size": 100,
    }]
    mgr = DownloadManager(_CancelOriginals(), tmp_path)
    with pytest.raises(DownloadCancelled):
        mgr.download_originals(PID, inventory=inv, max_workers=1)

    assert not (mgr.files_dir(PID) / "a.sav").exists(), "in-flight partial removed"


def test_originals_real_failure_still_swallowed(tmp_path):
    class _Boom:
        def download_datafile_original(self, file_id, dest, progress=None, is_cancelled=None):
            raise RuntimeError("server exploded")

    inv = [{
        "tabular": True, "id": "7", "original_name": "a.sav",
        "path": "a.sav", "original_size": 100,
    }]
    mgr = DownloadManager(_Boom(), tmp_path)
    staged = mgr.download_originals(PID, inventory=inv, max_workers=1)
    assert staged == [], "ordinary per-file failures stay non-fatal"


def test_happy_path_unaffected_by_live_stop_flag(tmp_path):
    class _OkClient:
        def download_dataset_zip(self, identifier, dest, version="draft", progress=None,
                                 is_cancelled=None):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                zf.writestr("data.txt", "hello")
            dest = Path(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(buf.getvalue())
            return dest

        def inventory(self, persistent_id):
            return []

    mgr = DownloadManager(_OkClient(), tmp_path)
    out = mgr.approve_and_download(PID, is_cancelled=lambda: False)
    assert (out / "data.txt").read_text(encoding="utf-8") == "hello"
