"""Worker registry must tolerate `finished` payloads.

Several workers emit `finished` with an argument (a list of datasets, a
metadata dict, a DatasetReport...). The registry slot that drops a worker
from `_LIVE_WORKERS` used to declare a single default argument, so Qt
bound the payload to it and `set.discard()` raised
``TypeError: unhashable type`` on dict/list/report payloads. The worker
then stayed registered for the life of the process.
"""

from typing import Any

from PySide6.QtCore import QThread, Signal

from ui import workers


class _DictPayloadWorker(QThread):
    finished = Signal(object)

    def run(self):
        self.finished.emit({"persistent_id": "doi:10.5072/FK2/REG"})


class _ListPayloadWorker(QThread):
    finished = Signal(list)

    def run(self):
        self.finished.emit([{"persistent_id": "doi:10.5072/FK2/REG"}])


class _ObjectPayloadWorker(QThread):
    finished = Signal(object)

    def run(self):
        self.finished.emit(_UnhashableReport())


class _UnhashableReport:
    # __hash__ = None makes instances unhashable: the registry must not
    # depend on the payload being hashable. mypy needs the ignore because
    # object.__hash__ is typed as Callable[[], int] (dv-hcg.28).
    __hash__ = None  # type: ignore[assignment]


def _run_and_flush(qapp: Any, worker: Any):
    worker.start()
    assert worker.wait(5000), "worker thread did not finish"
    for _ in range(10):
        qapp.processEvents()


def test_finished_payload_does_not_break_registry(qapp):
    payloads = [
        _DictPayloadWorker(),
        _ListPayloadWorker(),
        _ObjectPayloadWorker(),
    ]
    try:
        for worker in payloads:
            workers.register_worker(worker)
            assert worker in workers._LIVE_WORKERS
            _run_and_flush(qapp, worker)
            assert worker not in workers._LIVE_WORKERS, (
                f"{type(worker).__name__} stayed registered: the finished "
                "slot treated the signal payload as the worker"
            )
    finally:
        workers.stop_all_workers()
