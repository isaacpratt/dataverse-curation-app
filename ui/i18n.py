"""Externalised interface text.

Every user-visible string in the GUI lives in ``ui/assets/strings.json`` and
is looked up by a dotted key such as ``"dashboard.queue.title"``.  Keeping the
text out of the Python modules means copy can be reviewed, diffed and
translated without touching behaviour.

Why JSON (and not Qt ``.ts``/``.qm``, gettext ``.po`` or YAML):

- standard library only (the project supports Python 3.10, so ``tomllib`` is
  not available), no build step and no new runtime dependency;
- plain UTF-8 text, one file, easy to review in a pull request;
- nested objects give the same namespacing Qt contexts and gettext domains
  provide, without generated msgids;
- ships through the existing PyInstaller ``--add-data "ui/assets;ui/assets"``
  rule, so frozen builds need no extra packaging step.

The loader is intentionally forgiving at runtime: a missing key returns the
key itself instead of crashing a screen.  ``ui/tests/test_strings.py`` fails
the build when code references a key that is not in the catalogue, so missing
entries are caught before release.

Usage::

    from ui.i18n import t, tn

    title = t("dashboard.queue.title")
    status = t("dashboard.queue.status", shown=3, total=7)
    files = tn("detail.files.count", len(files), count=len(files))
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

__all__ = ["t", "tn", "has", "keys", "reload"]

_CATALOG_NAME = "strings.json"


def _candidate_paths() -> list[Path]:
    """Catalogue locations for source trees and frozen builds."""
    here = Path(__file__).resolve().parent
    candidates = [here / "assets" / _CATALOG_NAME]
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        candidates.insert(0, Path(meipass) / "ui" / "assets" / _CATALOG_NAME)
        candidates.insert(1, Path(meipass) / "assets" / _CATALOG_NAME)
    return candidates


def _load() -> dict[str, Any]:
    for path in _candidate_paths():
        try:
            with path.open(encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
        except Exception:
            continue
    return {}


_CATALOG: dict[str, Any] = _load()


def reload() -> None:
    """Re-read the catalogue (tests and live copy edits)."""
    global _CATALOG
    _CATALOG = _load()


def _lookup(key: str) -> Any:
    node: Any = _CATALOG
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def has(key: str) -> bool:
    """Return True when ``key`` resolves to a string leaf."""
    return isinstance(_lookup(key), str)


def keys() -> list[str]:
    """Every dotted leaf key in the catalogue (for validation/tests)."""
    out: list[str] = []

    def walk(node: Any, prefix: str) -> None:
        if isinstance(node, dict):
            for name, child in node.items():
                walk(child, f"{prefix}.{name}" if prefix else name)
        elif isinstance(node, str):
            out.append(prefix)

    walk(_CATALOG, "")
    return out


def t(key: str, /, **values: object) -> str:
    """Return the text for ``key``, formatting ``{name}`` placeholders.

    Literal braces in a catalogue value are escaped (``{{`` / ``}}``), so a
    value that documents another template syntax still renders correctly.
    Missing keys fall back to the key so a screen never crashes on a typo;
    the string test catches them in CI.

    ``key`` is positional-only so a catalogue value may itself use a
    ``{key}`` placeholder without colliding with this parameter.
    """
    text = _lookup(key)
    if not isinstance(text, str):
        return key
    try:
        return text.format(**values)
    except (KeyError, IndexError, ValueError):
        return text


def tn(key: str, count: int, /, **values: object) -> str:
    """Plural-aware lookup: ``key.one`` when count == 1, else ``key.other``.

    Falls back to the unsuffixed key when no plural variants exist.
    """
    variant = "one" if count == 1 else "other"
    chosen = _lookup(f"{key}.{variant}")
    if isinstance(chosen, str):
        values.setdefault("count", count)
        values.setdefault("n", count)
        return t(f"{key}.{variant}", **values)
    values.setdefault("count", count)
    values.setdefault("n", count)
    return t(key, **values)
