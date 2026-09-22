"""Dispatch staged files to their format checks.

Per-file checks apply when a file's extension (lowercase) matches the Check's
extensions set. Dataset-level checks have empty extension sets and run on the
file set as a whole (e.g. inventory.extensions, dataset.filename_policy).
"""

from pathlib import Path
from typing import Type

from engine.checks import registry
from engine.checks.base import Check

# Trailing compression layers handled transparently by the inner check
# (fastq sniffs gzip magic bytes; tarfile opens "r:*").
_STRIPPABLE = {".gz", ".bz2", ".xz"}


def _match_suffixes(path: Path) -> set[str]:
    """Suffixes to match against check extensions.

    Compound names shed one outer compression layer ONLY when the inner
    check handles compression transparently (fastq sniffs gzip magic,
    tarfile opens "r:*"). Otherwise the outer layer wins so
    a.csv.bz2 does not mis-dispatch to CsvCheck (which cannot decompress)
    — it falls through to containers/unmatched instead.
    sample.fq.gz -> {.fq}, a.tar.gz -> {.tar}, a.csv.bz2 -> {.bz2}.
    Bare data.gz keeps {.gz} so it still reaches the containers check.
    """
    suffixes = [s.lower() for s in path.suffixes]
    if len(suffixes) > 1 and suffixes[-1] in _STRIPPABLE:
        inner = suffixes[-2]
        # fastq handles .fq/.fastq(+.gz); tar handles .tar(+any compression).
        if inner in {".fq", ".fastq", ".tar"} or ".tar" in suffixes[:-1]:
            suffixes = suffixes[:-1]
        else:
            # Keep only the outer compression suffix so containers or the
            # unmatched-types warning handles it honestly.
            return {suffixes[-1]}
    return set(suffixes) or {path.suffix.lower()}


def checks_for_file(path: Path) -> list[Type[Check]]:
    wanted = _match_suffixes(path)
    return [cls for cls in registry.values() if wanted & set(cls.extensions)]


def dataset_level_checks() -> list[Type[Check]]:
    return [cls for cls in registry.values() if not cls.extensions]