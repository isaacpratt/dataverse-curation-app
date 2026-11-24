"""Base abstractions for format checks.

Checks are pure functions of local files - no network I/O. Each Check
returns one or more CheckResult objects, aggregated into a DatasetReport by
engine.report. See docs/reference/report-contract.md for the JSON contract.
"""

from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar


@dataclass
class CheckResult:
    check_id: str
    level: str
    passed: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    # Optional bespoke guidance (dv-lfn): checks may carry their own
    # "why it matters / how to fix" text; otherwise the shared registry
    # in engine.checks.guidance supplies it at render time.
    rationale: str = ""
    remediation: str = ""

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "check_id": self.check_id,
            "level": self.level,
            "passed": self.passed,
            "message": self.message,
            "details": self.details,
        }
        if self.rationale:
            out["rationale"] = self.rationale
        if self.remediation:
            out["remediation"] = self.remediation
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CheckResult":
        """Strict parse: raises ValueError on corrupt/foreign payloads."""
        if not isinstance(data, dict):
            raise ValueError(f"CheckResult must be an object, got {type(data).__name__}")
        try:
            check_id = str(data["check_id"])
            level = str(data["level"])
            passed = bool(data["passed"])
            message = str(data["message"])
        except KeyError as exc:
            raise ValueError(f"CheckResult missing required field {exc}") from exc
        details = data.get("details", {})
        if not isinstance(details, dict):
            raise ValueError("CheckResult.details must be an object")
        return cls(
            check_id=check_id,
            level=level,
            passed=passed,
            message=message,
            details=details,
            rationale=str(data.get("rationale", "") or ""),
            remediation=str(data.get("remediation", "") or ""),
        )


class Check:
    check_id: str = "base.check"
    # Checks declare a literal set; the base default is the empty frozenset,
    # so the annotation must admit both (AbstractSet, not `set`). All checks
    # are class-level (ClassVar) — instances carry no extension state.
    #
    # ``extensions`` answers *which files a check reads*. ``scope`` answers
    # *what its findings are about*: "dataset" (the dataset or its inventory
    # as a whole — reported once under ``dataset_checks``) or "file" (one
    # file's contents — reported in that file's ``checks``). The two are
    # independent: a cross-file check can read .csv and still be
    # dataset-scoped. There is deliberately no default here — the registry
    # refuses a check that does not declare one (dv-p1d), so a new check
    # cannot inherit an accidental answer.
    extensions: ClassVar[AbstractSet[str]] = frozenset()
    scope: ClassVar[str]

    def run(self, files: list[Path]) -> list[CheckResult]:
        raise NotImplementedError

    def run_dataset(
        self, files: list[Path], context: dict[str, Any] | None = None
    ) -> list[CheckResult]:
        """Dataset-level entry point.

        ``context`` carries optional dataset metadata the runner knows
        (currently ``inventory`` and ``metadata``). Checks that only need
        the file list inherit this default and ignore it.
        """
        return self.run(files)
