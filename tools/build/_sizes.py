"""One definition of a folder's size in decimal megabytes.

Both the build and the pack script print this number as "MB", so they must
share the unit as well as the name: build_app.py used binary MiB (1024**2)
while pack_app.py and check_pack.py used decimal MB (1e6), making the same
artefact read about 5% smaller in one report than in the other.
"""

from __future__ import annotations

from pathlib import Path


def dir_size_mb(path: Path) -> float:
    """Total bytes of the regular files under ``path``, in decimal MB."""
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file()) / 1e6
