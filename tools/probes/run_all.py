"""Run every UI probe and report the result.

The probes are the checks pytest cannot see: a pixel at a card's
corner, a column geometry after a drag, the two button sheets
agreeing. Each one exits non-zero when a check fails; this runner runs
them all and exits non-zero when any of them failed, so CI can call a
single command.

    python tools/probes/run_all.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main() -> int:
    probes = sorted(HERE.glob("probe_*.py"))
    if not probes:
        print("no probes found")
        return 1
    failures: list[str] = []
    for probe in probes:
        print(f"\n>>> {probe.name}")
        result = subprocess.run(
            [sys.executable, str(probe)],
            cwd=str(ROOT),
            check=False,
        )
        if result.returncode != 0:
            failures.append(probe.name)
    print("\n=== probe summary ===")
    if failures:
        for name in failures:
            print(f"  FAILED  {name}")
        print(f"{len(failures)} of {len(probes)} probes failed")
        return 1
    print(f"all {len(probes)} probes passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
