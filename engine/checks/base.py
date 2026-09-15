"""Base abstractions for format checks.

Checks are pure functions of local files - no network I/O. Each Check
returns one or more CheckResult objects, aggregated into a DatasetReport by
engine.report. See docs/report-contract.md for the JSON contract.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class CheckResult:
    check_id: str
    level: str
    passed: bool
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "level": self.level,
            "passed": self.passed,
            "message": self.message,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CheckResult":
        return cls(**data)


class Check:
    check_id: str = "base.check"
    extensions: set = frozenset()

    def run(self, files: List[Path]) -> List[CheckResult]:
        raise NotImplementedError