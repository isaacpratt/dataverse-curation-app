"""Frozen-build smoke probe for the shipped PyInstaller folder.

Port of the two-step smoke recipe that lived in the Makefile:
(1) report the exe size and that `--headless --help` exits 0, and
(2) run the frozen app against a tiny CSV with an email probe and fail
    if any check reports "inspection failed" (this is the regression that
    showed up when a rebuild was made without the SECRET_HIDDENS
    --hidden-import/--collect-all flags, surfacing as
    "cannot import name 'vnr' from 'stdnum.at'").

Exit 0 on success. Set DOCENT_SMOKE_EXE to inspect a different exe
(default: dist/DataverseDocent/DataverseDocent.exe).
"""

import json
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXE = pathlib.Path(os.environ.get(
    "DOCENT_SMOKE_EXE", ROOT / "dist" / "DataverseDocent" / "DataverseDocent.exe"
))


def main() -> int:
    if not EXE.exists():
        print(f"app exe missing - run `poe build` first ({EXE})")
        return 1
    print(f"exe {EXE.stat().st_size} bytes")

    r = subprocess.run([sys.executable, "main.py", "--headless", "--help"], cwd=ROOT)
    if r.returncode != 0:
        print(f"headless --help exited {r.returncode}")
        return r.returncode

    workdir = pathlib.Path(tempfile.mkdtemp(prefix="docent-smoke-"))
    (workdir / "CA-TP4_HH_201601010000_201701010000.csv").write_text(
        "t,v\n2016-01-01 00:00,-5.1\n2016-01-01 01:00,jane@example.com\n",
        encoding="utf-8",
    )
    out = workdir / "report.json"
    r = subprocess.run([str(EXE), "--headless", str(workdir), "--out", str(out)])
    if r.returncode != 0:
        print(f"frozen app exited {r.returncode}")
        return r.returncode

    report = json.loads(out.read_text(encoding="utf-8"))
    msgs = [
        c.get("message", "")
        for f in report.get("files", [])
        for c in f.get("checks", [])
    ]
    bad = [m for m in msgs if "inspection failed" in m]
    print(f"frozen csv checks: {len(msgs)} | inspection failures: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
