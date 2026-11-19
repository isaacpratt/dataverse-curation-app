"""Dispatch staged files to their format checks.

``scope`` decides where a check's findings live: a ``dataset``-scoped check
runs once over the file set as a whole (e.g. inventory.extensions,
inventory.access) and reports under ``dataset_checks``; a ``file``-scoped
check runs once per file and reports in that file's ``checks``. ``extensions``
is only the dispatch axis for file-scoped checks — the two axes are
independent (dv-p1d), so a cross-file check may read .csv and still be
dataset-scoped.
"""

from pathlib import Path

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


def checks_for_file(path: Path) -> list[type[Check]]:
    """File-scoped checks whose extensions match a file's suffixes.

    A dataset-scoped check is never returned here, whatever extensions it
    declares: its findings belong to the dataset, not to one file.
    """
    wanted = _match_suffixes(path)
    return [
        cls
        for cls in registry.values()
        if getattr(cls, "scope", "file") == "file" and wanted & set(cls.extensions)
    ]


def dataset_level_checks() -> list[type[Check]]:
    """Dataset-scoped checks (run once per staged dataset, not per file)."""
    return [cls for cls in registry.values() if getattr(cls, "scope", "file") == "dataset"]
