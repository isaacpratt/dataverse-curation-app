"""Guard: colour literals live only in ui/theme.py.

The P2 token pass replaced every ``#rrggbb`` literal across ``ui/*.py``
with a theme token, so palette changes now happen in one place. These
tests fail if a hex literal sneaks back into a module, or if a token
fails to render inside a generated QSS string.
"""

import io
import re
import tokenize
from pathlib import Path

_HEX = re.compile(r"#[0-9a-fA-F]{6}(?![0-9a-fA-F])")
_UNRENDERED = re.compile(r"\{[A-Z][A-Z0-9_]{1,}\}")
_UI_DIR = Path(__file__).resolve().parents[1]


def _hex_string_hits():
    hits = []
    for path in sorted(_UI_DIR.glob("*.py")):
        if path.name == "theme.py":  # the one place raw hex is allowed
            continue
        src = path.read_text(encoding="utf-8")
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.STRING and _HEX.search(tok.string):
                hits.append(f"{path.name}:{tok.start[0]}")
    return hits


def test_no_hex_literals_outside_theme():
    assert _hex_string_hits() == []


def test_global_qss_renders_tokens():
    from ui.theme import global_qss

    qss = global_qss()
    assert "#004ccd" in qss  # PRIMARY actually landed in the stylesheet
    assert "{{" not in qss
    assert "}}" not in qss
    assert not _UNRENDERED.search(qss)  # no leftover {TOKEN}


def test_action_button_style_renders_tokens():
    from ui.theme import action_button_style

    qss = action_button_style()
    assert "#004ccd" in qss
    assert "{{" not in qss
    assert "}}" not in qss
    assert not _UNRENDERED.search(qss)
