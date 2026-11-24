"""Streaming file hashing shared by staging and checksum verification."""

import hashlib
from pathlib import Path

from curation.client.constants import _STREAM_CHUNK


def hash_file(path: Path, algorithm: str) -> str:
    """Return the hex digest of `path` without loading the whole file."""
    digest = hashlib.new(algorithm)
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_STREAM_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()
