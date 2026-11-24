"""Cancellation and headless error visibility (dv-gfk)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _staged(tmp_path: Path, count: int = 30) -> Path:
    ds = tmp_path / "dataset"
    ds.mkdir()
    for i in range(count):
        (ds / f"f{i:02d}.txt").write_text("hello\n", encoding="utf-8")
    return ds


def test_parallel_run_stops_submitting_after_cancel(tmp_path: Path, monkeypatch: Any) -> None:
    import engine.runner as runner

    ds = _staged(tmp_path)
    real_safe_run = runner._safe_run
    calls: list[str] = []

    def _record(check_cls: Any, files: list[Path]) -> list[Any]:
        calls.append(files[0].name)
        return real_safe_run(check_cls, files)

    monkeypatch.setattr(runner, "_safe_run", _record)
    state = {"cancel": False}

    def _fraction(done: int, total: int) -> None:
        if done >= 3:
            state["cancel"] = True

    report = runner.run_report(
        ds,
        max_workers=2,
        is_cancelled=lambda: state["cancel"],
        progress_fraction=_fraction,
    )
    assert report is not None
    assert calls, "no per-file check ran at all"
    assert len(calls) < 30, "cancellation did not stop the remaining submitted files"


def test_run_report_to_file_forwards_cancellation(tmp_path: Path, monkeypatch: Any) -> None:
    import engine.runner as runner

    seen: dict[str, Any] = {}

    def _fake_run(dataset_dir: Path, **kwargs: Any) -> Any:
        seen.update(kwargs)
        from engine.report import DatasetReport

        return DatasetReport("id", "label", "0")

    monkeypatch.setattr(runner, "run_report", _fake_run)

    def sentinel() -> bool:
        return True

    runner.run_report_to_file(tmp_path, tmp_path / "r.json", is_cancelled=sentinel)
    assert seen.get("is_cancelled") is sentinel


def test_headless_verdict_failure_is_reported(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    import engine.verdict as verdict
    from main import main

    ds = _staged(tmp_path, count=2)

    def _boom(report: Any) -> None:
        raise RuntimeError("verdict exploded")

    monkeypatch.setattr(verdict, "assess", _boom)
    code = main(["--headless", str(ds), "--out", str(tmp_path / "report.json")])
    captured = capsys.readouterr()
    assert code == 0
    assert "Verdict unavailable: verdict exploded" in captured.err
    assert json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))["files"]
