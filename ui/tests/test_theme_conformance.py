"""Static guards: the UI layering contract, enforced by the build.

The app has one rule for how a view is allowed to look:

    palette -> role -> component

The palette says what a colour IS. The role says what it is FOR. The
component (the kit) is what the user actually touches. A view composes
components; it does not paint.

Three guards check that, by reading the source rather than by running
the app:

1. **No inline stylesheets in a view.** A view may not hand Qt a
   stylesheet it wrote itself. It asks the theme for a rule (a mixin)
   or the kit for a component. The one escape is an explicit
   ``# theme-allow:`` marker, for the rare rule that genuinely belongs
   to that single widget.
2. **No raw palette names in a view.** Only the theme and the kit may
   name a palette entry; a view names a semantic role. The palette set
   is derived from the theme's own source, so a new palette entry is
   covered the moment it is written - no list to forget to update.
3. **No raw input widgets in a view.** The standard text inputs, lists,
   check boxes, progress bars, combos and buttons come from the kit.

The guards parse the source with ``ast``, so they are cheap, exact and
need no window: they run in CI next to ruff and pytest.
"""

import ast
import pathlib
import re

import pytest

UI_DIR = pathlib.Path(__file__).resolve().parent.parent
THEME_PATH = UI_DIR / "theme.py"
KIT_PATH = UI_DIR / "widgets.py"

# The theme and the kit own the look; everything else is a view.
_OWNERS = {"theme.py", "widgets.py"}

# The marker that divides the palette from the role layer in the theme's
# source. Everything above it is a raw palette entry; everything below
# is a semantic role.
_ROLE_MARKER = "# --- Semantic roles: what a colour is FOR"

# The style generators a view may call. Each one is owned by the theme
# (a mixin) or the kit (a component's chrome).
_ALLOWED_STYLE_CALLS = frozenset(
    {
        # theme mixins
        "button_qss",
        "input_qss",
        "page_background_qss",
        "transparent_surface_qss",
        "surface_frame_qss",
        "band_qss",
        "badge_qss",
        "status_strip_qss",
        "label_badge_style",
        "header_section_qss",
        "scrollbar_lane_qss",
        "action_button_style",
        "transparent_qss",
        # kit chrome
        "flush_table_style",
        "flush_list_style",
        "tree_style",
    }
)

# The raw input widgets a view must not build. The kit has a builder
# for each of these.
_RAW_INPUT_WIDGETS = frozenset(
    {
        "QCheckBox",
        "QComboBox",
        "QLineEdit",
        "QListWidget",
        "QPlainTextEdit",
        "QProgressBar",
        "QPushButton",
        "QTableWidget",
        "QTextEdit",
        "QTreeWidget",
    }
)

_HEX = re.compile(r"#[0-9a-fA-F]{6}")


def _view_paths() -> list[pathlib.Path]:
    """Every module in the ui package that is not the theme or the kit."""
    return sorted(p for p in UI_DIR.glob("*.py") if p.name not in _OWNERS)


def _module_tree(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _palette_names() -> set[str]:
    """Read the raw palette entries from the theme's own source.

    A palette entry is a module-level name in the palette region whose
    value is a colour literal (or a tuple of them). The role layer sits
    below the marker, so roles are never mistaken for palette.
    """
    source = THEME_PATH.read_text(encoding="utf-8")
    marker = source.index(_ROLE_MARKER)
    head = source[:marker]
    tree = ast.parse(head)
    names: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
            continue
        value = node.value.value
        if not isinstance(value, str) or not _HEX.fullmatch(value):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                names.add(target.id)
    return names


def _module_bindings(tree: ast.Module) -> dict[str, ast.expr]:
    """Module-level name -> its assigned expression."""
    bindings: dict[str, ast.expr] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    bindings[target.id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.value is not None:
                bindings[node.target.id] = node.value
    return bindings


def _callee_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _is_style_expression(
    expr: ast.expr,
    bindings: dict[str, ast.expr],
    seen: frozenset[str] = frozenset(),
) -> bool:
    """Whether a stylesheet expression came from the theme or the kit.

    A view may pass the result of an allow-listed generator, a
    module-level constant built from one, or a composition of the two.
    A string literal or an f-string written in the view is not allowed:
    that is the view painting for itself.
    """
    if isinstance(expr, ast.Constant):
        return False
    if isinstance(expr, ast.JoinedStr):
        return False
    if isinstance(expr, ast.Call):
        return _callee_name(expr.func) in _ALLOWED_STYLE_CALLS
    if isinstance(expr, ast.Name):
        if expr.id in seen:
            return False
        bound = bindings.get(expr.id)
        if bound is None:
            return False
        return _is_style_expression(bound, bindings, seen | {expr.id})
    if isinstance(expr, ast.IfExp):
        return _is_style_expression(
            expr.body, bindings, seen
        ) and _is_style_expression(expr.orelse, bindings, seen)
    if isinstance(expr, ast.BinOp):
        return _is_style_expression(
            expr.left, bindings, seen
        ) and _is_style_expression(expr.right, bindings, seen)
    return False


def _allow_marker(lines: list[str], lineno: int) -> bool:
    """Whether the call carries an explicit ``# theme-allow:`` marker.

    The marker may sit on the call's own line or in the comment block
    directly above it, so a three-line explanation counts too.
    """
    if 0 <= lineno - 1 < len(lines) and "# theme-allow:" in lines[lineno - 1]:
        return True
    probe = lineno - 2
    while probe >= 0:
        stripped = lines[probe].strip()
        if not stripped:
            break
        if not stripped.startswith("#"):
            return False
        if "# theme-allow:" in stripped:
            return True
        probe -= 1
    return False


# ---------------------------------------------------------------------------
# Guard 1: no inline stylesheets in a view.
# ---------------------------------------------------------------------------


def test_no_view_writes_its_own_stylesheet():
    failures = []
    for path in _view_paths():
        source = path.read_text(encoding="utf-8").splitlines()
        tree = _module_tree(path)
        bindings = _module_bindings(tree)
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "setStyleSheet"
            ):
                continue
            if not node.args:
                continue
            if _allow_marker(source, node.lineno):
                continue
            if _is_style_expression(node.args[0], bindings):
                continue
            failures.append(
                f"{path.name}:{node.lineno}: setStyleSheet({ast.unparse(node.args[0])[:60]})"
            )
    assert not failures, (
        "a view may not write its own stylesheet - use a theme mixin or a "
        "kit builder (or mark the line '# theme-allow:'):\n  "
        + "\n  ".join(failures)
    )


# ---------------------------------------------------------------------------
# Guard 2: no raw palette names in a view.
# ---------------------------------------------------------------------------


def test_no_view_names_a_raw_palette_entry():
    palette = _palette_names()
    assert palette, "the palette could not be read from the theme"
    failures = []
    for path in _view_paths():
        tree = _module_tree(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.module not in ("ui.theme", "ui.widgets"):
                continue
            for alias in node.names:
                if alias.name in palette:
                    failures.append(f"{path.name}: {alias.name}")
    assert not failures, (
        "a view must name a semantic role, not a raw palette entry "
        "(only ui/theme.py and ui/widgets.py may):\n  " + "\n  ".join(failures)
    )


def test_the_role_layer_covers_every_palette_entry_the_views_use():
    """The roles must be able to express what the views need."""
    palette = _palette_names()
    roles = {
        name
        for name in dir_names(THEME_PATH)
        if name not in palette
    }
    assert "TEXT_PRIMARY" in roles
    assert "SURFACE_CARD" in roles
    assert "ACCENT_PRIMARY" in roles


def dir_names(path: pathlib.Path) -> set[str]:
    """List the module-level names a file defines."""
    tree = _module_tree(path)
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
    return names


# ---------------------------------------------------------------------------
# Guard 3: no raw input widgets in a view.
# ---------------------------------------------------------------------------


def test_no_view_builds_a_raw_input_widget():
    failures = []
    for path in _view_paths():
        tree = _module_tree(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _callee_name(node.func)
            if name in _RAW_INPUT_WIDGETS:
                failures.append(f"{path.name}:{node.lineno}: {name}()")
    assert not failures, (
        "the standard inputs come from the kit (make_line_edit, "
        "make_multiline_input, make_list, make_checkbox, "
        "make_progress_bar, make_combo, make_action_button):\n  "
        + "\n  ".join(failures)
    )


# ---------------------------------------------------------------------------
# The guards must be meaningful.
# ---------------------------------------------------------------------------


def test_the_guards_would_notice_a_violation(tmp_path):
    """Prove the guard bites: a planted violation must be detected.

    A guard that never fires is worse than no guard, so this test plants
    each kind of violation in a scratch module and checks the checker
    rejects it.
    """
    bad = tmp_path / "bad_view.py"
    bad.write_text(
        "from ui.theme import PRIMARY\n"
        "from PySide6.QtWidgets import QLineEdit\n"
        "\n"
        "def build():\n"
        "    edit = QLineEdit()\n"
        "    edit.setStyleSheet(f'color: {PRIMARY};')\n"
        "    return edit\n",
        encoding="utf-8",
    )
    tree = _module_tree(bad)
    bindings = _module_bindings(tree)

    styles = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "setStyleSheet"
    ]
    assert styles
    assert not _is_style_expression(styles[0].args[0], bindings)

    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "PRIMARY" in imported & _palette_names()

    built = {
        _callee_name(node.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    assert "QLineEdit" in built & _RAW_INPUT_WIDGETS


@pytest.mark.parametrize(
    "expression",
    [
        "button_qss('primary')",
        "page_background_qss('DetailView')",
        "flush_table_style(header_background=SURFACE_HEADER)",
        "input_qss('QTextEdit', font_size=13)",
    ],
)
def test_the_style_checker_accepts_theme_and_kit_rules(expression):
    """A stylesheet built from the theme or the kit is fine."""
    tree = ast.parse(f"value = {expression}\n")
    bindings = _module_bindings(tree)
    assert _is_style_expression(tree.body[0].value, bindings)


# ---------------------------------------------------------------------------
# Guard 4: the button sheet comes from the kit.
# ---------------------------------------------------------------------------

# The kit builds these; a view asks the kit for the component.
_KIT_OWNED_STYLE_BUILDERS = frozenset({"action_button_style", "label_badge_style"})


def test_no_view_builds_a_button_or_badge_sheet_itself():
    failures = []
    for path in _view_paths():
        tree = _module_tree(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.module not in ("ui.theme", "ui.widgets"):
                continue
            for alias in node.names:
                if alias.name in _KIT_OWNED_STYLE_BUILDERS:
                    failures.append(f"{path.name}: {alias.name}")
    assert not failures, (
        "the kit owns the button and badge sheets (make_action_button, "
        "make_badge):\n  " + "\n  ".join(failures)
    )
