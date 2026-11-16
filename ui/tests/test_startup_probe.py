"""Startup probe: opt-in, append-only, silent and harmless when disabled."""

from __future__ import annotations


def test_disabled_is_a_noop(tmp_path, monkeypatch):
    monkeypatch.delenv("DOCENT_STARTUP_LOG", raising=False)
    import startup_probe

    target = tmp_path / "startup.log"
    assert not startup_probe.enabled()
    startup_probe.mark("ignored")
    assert not target.exists()


def test_enabled_writes_one_row_per_mark(tmp_path, monkeypatch):
    log = tmp_path / "startup.log"
    monkeypatch.setenv("DOCENT_STARTUP_LOG", str(log))
    import startup_probe

    monkeypatch.setattr(startup_probe, "_HEADER_WRITTEN", False)
    assert startup_probe.enabled()
    startup_probe.mark("first")
    startup_probe.mark("second")

    lines = log.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "# Dataverse Docent startup timing"
    assert lines[1].startswith("# run: ")
    assert lines[2] == "# total_ms\tmodule_ms\tphase"
    rows = [line.split("\t") for line in lines[3:]]
    assert [row[2] for row in rows] == ["first", "second"]
    for total, module_ms, _phase in rows:
        assert total == "-" or total.isdigit(), total
        assert module_ms.isdigit(), module_ms


def test_label_tabs_are_sanitized(tmp_path, monkeypatch):
    log = tmp_path / "startup.log"
    monkeypatch.setenv("DOCENT_STARTUP_LOG", str(log))
    import startup_probe

    monkeypatch.setattr(startup_probe, "_HEADER_WRITTEN", False)
    startup_probe.mark("bad\tphase")

    row = next(line for line in log.read_text(encoding="utf-8").splitlines() if "bad" in line)
    assert len(row.split("\t")) == 3
    assert row.endswith("bad phase")
