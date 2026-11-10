from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(label: str, source: Path) -> dict:
    environment = os.environ.copy()
    environment["CATALOG_SOURCE"] = str(source.relative_to(ROOT))
    process = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_catalog.py", "-q"],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    return {"label": label, "command": f"CATALOG_SOURCE={source.relative_to(ROOT)} python -m pytest tests/test_catalog.py -q", "exit_code": process.returncode, "stdout": process.stdout, "stderr": process.stderr}


before = run("before", ROOT / "snapshots" / "before")
after = run("after", ROOT / "sample_app")
record = {"before": before, "after": after, "expected": {"before_nonzero": True, "after_zero": True}}
(ROOT / "records").mkdir(exist_ok=True)
with (ROOT / "records" / "test_run.json").open("w", encoding="utf-8", newline="\n") as output:
    output.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"before_exit": before["exit_code"], "after_exit": after["exit_code"]}, indent=2))
if before["exit_code"] == 0 or after["exit_code"] != 0:
    raise SystemExit("Expected the target suite to fail before and pass after")
