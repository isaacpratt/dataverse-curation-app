"""Base abstractions for format checks.

Checks are pure functions of local files - no network I/O. Each Check
returns one or more CheckResult objects, aggregated into a DatasetReport by
engine.report. See docs/report-contract.md for the JSON contract.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CheckResult:
    check_id: str
    level: str
    passed: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "level": self.level,
            "passed": self.passed,
            "message": self.message,
            "details": self.details,
        }

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
        )


class Check:
    check_id: str = "base.check"
    extensions: set = frozenset()

    def run(self, files: list[Path]) -> list[CheckResult]:
        raise NotImplementedError