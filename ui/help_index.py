"""Help index: every (i) tip in the app, grouped by curator task.

The kit's ``add_info_tip`` registers the paragraph(s) it hangs off a
card here, so the Help pane can offer the same text without hover
(dv-o8k). Grouping honours an explicit ``group=`` argument first, then
falls back to keyword matching on name + text, so tips added without a
group still land somewhere sensible. Empty groups are hidden by the
Help page.
"""

from __future__ import annotations

GROUP_ORDER = ["Queue", "Download", "Checks", "Respond", "General"]

_KEYWORDS = {
    "Queue": ("queue", "dashboard", "manifest", "preview", "log"),
    "Download": ("download", "staged", "staging"),
    "Checks": ("check", "metadata check", "auto-check"),
    "Respond": ("respond", "response", "findings", "assessment", "draft", "verdict"),
}

_entries: list[tuple[str, str, str]] = []
_seen: set[tuple[str, str, str]] = set()


def _classify(group: str, name: str, text: str) -> str:
    g = (group or "").strip()
    if g:
        return g if g in GROUP_ORDER else "General"
    haystack = f"{name}\n{text}".lower()
    for grp, keywords in _KEYWORDS.items():
        if any(k in haystack for k in keywords):
            return grp
    return "General"


def register_help(group: str, name: str, text: str) -> None:
    """Add an entry; duplicates (same group, name, text) are ignored."""
    name = str(name or "").strip()
    text = str(text or "").strip()
    if not text:
        return
    g = _classify(group, name, text)
    key = (g, name, text)
    if key in _seen:
        return
    _seen.add(key)
    _entries.append((g, name, text))


def help_entries() -> list[tuple[str, str, str]]:
    """All registered (group, name, text) tuples, group order, stable."""
    order = {g: i for i, g in enumerate(GROUP_ORDER)}
    return sorted(_entries, key=lambda e: (order.get(e[0], len(order)), e[1]))


def grouped(query: str = "") -> dict[str, list[tuple[str, str]]]:
    """Group entries by task, optionally filtered by a case-insensitive query."""
    q = query.strip().lower()
    out: dict[str, list[tuple[str, str]]] = {g: [] for g in GROUP_ORDER}
    for g, name, text in help_entries():
        if q and q not in g.lower() and q not in name.lower() and q not in text.lower():
            continue
        out[g].append((name, text))
    return {g: items for g, items in out.items() if items}


def clear_for_tests() -> None:
    """Empty the registry (tests only)."""
    _entries.clear()
    _seen.clear()
