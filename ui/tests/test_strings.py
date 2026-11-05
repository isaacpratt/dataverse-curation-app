"""Guard: interface text lives in ``ui/assets/strings.json``.

The GUI copy was externalised into a UTF-8 JSON catalogue so wording can be
reviewed, diffed and translated without touching behaviour.  These tests keep
the catalogue and the code in sync:

- the file parses and every leaf is a non-empty string;
- every ``t(...)`` / ``tn(...)`` key used in ``ui/`` exists in the catalogue;
- every dotted name shaped like a catalogue key resolves, even when it is
  reached through a lookup table rather than a direct call;
- every catalogue entry is referenced by the application — an orphan is rot;
- every ``{placeholder}`` a catalogue value declares is supplied at the call
  site (and vice versa), so a renamed placeholder cannot silently render the
  raw ``{name}`` in the UI;
- no module hard-codes user-visible wording any more.
"""

import ast
import re
from pathlib import Path
from string import Formatter

import pytest

from ui.i18n import has, keys, t

_UI_DIR = Path(__file__).resolve().parents[1]
_CATALOG = _UI_DIR / "assets" / "strings.json"

# Keys that intentionally live outside the catalogue.
_ALLOWLIST = {
    "ui.i18n",
}

# Calls that look like a lookup but are not one (helpers named ``t``).
_LOOKUP_NAMES = {"t", "tn"}

# The shape every catalogue key has: dotted lower-case identifiers.
_KEY_SHAPE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")


def _placeholders(value: str) -> set[str]:
    """Real ``{name}`` placeholders in a catalogue value (``{{`` is literal)."""
    out: set[str] = set()
    try:
        for _literal, field, _spec, _conv in Formatter().parse(value):
            if field:
                out.add(field.split(".")[0].split("[")[0])
    except ValueError:
        return set()
    return out


def _python_files() -> list[Path]:
    files = sorted(_UI_DIR.glob("*.py"))
    files += sorted((_UI_DIR / "tests").glob("*.py"))
    entry = _UI_DIR.parent / "main.py"
    if entry.is_file():
        files.append(entry)
    return files


def _app_files() -> list[Path]:
    """Application code only — tests never count as a catalogue reference."""
    files = sorted(_UI_DIR.glob("*.py"))
    entry = _UI_DIR.parent / "main.py"
    if entry.is_file():
        files.append(entry)
    return files


def _string_constants(path: Path) -> list[tuple[int, str]]:
    """Every string literal in ``path`` with its line number."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def _key_like(value: str, namespaces: set[str]) -> bool:
    """True for a string that is meant to be a catalogue key.

    A dotted lower-case name whose first segment is a catalogue namespace —
    the shape every key has (``dashboard.filters.all``).  Matching on the
    namespace keeps unrelated dotted strings (module paths, CSS selectors,
    log sentences) out.
    """
    if not _KEY_SHAPE.match(value):
        return False
    head = value.split(".", 1)[0]
    return head in namespaces


def _catalog_data() -> dict:
    import json

    with _CATALOG.open(encoding="utf-8") as fh:
        return json.load(fh)


def _lookup_calls() -> list[tuple[Path, int, str, set[str]]]:
    """Every ``t("key", ...)`` / ``tn("key", count, ...)`` call in ui/.

    Returns ``(path, line, key, placeholders_supplied)`` tuples.
    """
    out: list[tuple[Path, int, str, set[str]]] = []
    for path in _python_files():
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        # Only trust calls on the imported catalogue helper, not on a local
        # variable that happens to be called ``t``.
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("i18n"):
                for alias in node.names:
                    if alias.name in _LOOKUP_NAMES:
                        imported.add(alias.asname or alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "ui.i18n":
                        imported.add(alias.asname or alias.name)
        if not imported:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if name not in imported:
                continue
            if not node.args:
                continue
            first = node.args[0]
            if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
                continue
            supplied: set[str] = set()
            for kw in node.keywords:
                if kw.arg:
                    supplied.add(kw.arg)
            # tn(key, count, ...) takes the count positionally.
            if name == "tn" and len(node.args) > 1:
                supplied.add("count")
                supplied.add("n")
            out.append((path, node.lineno, first.value, supplied))
    return out


def _leaf_values(node, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    if isinstance(node, dict):
        for name, child in node.items():
            out.update(_leaf_values(child, f"{prefix}.{name}" if prefix else name))
    elif isinstance(node, str):
        out[prefix] = node
    return out


# ---------------------------------------------------------------- catalogue


def test_catalog_exists():
    assert _CATALOG.is_file(), f"missing catalogue: {_CATALOG}"


def test_catalog_parses():
    data = _catalog_data()
    assert isinstance(data, dict)
    assert data, "catalogue is empty"


def test_catalog_leaves_are_non_empty_strings():
    for key, value in _leaf_values(_catalog_data()).items():
        assert isinstance(value, str), f"{key} is not a string"
        assert value.strip(), f"{key} is empty"


def test_catalog_has_no_placeholder_only_values():
    """A value that is only ``{name}`` means the copy was never written."""
    for key, value in _leaf_values(_catalog_data()).items():
        stripped = value.strip()
        if not (stripped.startswith("{") and stripped.endswith("}")):
            continue
        # All-placeholder values are fine as long as they carry real words
        # outside the braces (e.g. "{sub}\\nLast refresh: {when}").
        outside = re.sub(r"\{[A-Za-z_][A-Za-z0-9_]*\}", "", stripped).strip()
        assert outside, f"{key} is an unwritten placeholder"


# ------------------------------------------------------------------ lookups


def test_lookup_keys_exist():
    missing = []
    for path, line, key, _supplied in _lookup_calls():
        if key in _ALLOWLIST:
            continue
        if not has(key):
            missing.append(f"{path.name}:{line} -> {key}")
    assert missing == [], "catalogue is missing keys:\n" + "\n".join(missing)


def test_key_like_strings_exist():
    """Any dotted name shaped like a catalogue key must resolve.

    ``t("key")`` calls are checked above; this covers keys reached through
    a lookup table (``_CAPTION_KEYS``) or a variable, which the call-based
    scan cannot see.  A renamed key in such a table would otherwise render
    the raw key in the interface.
    """
    namespaces = set(_catalog_data())
    missing = []
    for path in _app_files():
        for line, value in _string_constants(path):
            if not _key_like(value, namespaces):
                continue
            if value in _ALLOWLIST:
                continue
            if not has(value):
                missing.append(f"{path.name}:{line} -> {value}")
    assert missing == [], "catalogue is missing keys:\n" + "\n".join(missing)


def test_no_orphan_catalog_entries():
    """Every catalogue entry must be referenced by the application.

    Unreferenced entries are rot: they look like live copy but nothing can
    show them, and they hide the fact that a wording change never reached
    the screen.
    """
    namespaces = set(_catalog_data())
    referenced: set[str] = set()
    for path in _app_files():
        for _line, value in _string_constants(path):
            if _key_like(value, namespaces):
                referenced.add(value)
    orphans = sorted(set(_leaf_values(_catalog_data())) - referenced)
    assert orphans == [], "unused catalogue entries:\n" + "\n".join(orphans)


def test_lookup_keys_are_reachable():
    known = set(keys())
    unknown = sorted({key for _p, _l, key, _s in _lookup_calls() if key not in known})
    assert unknown == []


def test_lookup_placeholders_match_catalog():
    """Call sites must supply every placeholder the catalogue value declares."""
    leaves = _leaf_values(_catalog_data())
    problems = []
    for path, line, key, supplied in _lookup_calls():
        value = leaves.get(key)
        if value is None:
            continue
        missing = _placeholders(value) - supplied
        if missing:
            problems.append(
                f"{path.name}:{line} -> {key} missing {sorted(missing)}"
            )
    assert problems == [], "placeholder mismatches:\n" + "\n".join(problems)


def test_lookup_renders_without_raw_braces():
    """The catalogue value must format cleanly at every call site.

    ``t()`` falls back to the raw value when formatting fails, which would
    show ``{name}`` in the UI — so a call that cannot format is a failure.
    """
    leaves = _leaf_values(_catalog_data())
    problems = []
    for path, line, key, supplied in _lookup_calls():
        value = leaves.get(key)
        if value is None:
            continue
        # Integers satisfy both plain and numeric (``{n:,}``) format specs.
        dummies = {name: 0 for name in supplied}
        try:
            expected = value.format(**dummies)
        except (KeyError, IndexError, ValueError) as exc:
            problems.append(f"{path.name}:{line} -> {key} cannot format: {exc}")
            continue
        if t(key, **dummies) != expected:
            problems.append(f"{path.name}:{line} -> {key} rendered differently")
    assert problems == [], "unfilled placeholders:\n" + "\n".join(problems)


# -------------------------------------------------------------- leftovers

# Names of the widgets that hold the (already externalised) copy.
_TEXT_ATTRS = {
    "setText",
    "setToolTip",
    "setPlaceholderText",
    "setAccessibleName",
    "setAccessibleDescription",
    "setWindowTitle",
    "setStatusTip",
    "setWhatsThis",
    "show_info",
    "show_warning",
    "show_critical",
    "show_question",
    "confirm",
    "make_card",
    "make_combo",
    "make_search_field",
    "add_info_tip",
    "AppButton",
    "QLabel",
    "QPushButton",
    "setHeaderLabels",
    "addRow",
    "addTab",
    "QFileDialog.getSaveFileName",
    "QFileDialog.getOpenFileName",
    "QInputDialog.getText",
    "QInputDialog.getItem",
    "QMessageBox.information",
    "QMessageBox.warning",
    "QMessageBox.critical",
    "QMessageBox.question",
}


def _literal_text_calls() -> list[str]:
    """User-visible calls still fed with a plain literal string."""
    hits: list[str] = []
    for path in _python_files():
        if path.name in ("i18n.py", "status_text.py"):
            continue
        if path.parent.name == "tests":
            continue  # tests may legitimately spell out literal copy
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if name not in _TEXT_ATTRS:
                continue
            for arg in node.args:
                if not isinstance(arg, ast.Constant) or not isinstance(arg.value, str):
                    continue
                value = arg.value.strip()
                if not value or len(value) < 2:
                    continue
                # Not interface copy: css, urls, object names, format ids.
                if any(
                    marker in value
                    for marker in (
                        "QWidget",
                        "QLabel",
                        "QPushButton",
                        "QListWidget",
                        "QTreeView",
                        "QScrollArea",
                        "QTextEdit",
                        "QFrame",
                        "QProgressBar",
                        "QTable",
                        "border",
                        "background",
                        "font-size",
                        "padding",
                        "color:",
                        "://",
                        "http",
                        ".md",
                        ".json",
                        ".csv",
                        "QSS",
                    )
                ):
                    continue
                hits.append(f"{path.name}:{node.lineno} {name}({value!r})")
    return hits


def test_no_inline_interface_copy():
    hits = _literal_text_calls()
    assert hits == [], "inline interface copy found:\n" + "\n".join(hits)


# Markup-only fragments are structural (html tags, qss), not copy.
_MARKUP_FRAGMENTS = {
    "<b>",
    "</b>",
    "</b><br>",
    "<br>",
    "<br><br>",
    "<a href='",
    "' style='color:",
    "; text-decoration:none;'>",
    "</a>",
}


def _fstring_text_calls() -> list[str]:
    """Text calls built with an f-string that still carries literal words."""
    hits: list[str] = []
    for path in _python_files():
        if path.name in ("i18n.py", "status_text.py"):
            continue
        if path.parent.name == "tests":
            continue
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if name not in _TEXT_ATTRS:
                continue
            for arg in node.args:
                if not isinstance(arg, ast.JoinedStr):
                    continue
                parts = [
                    value.value
                    for value in arg.values
                    if isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                    and value.value.strip()
                ]
                words = [p for p in parts if p not in _MARKUP_FRAGMENTS]
                if words:
                    hits.append(f"{path.name}:{node.lineno} {name} f-string {words}")
    return hits


def test_no_inline_interface_copy_in_fstrings():
    hits = _fstring_text_calls()
    assert hits == [], "inline interface copy in f-strings:\n" + "\n".join(hits)


def test_cli_help_text_is_catalogue_backed():
    """argparse copy in main.py must come from the catalogue."""
    entry = _UI_DIR.parent / "main.py"
    if not entry.is_file():
        return
    tree = ast.parse(entry.read_text(encoding="utf-8"))
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = getattr(fn, "id", None) or getattr(fn, "attr", None)
        if name == "ArgumentParser":
            wanted = ("description",)
        elif name == "add_argument":
            wanted = ("help",)
        elif name == "error":
            wanted = ()
        else:
            continue
        if name == "error":
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    hits.append(f"main.py:{node.lineno} error({arg.value!r})")
            continue
        for kw in node.keywords:
            if kw.arg in wanted and isinstance(kw.value, ast.Constant):
                hits.append(
                    f"main.py:{node.lineno} {name}({kw.arg}={kw.value.value!r})"
                )
    assert hits == [], "inline CLI copy found:\n" + "\n".join(hits)


@pytest.mark.parametrize("namespace", sorted(_catalog_data()))
def test_namespace_has_leaves(namespace):
    leaves = _leaf_values(_catalog_data())
    owned = [key for key in leaves if key.split(".")[0] == namespace]
    assert owned, f"namespace '{namespace}' has no entries"
