from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = os.environ.copy()
ENV["PYTHONPATH"] = str(ROOT)


def command(*arguments: str) -> dict:
    process = subprocess.run(
        [sys.executable, "-m", "sdd_context.cli", "--root", str(ROOT), *arguments],
        cwd=ROOT,
        env=ENV,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode:
        raise RuntimeError(process.stderr or process.stdout)
    return {"command": " ".join(arguments), "exit_code": process.returncode, "stdout": process.stdout}


initial = command("ingest", "corpus/initial.json")
updated = command("ingest", "corpus/update-v2.json")
state_write = command("save-state", "fixtures/state-in-progress.json")
state_read = command("load-state")
context = command("context", "--output", "records/context.json")
payload = json.loads((ROOT / "records" / "context.json").read_text(encoding="utf-8"))
assert [item["version"] for item in payload["sources"]["spec"]] == [2]
assert payload["sources"]["code"] and payload["sources"]["test"]
assert payload["task_state"]["revision"] >= 1
record = {"initial_ingest": initial, "updated_ingest": updated, "state_write": state_write, "state_read": state_read, "context": context}
with (ROOT / "records" / "context_run.json").open("w", encoding="utf-8", newline="\n") as output:
    output.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"spec_version": 2, "state_revision": payload["task_state"]["revision"], "status": "passed"}, indent=2))
