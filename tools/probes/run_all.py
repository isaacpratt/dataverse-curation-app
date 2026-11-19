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

WARNING_PREFIX = "UNEXPECTED Qt message:"


def main() -> int:
    probes = sorted(HERE.glob("probe_*.py"))
    if not probes:
        print("no probes found")
        return 1
    failures: list[str] = []
    warnings: dict[str, list[str]] = {}
    for probe in probes:
        print(f"\n>>> {probe.name}")
        result = subprocess.run(
            [sys.executable, str(probe)],
            cwd=str(ROOT),
            check=False,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        # The probe's own output streams; only the warning lines are held back
        # so they can be repeated in the summary.
        if result.stderr:
            sys.stderr.write(result.stderr)
        found = [
            line[len(WARNING_PREFIX) :].strip()
            for line in (result.stderr or "").splitlines()
            if line.startswith(WARNING_PREFIX)
        ]
        if found:
            warnings[probe.name] = found
        if result.returncode != 0:
            failures.append(probe.name)
    print("\n=== probe summary ===")
    if warnings:
        for name, messages in warnings.items():
            print(f"  WARNING {name}")
            for message in messages:
                print(f"          {message}")
    if failures:
        for name in failures:
            print(f"  FAILED  {name}")
        print(f"{len(failures)} of {len(probes)} probes failed")
        return 1
    print(f"all {len(probes)} probes passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
