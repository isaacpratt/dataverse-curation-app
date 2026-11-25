"""Diff logic and environment pin for the golden gate (dv-ufu.1).

These tests run in the default suite: they do not render the app and need no
blessed baseline, so a broken comparator fails before anyone trusts a
screenshot result.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from ui.tests import golden


def _image(path: Path, color: tuple[int, int, int] = (20, 40, 60)) -> None:
    Image.new("RGB", (40, 40), color).save(path)


def test_diff_detects_a_small_change(tmp_path: Path) -> None:
    baseline = tmp_path / "a.png"
    candidate = tmp_path / "b.png"
    _image(baseline)
    _image(candidate, (21, 40, 60))
    diff = golden.compare(baseline, candidate)
    assert diff.max_delta == 1
    # Below the 12/255 threshold: a non-zero bbox but no failing pixels.
    assert diff.changed_percent == 0.0
    assert diff.bbox is not None
    assert not diff.fails("any-case")


def test_diff_rejects_a_large_change_and_size_mismatch(tmp_path: Path) -> None:
    baseline = tmp_path / "a.png"
    candidate = tmp_path / "b.png"
    _image(baseline)
    _image(candidate, (120, 40, 60))
    assert golden.compare(baseline, candidate).fails("any-case")

    Image.new("RGB", (50, 50), (20, 40, 60)).save(candidate)
    diff = golden.compare(baseline, candidate)
    assert diff.max_delta == 255
    assert diff.changed_percent == 100.0


def test_environment_pin_fails_loudly(tmp_path: Path, monkeypatch: Any) -> None:
    meta = tmp_path / "baseline.meta"
    meta.write_text(json.dumps({"python": "different"}), encoding="utf-8")
    monkeypatch.setattr(golden, "META_PATH", meta)
    monkeypatch.setenv("QT_QPA_PLATFORM", "windows")
    with pytest.raises(AssertionError, match="environment drift"):
        golden.check_environment()
