"""The searchable, task-grouped help index (dv-o8k).

Every (i) tooltip lands in ``ui.help_index`` under a curator task; the
Help page renders them grouped and filters as you type. Tests open the
detail view once so its tips exist, then search the index.
"""

from typing import Any

import curation.applog as applog


def _open_detail_defaults(win: Any):
    win._open_dataset("doi:10.5072/FK2/HELP", "Help test (tests)")


def test_tips_register_under_their_task_groups(win):
    _open_detail_defaults(win)
    win._show_help()
    try:
        from ui.help_index import help_entries

        entries = help_entries()
        assert entries, "no tips were registered — add_info_tip must feed the index"
        groups = {g for g, _n, _t in entries}
        assert "Checks" in groups
        assert "Respond" in groups
        assert "Queue" in groups
        assert "General" in groups
        # Specific tips land in their task groups.
        checks = {name for g, name, _t in entries if g == "Checks"}
        assert any("Checks" in n or "check" in n.lower() for n in checks)
        respond = {name for g, name, _t in entries if g == "Respond"}
        assert any(respond), "response tips must register under Respond"
    finally:
        win._show_dashboard()


def test_each_registered_tip_is_findable_by_search(win):
    _open_detail_defaults(win)
    win._show_help()
    try:
        from ui.help_index import help_entries

        win._ensure_help()
        for _g, name, text in help_entries():
            hits = [
                (g, n, tx)
                for g, n, tx in help_entries()
                if text.lower() in f"{n} {tx}".lower() or name.lower() in f"{n} {tx}".lower()
            ]
            assert hits, f"tip {name!r} is not findable"
    finally:
        win._show_dashboard()


def test_search_narrows_and_restores_the_list(win):
    _open_detail_defaults(win)
    win._show_help()
    try:
        pane = win._ensure_help()
        total = pane.visible_entry_count()
        assert total >= 4, f"expected the built tips to be listed, got {total}"
        pane._search.setText("metadata")
        narrowed = pane.visible_entry_count()
        assert 0 < narrowed < total
        pane._search.setText("zzzzz-no-such-tip")
        assert pane.visible_entry_count() == 0
        pane._search.setText("")
        assert pane.visible_entry_count() == total
    finally:
        win._show_dashboard()


def test_help_logs_index_build_count(win):
    applog.clear()
    win._show_help()
    try:
        lines = "\n".join(applog.lines())
        assert "Help index built:" in lines
    finally:
        win._show_dashboard()
