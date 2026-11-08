"""One-click curation record export (dv-vwt) — the "Document" step.

Assembles everything a review produced into one dated folder beside the
dataset's workspace folder:

    curation-record/<YYYYMMDD-HHMM>/
      index.json               binds the artifacts + their sha256
      checks_report.json/.md   the engine report (when a report exists)
      depositor_response.md    the response draft text (when non-empty)
      curation_log.md          the append-only action timeline
      dispositions.json        per-finding curator decisions + notes
      sensitivity.json         the sensitivity questionnaire
      decision.json            recorded decision + curation label
      sha256sums.txt           manifest of the staged files

No Qt: pure composition over storage/report helpers, reusable headless.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DISPOSITION_LABELS = {
    "acknowledged": "Acknowledged",
    "fix-requested": "Fix requested",
    "wontfix": "Won't fix",
    "blocked": "Blocked",
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)
        handle.flush()


def _write_text(path: Path, text: str) -> None:
    _write_bytes(path, text.encode("utf-8"))


def _log_markdown(actions: list[dict[str, Any]]) -> str:
    """The curation timeline as readable Markdown (newest first)."""
    lines = ["# Curation log", ""]
    if not actions:
        lines.append("(no recorded actions)")
    for a in actions:
        ts = str(a.get("timestamp") or "")[:19].replace("T", " ")
        actor = str(a.get("actor") or "curator")
        action = str(a.get("action") or "")
        notes = str(a.get("notes") or "").replace("\n", " ")
        line = f"- {ts} [{actor}] {action}"
        if notes:
            line += f" — {notes}"
        lines.append(line)
    return "\n".join(lines) + "\n"


def _dispositions_markdown(dispositions: dict[str, Any]) -> str:
    lines = ["# Finding dispositions", ""]
    if not dispositions:
        lines.append("(no dispositions recorded)")
    for key, entry in dispositions.items():
        token = str(entry.get("disposition") or "")
        label = _DISPOSITION_LABELS.get(token, token or "unset")
        note = str(entry.get("note") or "").replace("\n", " ")
        when = str(entry.get("updated_at") or "")[:19].replace("T", " ")
        line = f"- {key[:12]}… {label}"
        if when:
            line += f" ({when})"
        if note:
            line += f" — {note}"
        lines.append(line)
    return "\n".join(lines) + "\n"


def export_record(dataset_dir: Path,
                  report: Any = None,
                  response_text: str = "",
                  actions: list[dict[str, Any]] | None = None,
                  dispositions: dict[str, Any] | None = None,
                  sensitivity: dict[str, Any] | None = None,
                  decision: str = "",
                  curation_label: str = "",
                  staged_dir: Path | None = None) -> Path:
    """Write one dated curation-record folder; return its path.

    Every input is optional: the record contains whatever the review
    produced so far, so a partial review still exports. Raises on
    hard I/O errors (the caller reports them).
    """
    dataset_dir = Path(dataset_dir)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    record_dir = dataset_dir / "curation-record" / stamp
    if record_dir.exists():
        # Same-second re-run: never clobber — take the next free suffix.
        for n in range(2, 100):
            candidate = dataset_dir / "curation-record" / f"{stamp}-{n}"
            if not candidate.exists():
                record_dir = candidate
                break
    record_dir.mkdir(parents=True, exist_ok=True)

    index: dict[str, Any] = {
        "persistent_id": str(getattr(report, "persistent_id", "") or ""),
        "label": str(getattr(report, "label", "") or ""),
        "engine_version": str(getattr(report, "engine_version", "") or ""),
        "exported_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds"),
        "curation_label": curation_label,
        "decision": decision,
        "artifacts": {},
    }

    if report is not None:
        try:
            report.save(record_dir / "checks_report.json")
            report.save_markdown(record_dir / "checks_report.md")
            index["artifacts"]["checks_report.json"] = True
            index["artifacts"]["checks_report.md"] = True
        except Exception:
            pass

    if str(response_text or "").strip():
        _write_text(record_dir / "depositor_response.md", response_text)
        index["artifacts"]["depositor_response.md"] = True

    _write_text(record_dir / "curation_log.md", _log_markdown(list(actions or [])))
    index["artifacts"]["curation_log.md"] = True

    disp = dict(dispositions or {})
    _write_text(record_dir / "dispositions.json",
                json.dumps(disp, indent=2, ensure_ascii=False))
    index["artifacts"]["dispositions.json"] = True
    index["disposition_count"] = len(disp)

    sens = dict(sensitivity or {})
    _write_text(record_dir / "sensitivity.json",
                json.dumps(sens, indent=2, ensure_ascii=False))
    index["artifacts"]["sensitivity.json"] = True
    if isinstance(sens.get("answers"), dict):
        index["sensitivity_answered"] = sum(
            1 for v in sens["answers"].values() if str(v or "") in ("yes", "no")
        )

    if decision or curation_label:
        _write_text(record_dir / "decision.json",
                    json.dumps({"decision": decision, "curation_label": curation_label},
                               indent=2, ensure_ascii=False))
        index["artifacts"]["decision.json"] = True

    # Fixity: a sha256 manifest of the staged files, plus per-artifact
    # hashes in the index so the record binds itself.
    staged = Path(staged_dir) if staged_dir is not None else None
    manifest_lines: list[str] = []
    if staged is not None and staged.exists():
        for path in sorted(p for p in staged.rglob("*") if p.is_file() and not p.is_symlink()):
            rel = path.relative_to(staged).as_posix()
            manifest_lines.append(f"{_sha256_file(path)}  {rel}")
    _write_text(record_dir / "sha256sums.txt", "\n".join(manifest_lines) + "\n")
    index["artifacts"]["sha256sums.txt"] = True
    index["staged_files"] = len(manifest_lines)

    for artifact in sorted(record_dir.iterdir()):
        if artifact.is_file() and artifact.name != "index.json":
            index["artifacts"][artifact.name] = _sha256_file(artifact)
    _write_text(record_dir / "index.json",
                json.dumps(index, indent=2, ensure_ascii=False))
    return record_dir
