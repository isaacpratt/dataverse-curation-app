"""One folder-size unit for the build and pack reports."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.build._sizes import dir_size_mb  # noqa: E402


def test_dir_size_mb_is_decimal_and_counts_only_files(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()
    (tmp_path / "a.bin").write_bytes(b"x" * 1_000_000)
    (tmp_path / "nested" / "b.bin").write_bytes(b"y" * 500_000)
    assert dir_size_mb(tmp_path) == 1.5


def test_dir_size_mb_of_empty_folder_is_zero(tmp_path: Path) -> None:
    assert dir_size_mb(tmp_path) == 0.0
