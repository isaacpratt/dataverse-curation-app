"""Run report checks over a staged dataset directory.

Dispatches checks and aggregates findings into a DatasetReport
(docs/html/report-contract.html).
"""

import mimetypes
from pathlib import Path

from engine import __version__
from engine.checks.base import CheckResult
from engine.dispatcher import checks_for_file, dataset_level_checks
from engine.report import DatasetReport, FileEntry


def collect_files(dataset_dir: Path) -> list[Path]:
    """List staged files, sorted.

    Symlinks are skipped (a staged symlink could point outside the
    dataset dir) and vanishing paths are ignored.
    """
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


def _safe_run(check_cls, files: list[Path]) -> list[CheckResult]:
    try:
        result: list[CheckResult] = check_cls().run(files)
        return result
    except Exception as exc:
        return [
            CheckResult(
                check_id=check_cls.check_id,
                level="error",
                passed=False,
                message=f"check crashed ({exc})",
            )
        ]


def _safe_run_dataset(
    check_cls, files: list[Path], context: dict
) -> list[CheckResult]:
    """Run a dataset-level check, passing the inventory/metadata context."""
    try:
        result: list[CheckResult] = check_cls().run_dataset(files, context)
        return result
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
    from collections import Counter

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
    # per-file: single pass over files (O(F) dispatcher calls, not O(C*F)).
    counts: Counter = Counter()
    for path in files:
        try:
            for check_cls in checks_for_file(path):
                counts[check_cls.check_id] += 1
        except Exception:
            continue
    for check_cls in registry.values():
        if not check_cls.extensions:
            continue
        matching_n = counts.get(check_cls.check_id, 0)
        planned.append(
            {
                "check_id": check_cls.check_id,
                "description": _check_description(check_cls),
                "file_types": ", ".join(sorted(check_cls.extensions)),
                "will_run": matching_n > 0,
                "matching_files": matching_n,
            }
        )
    return planned


def run_report(
    dataset_dir: Path,
    persistent_id: str = "",
    label: str = "",
    progress_callback=None,
    progress_fraction=None,
    max_workers: int = 1,
    is_cancelled=None,
    inventory: list[dict] | None = None,
    metadata: dict | None = None,
    variable_metadata: dict | None = None,
    ruleset: dict | None = None,
) -> DatasetReport:
    """Run all applicable checks on a staged dataset directory.

    `max_workers>1` parallelizes per-file checks with a ThreadPool (checks
    are per-file isolated via `run_per_file`). `is_cancelled` is an optional
    zero-arg callable polled between files for cooperative cancellation.
    `progress_fraction` is an optional callback receiving (done, total) so
    a UI can show a determinate progress ring. `inventory`/`metadata` are
    passed to dataset-level checks (access restrictions, embargo dates and
    terms of access); without them those checks report as skipped. `ruleset`
    lets a dataset-level check honour per-ruleset settings (the README
    section list); headless runs fall back to the defaults.
    """
    dataset_dir = Path(dataset_dir)
    try:
        dataset_resolved = dataset_dir.resolve()
    except OSError:
        dataset_resolved = dataset_dir
    files = collect_files(dataset_dir)

    def _report_progress(msg: str) -> None:
        if progress_callback:
            try:
                progress_callback(msg)
            except Exception:
                pass

    def _report_fraction(done: int, total: int) -> None:
        if progress_fraction:
            try:
                progress_fraction(done, total)
            except Exception:
                pass

    def _cancelled() -> bool:
        try:
            return bool(is_cancelled and is_cancelled())
        except Exception:
            return False

    dataset_context = {
        "inventory": inventory,
        "metadata": metadata,
        # path -> {variable: {label, type}} for tabular files (dv-tfy);
        # the UI worker fetches it from Dataverse's per-file DDI.
        "variable_metadata": variable_metadata,
        # Per-ruleset settings a dataset-level check may need (README
        # section rules, dv-81q); None means "use the built-in defaults".
        "ruleset": ruleset,
    }
    _report_progress(f"Found {len(files)} file(s), starting {len(dataset_level_checks())} dataset-level check(s)…")
    dataset_checks: list[CheckResult] = []
    for check_cls in dataset_level_checks():
        if _cancelled():
            break
        _report_progress(f"Running {check_cls.check_id} …")
        dataset_checks.extend(_safe_run_dataset(check_cls, files, dataset_context))

    _report_progress(f"Running per-file checks on {len(files)} file(s)…")

    def _run_one_file(args) -> FileEntry | Path | None:
        idx, path = args
        try:
            checks = checks_for_file(path)
        except Exception:
            checks = []
        if checks:
            _report_progress(f"[{idx}/{len(files)}] {path.name}: {', '.join(c.check_id for c in checks)} …")
        file_checks: list[CheckResult] = []
        for check_cls in checks:
            if _cancelled():
                break
            file_checks.extend(_safe_run(check_cls, [path]))
        try:
            size = path.stat().st_size
        except OSError:
            return None  # vanished mid-run
        try:
            rel = path.resolve().relative_to(dataset_resolved).as_posix()
        except ValueError:
            # Symlink-race escape outside dataset_dir: record basename only.
            rel = path.name
        except OSError:
            return None
        return FileEntry(
            path=rel,
            size_bytes=size,
            mime_type=guess_mime(path),
            checks=file_checks,
        )

    entries: list[FileEntry] = []
    unmatched: list[Path] = []
    # Pre-classify unmatched sequentially (cheap) to keep warning stable.
    matched_flags: list[bool] = []
    for path in files:
        try:
            matched_flags.append(bool(checks_for_file(path)))
        except Exception:
            matched_flags.append(False)
    unmatched = [p for p, m in zip(files, matched_flags, strict=True) if not m]

    indexed = list(enumerate(files, 1))
    total_files = len(indexed)
    done_files = 0
    if max_workers and max_workers > 1:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for result in pool.map(_run_one_file, indexed):
                if _cancelled():
                    break
                done_files += 1
                _report_fraction(done_files, total_files)
                if result is None or isinstance(result, Path):
                    continue
                entries.append(result)
        # Restore deterministic sorted order (ThreadPool.map preserves
        # order already, but sort defensively by path).
        entries.sort(key=lambda e: e.path)
    else:
        for idx, path in indexed:
            if _cancelled():
                break
            result = _run_one_file((idx, path))
            done_files += 1
            _report_fraction(done_files, total_files)
            if result is None or isinstance(result, Path):
                continue
            entries.append(result)
    if unmatched:
        exts = sorted({p.suffix.lower() or "(no extension)" for p in unmatched})
        sample: list[str] = []
        for p in unmatched[:10]:
            try:
                sample.append(p.resolve().relative_to(dataset_resolved).as_posix())
            except (ValueError, OSError):
                sample.append(p.name)
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
                    "files": sample,
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
    max_workers: int = 1,
    fmt: str = "json",
    inventory: list[dict] | None = None,
    metadata: dict | None = None,
    variable_metadata: dict | None = None,
    ruleset: dict | None = None,
) -> DatasetReport:
    """Write the report in json, md, or both (sibling extension swap).

    fmt="both" writes out_path as given plus the sibling (.json<->.md).
    """
    report = run_report(
        dataset_dir,
        persistent_id=persistent_id,
        label=label,
        max_workers=max_workers,
        inventory=inventory,
        metadata=metadata,
        variable_metadata=variable_metadata,
        ruleset=ruleset,
    )
    out_path = Path(out_path)
    fmt = (fmt or "json").lower()
    if fmt not in ("json", "md", "markdown", "both"):
        raise ValueError(f"unknown format {fmt!r} (json|md|both)")
    if fmt in ("md", "markdown"):
        if out_path.suffix.lower() != ".md":
            out_path = out_path.with_suffix(".md")
        report.save_markdown(out_path)
    elif fmt == "both":
        json_path = out_path if out_path.suffix.lower() == ".json" else out_path.with_suffix(".json")
        md_path = json_path.with_suffix(".md") if json_path.suffix.lower() == ".json" else out_path.with_suffix(".md")
        # When caller passed .md, mirror: md as given, json sibling.
        if out_path.suffix.lower() == ".md":
            md_path = out_path
            json_path = out_path.with_suffix(".json")
        report.save(json_path)
        report.save_markdown(md_path)
    else:
        report.save(out_path)
    return report
