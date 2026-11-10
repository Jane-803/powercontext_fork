from __future__ import annotations

import argparse
import json
from pathlib import Path

from .minimax_agent import run_minimax
from .service import ContextService

DEFAULT_TASK = (
    "Add an optional min_rating filter to filter_places. Reject ratings outside 0..5. "
    "Keep category and max_distance behavior and preserve input order."
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="sdd-context")
    result.add_argument("--root", type=Path, default=Path.cwd())
    commands = result.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest")
    ingest.add_argument("manifest", type=Path)
    context = commands.add_parser("context")
    context.add_argument("--task", default=DEFAULT_TASK)
    context.add_argument("--output", type=Path, default=Path("records/context.json"))
    save = commands.add_parser("save-state")
    save.add_argument("state", type=Path)
    commands.add_parser("load-state")
    agent = commands.add_parser("run-minimax")
    agent.add_argument("--task", default=DEFAULT_TASK)
    agent.add_argument("--context", type=Path, default=Path("records/context.json"))
    agent.add_argument("--output", type=Path, default=Path("records/minimax_run.json"))
    return result


def main() -> None:
    args = parser().parse_args()
    root = args.root.resolve()
    service = ContextService(root)
    if args.command == "ingest":
        print(json.dumps({"ingested": service.ingest((root / args.manifest).resolve()), "database": "seekdb"}))
    elif args.command == "context":
        data = service.write_context(args.task, (root / args.output).resolve())
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif args.command == "save-state":
        state = json.loads((root / args.state).read_text(encoding="utf-8"))
        print(json.dumps(service.state.save(state), ensure_ascii=False, indent=2))
    elif args.command == "load-state":
        print(json.dumps(service.state.load(), ensure_ascii=False, indent=2))
    elif args.command == "run-minimax":
        context = json.loads((root / args.context).read_text(encoding="utf-8"))
        record = run_minimax(args.task, context, (root / args.output).resolve())
        print(json.dumps({key: record[key] for key in ("provider", "model", "request_id", "usage")}, indent=2))


if __name__ == "__main__":
    main()
