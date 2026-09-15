"""Report runner: dispatches checks over a staged dataset directory and
aggregates findings into a DatasetReport (docs/report-contract.md).
"""

import mimetypes
from pathlib import Path
from typing import List

from engine import __version__
from engine.checks.base import CheckResult
from engine.dispatcher import checks_for_file, dataset_level_checks
from engine.report import DatasetReport, FileEntry


def collect_files(dataset_dir: Path) -> List[Path]:
    """Staged files, sorted. Symlinks are skipped (a staged symlink could
    point outside the dataset dir) and vanishing paths are ignored."""
    out = []
    for path in sorted(dataset_dir.rglob("*")):
        try:
            if path.is_symlink() or not path.is_file():
                continue
            out.append(path)
        except OSError:
            continue
    return out


def guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    return mime or "application/octet-stream"


def _safe_run(check_cls, files: List[Path]) -> List[CheckResult]:
    try:
        return check_cls().run(files)
    except Exception as exc:
        return [
            CheckResult(
                check_id=check_cls.check_id,
                level="error",
                passed=False,
                message=f"check crashed ({exc})",
            )
        ]


def _check_description(check_cls) -> str:
    doc = (check_cls.__doc__ or "").strip().split("\n")[0]
    return doc[:80] if doc else check_cls.check_id


def list_planned_checks(files: list[Path]) -> list[dict]:
    """Return list of checks that will be run for the given file list, with status."""
    from engine.checks import registry

    planned = []
    # dataset-level
    for check_cls in dataset_level_checks():
        planned.append(
            {
                "check_id": check_cls.check_id,
                "description": _check_description(check_cls),
                "file_types": "dataset-level",
                "will_run": True,
            }
        )
    # per-file: group by check, using the same dispatcher as the real run
    # (so compound names like .fq.gz plan exactly what will execute).
    from collections import Counter

    ext_counter = Counter(p.suffix.lower() or "(no ext)" for p in files)
    for check_cls in registry.values():
        if not check_cls.extensions:
            continue
        matching = [p for p in files if check_cls in checks_for_file(p)]
        planned.append(
            {
                "check_id": check_cls.check_id,
                "description": _check_description(check_cls),
                "file_types": ", ".join(sorted(check_cls.extensions)),
                "will_run": len(matching) > 0,
                "matching_files": len(matching),
            }
        )
    return planned


def run_report(
    dataset_dir: Path, persistent_id: str = "", label: str = "", progress_callback=None
) -> DatasetReport:
    """Run all applicable checks on a staged dataset directory."""
    dataset_dir = Path(dataset_dir)
    files = collect_files(dataset_dir)

    def _report_progress(msg: str) -> None:
        if progress_callback:
            try:
                progress_callback(msg)
            except Exception:
                pass

    _report_progress(f"Found {len(files)} file(s), starting {len(dataset_level_checks())} dataset-level check(s)…")
    dataset_checks: List[CheckResult] = []
    for check_cls in dataset_level_checks():
        _report_progress(f"Running {check_cls.check_id} …")
        dataset_checks.extend(_safe_run(check_cls, files))

    _report_progress(f"Running per-file checks on {len(files)} file(s)…")
    entries: List[FileEntry] = []
    unmatched: List[Path] = []
    for idx, path in enumerate(files, 1):
        file_checks: List[CheckResult] = []
        checks = checks_for_file(path)
        if checks:
            _report_progress(f"[{idx}/{len(files)}] {path.name}: {', '.join(c.check_id for c in checks)} …")
        else:
            unmatched.append(path)
        for check_cls in checks:
            file_checks.extend(_safe_run(check_cls, [path]))
        try:
            size = path.stat().st_size
        except OSError:
            continue  # vanished mid-run
        entries.append(
            FileEntry(
                path=path.relative_to(dataset_dir).as_posix(),
                size_bytes=size,
                mime_type=guess_mime(path),
                checks=file_checks,
            )
        )
    if unmatched:
        exts = sorted({p.suffix.lower() or "(no extension)" for p in unmatched})
        dataset_checks.append(
            CheckResult(
                check_id="inventory.unchecked_types",
                level="warning",
                passed=False,
                message=(
                    f"{len(unmatched)} file(s) with no automated check "
                    f"({', '.join(exts)}) — manual review required"
                ),
                details={
                    "extensions": exts,
                    "files": [p.relative_to(dataset_dir).as_posix() for p in unmatched[:10]],
                },
            )
        )

    return DatasetReport(
        persistent_id=persistent_id,
        label=label or dataset_dir.name,
        engine_version=__version__,
        dataset_checks=dataset_checks,
        files=entries,
    )


def run_report_to_file(
    dataset_dir: Path,
    out_path: Path,
    persistent_id: str = "",
    label: str = "",
) -> DatasetReport:
    report = run_report(dataset_dir, persistent_id=persistent_id, label=label)
    report.save(Path(out_path))
    return report