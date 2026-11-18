"""Reads that are skipped because the queue row already answered them.

The dashboard's search payload knows whether a dataset is under curation.
The detail view uses that answer: a dataset with no draft has no
curation status, no label history and no version comparison, so those
calls are not sent.
"""


def _worker(draft_hint):
    from ui.workers import MetadataWorker

    return MetadataWorker(
        "https://example.invalid",
        "token",
        "doi:10.5072/FK2/A",
        draft_hint=draft_hint,
    )


def test_curation_reads_are_skipped_for_a_dataset_with_no_draft():
    names = _worker(False)._fetch_names()
    assert "curation" not in names
    assert "history" not in names
    assert "version_diff" not in names
    # The reads that always answer are still made.
    assert "metadata" in names
    assert "inventory" in names
    assert "versions" in names


def test_curation_reads_are_made_when_the_dataset_is_under_curation():
    names = _worker(True)._fetch_names()
    assert "curation" in names
    assert "history" in names
    assert "version_diff" in names


def test_curation_reads_are_made_when_nothing_is_known():
    names = _worker(None)._fetch_names()
    assert "curation" in names
    assert "version_diff" in names


def test_detail_view_takes_the_hint_from_the_queue_row(win):
    win._open_dataset(
        "doi:10.5072/FK2/HINT1",
        "Hint (tests)",
        {"state": "RELEASED", "has_draft": False},
    )
    assert win._detail._draft_hint() is False

    win._open_dataset(
        "doi:10.5072/FK2/HINT2",
        "Hint 2 (tests)",
        {"state": "DRAFT", "has_draft": True},
    )
    assert win._detail._draft_hint() is True

    # No row (a dataset opened outside the queue): ask for everything.
    win._open_dataset("doi:10.5072/FK2/HINT3", "Hint 3 (tests)")
    assert win._detail._draft_hint() is None


def test_detail_view_treats_an_unreadable_row_as_not_under_curation(win):
    win._open_dataset(
        "doi:10.5072/FK2/HINT4",
        "Hint 4 (tests)",
        {
            "state": "DRAFT",
            "has_draft": True,
            "access": {"state": "restricted", "reason": "draft_not_readable"},
        },
    )
    assert win._detail._draft_hint() is False


# -- replacing an open dataset (dv-n1d) -------------------------------------


def test_replacing_a_dataset_cancels_the_pending_first_load(win):
    """The deferred first load must not start on a view that is replaced.

    Otherwise the worker is a child of a view that is about to be
    destroyed, and destroying a view with a running QThread child aborts
    the process (the whole test run dies with 0xC0000409).
    """
    win._open_dataset("doi:10.5072/FK2/HINT5", "Hint 5 (tests)")
    first = win._detail
    assert first._auto_load_timer.isActive()
    win._open_dataset("doi:10.5072/FK2/HINT6", "Hint 6 (tests)")
    assert not first._auto_load_timer.isActive()


def test_opening_several_datasets_in_a_row_is_safe(win):
    """Opening A, then B, then C must not abort the app."""
    win._open_dataset("doi:10.5072/FK2/HINT7", "Hint 7 (tests)")
    win._open_dataset("doi:10.5072/FK2/HINT8", "Hint 8 (tests)")
    win._open_dataset("doi:10.5072/FK2/HINT9", "Hint 9 (tests)")
    assert win._detail is not None
    assert win._detail._pid == "doi:10.5072/FK2/HINT9"
