"""One hashing and one base-URL key implementation (dv-dhm)."""

from __future__ import annotations

from pathlib import Path

from curation.client import caches
from curation.client.downloads import _DownloadsMixin
from curation.client.hashing import hash_file
from curation.config import base_url_key
from curation.download_manager import DownloadManager
from curation.review_rules import _norm_base


def test_hash_file_shared_by_staging_and_client(tmp_path: Path) -> None:
    target = tmp_path / "blob.bin"
    target.write_bytes(b"abc" * 1000)
    expected = hash_file(target, "sha256")
    assert not hasattr(DownloadManager, "_hash_file"), "staging still has its own hash helper"
    assert _DownloadsMixin.hash_file(target, "sha256") == expected
    assert hash_file(target, "sha1") == _DownloadsMixin.hash_file(target, "sha1")


def test_base_url_key_shared_by_rulesets_and_cache() -> None:
    for raw in ("HTTPS://Example.Test/", "https://example.test", "", "http://x/"):
        assert _norm_base(raw) == base_url_key(raw)
        assert caches._metadatablocks_disk_key(raw) == base_url_key(raw)
