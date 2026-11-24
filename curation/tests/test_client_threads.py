"""Thread-safety of the Dataverse client's HTTP sessions (dv-u9i)."""

from __future__ import annotations

import threading
from typing import Any, cast

from curation.client import DataverseClient


def test_each_thread_gets_its_own_session() -> None:
    client = DataverseClient("https://demo.test", "tok")
    seen: dict[int, int] = {}
    barrier = threading.Barrier(4)

    def worker(index: int) -> None:
        session = client._session
        seen[index] = id(session)
        # Holding the reference must stay stable for the life of the thread.
        barrier.wait()
        assert client._session is session

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()

    assert len(seen) == 4
    assert len(set(seen.values())) == 4
    client.close()


def test_assigned_session_is_an_override_for_every_thread() -> None:
    class FakeSession:
        pass

    client = DataverseClient("https://demo.test", "tok")
    fake = FakeSession()
    client._session = fake  # type: ignore[assignment]
    assert cast(Any, client._session) is fake

    seen: list[bool] = []

    def worker() -> None:
        seen.append(cast(Any, client._session) is fake)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(timeout=5)
    assert seen == [True]
