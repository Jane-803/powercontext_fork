"""Traceboard: a small seekdb-backed evidence and progress workspace."""

import json
import os
import re
import subprocess
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
HOST = os.environ.get("APP_HOST", "127.0.0.1")
PORT = int(os.environ.get("APP_PORT", "8088"))
MYSQL = os.environ.get("MYSQL_BIN", "mysql")
DB_HOST = os.environ.get("SEEKDB_HOST", "127.0.0.1")
DB_PORT = os.environ.get("SEEKDB_PORT", "2881")
DB_USER = os.environ.get("SEEKDB_USER", "root")
DB_PASSWORD = os.environ.get("SEEKDB_PASSWORD", "")


def literal(value):
    """Hex literals keep user input out of SQL syntax and client escape rules."""
    return "CONVERT(0x" + str(value).encode("utf-8").hex() + " USING utf8mb4)"


def query(sql):
    env = os.environ.copy()
    env["MYSQL_PWD"] = DB_PASSWORD
    command = [MYSQL, "--host=" + DB_HOST, "--port=" + DB_PORT,
               "--user=" + DB_USER, "--default-character-set=utf8mb4",
               "--batch", "--raw", "--skip-column-names", "traceboard"]
    result = subprocess.run(command, input=sql, text=True, capture_output=True,
                            env=env, timeout=15, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "seekdb query failed")
    return [line.split("\t") for line in result.stdout.splitlines()]


def decoded(value):
    return bytes.fromhex(value or "").decode("utf-8")


def require_text(data, key, maximum):
    value = data.get(key, "")
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{key} must contain 1-{maximum} characters")
    return value.strip()


def valid_date(value):
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError):
        raise ValueError("date must use YYYY-MM-DD") from None


def evidence_rows(project="", search="", kind="", start="", end=""):
    filters = ["1=1"]
    if project:
        filters.append("project=" + literal(project))
    if kind:
        filters.append("kind=" + literal(kind))
    if start:
        filters.append("occurred_on >= " + literal(valid_date(start)))
    if end:
        filters.append("occurred_on <= " + literal(valid_date(end)))
    # MATCH uses seekdb's indexed full-text search; project and date remain SQL filters.
    if search:
        filters.append("MATCH(title, content) AGAINST(" + literal(search) + ")")
    sql = ("SELECT id, HEX(project), HEX(kind), HEX(title), "
           "HEX(content), HEX(source_url), occurred_on "
           "FROM evidence WHERE " + " AND ".join(filters) +
           " ORDER BY occurred_on DESC, id DESC LIMIT 200")
    return [dict(id=int(row[0]), project=decoded(row[1]), kind=decoded(row[2]),
                 title=decoded(row[3]), content=decoded(row[4]),
                 source_url=decoded(row[5]), occurred_on=row[6])
            for row in query(sql)]


def task_rows(project=""):
    condition = " WHERE project=" + literal(project) if project else ""
    sql = ("SELECT id, HEX(project), HEX(title), status, "
           "IFNULL(due_on, ''), IFNULL(evidence_id, 0) FROM tasks" + condition +
           " ORDER BY FIELD(status, 'doing', 'todo', 'done'), id DESC LIMIT 200")
    return [dict(id=int(row[0]), project=decoded(row[1]), title=decoded(row[2]),
                 status=row[3], due_on=row[4], evidence_id=int(row[5]))
            for row in query(sql)]


def create_evidence(data):
    project = require_text(data, "project", 100)
    kind = require_text(data, "kind", 20)
    if kind not in ("note", "meeting", "result", "blocker"):
        raise ValueError("invalid evidence kind")
    title = require_text(data, "title", 200)
    content = require_text(data, "content", 10000)
    source = data.get("source_url", "")
    if not isinstance(source, str) or len(source) > 500:
        raise ValueError("source_url is too long")
    if source and (urlparse(source).scheme not in ("http", "https") or not urlparse(source).netloc):
        raise ValueError("source_url must be an HTTP(S) URL")
    occurred = valid_date(data.get("occurred_on", date.today().isoformat()))
    query("INSERT INTO evidence (project, kind, title, content, source_url, occurred_on) "
          "VALUES (" + ", ".join(map(literal, (project, kind, title, content, source, occurred))) + ");")


def create_task(data):
    project = require_text(data, "project", 100)
    title = require_text(data, "title", 200)
    due = data.get("due_on", "")
    due_sql = literal(valid_date(due)) if due else "NULL"
    query("INSERT INTO tasks (project, title, due_on) VALUES (" +
          literal(project) + ", " + literal(title) + ", " + due_sql + ");")


def update_task(task_id, data):
    if not re.fullmatch(r"[1-9][0-9]*", task_id):
        raise ValueError("invalid task id")
    status = data.get("status")
    if status not in ("todo", "doing", "done"):
        raise ValueError("invalid status")
    evidence_id = data.get("evidence_id")
    if evidence_id is not None and (not isinstance(evidence_id, int) or evidence_id < 1):
        raise ValueError("invalid evidence id")
    linked = str(evidence_id) if evidence_id else "NULL"
    query("UPDATE tasks SET status=" + literal(status) + ", evidence_id=" +
          linked + " WHERE id=" + task_id + ";")


def report(project, start, end):
    if not project:
        raise ValueError("project is required")
    items = evidence_rows(project=project, start=valid_date(start), end=valid_date(end))
    tasks = task_rows(project=project)
    lines = [f"# {project} | {start} - {end}", "", "## 本期证据"]
    for item in items:
        source = f" ([来源]({item['source_url']}))" if item["source_url"] else ""
        lines.append(f"- {item['occurred_on']} [{item['kind']}] {item['title']}{source}: {item['content']}")
    if not items:
        lines.append("- 本期暂无记录")
    lines.extend(["", "## 任务进度"])
    for task in tasks:
        evidence = f"；证据 #{task['evidence_id']}" if task["evidence_id"] else ""
        lines.append(f"- [{task['status']}] {task['title']}{evidence}")
    if not tasks:
        lines.append("- 暂无任务")
    return "\n".join(lines)


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, body):
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        parsed = urlparse(self.path)
        args = {key: values[0] for key, values in parse_qs(parsed.query).items()}
        try:
            if parsed.path == "/api/evidence":
                return self.reply(200, evidence_rows(**{key: args.get(key, "") for key in
                                                       ("project", "search", "kind", "start", "end")}))
            if parsed.path == "/api/tasks":
                return self.reply(200, task_rows(args.get("project", "")))
            if parsed.path == "/api/report":
                return self.reply(200, {"markdown": report(args.get("project", ""),
                                                            args.get("start", ""), args.get("end", ""))})
            if parsed.path == "/api/health":
                query("SELECT 1;")
                return self.reply(200, {"ok": True, "database": "seekdb"})
            path = ROOT / "site" / ("index.html" if parsed.path == "/" else parsed.path.lstrip("/"))
            if not path.resolve().is_relative_to((ROOT / "site").resolve()) or not path.is_file():
                return self.reply(404, {"error": "not found"})
            types = {".html": "text/html", ".css": "text/css", ".js": "text/javascript"}
            data = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", types.get(path.suffix, "application/octet-stream") + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (ValueError, TypeError) as exc:
            self.reply(400, {"error": str(exc)})
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            self.reply(503, {"error": str(exc)})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 20000:
                raise ValueError("invalid request size")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("JSON object required")
            if self.path == "/api/evidence":
                create_evidence(data)
            elif self.path == "/api/tasks":
                create_task(data)
            elif self.path.startswith("/api/tasks/"):
                update_task(self.path.rsplit("/", 1)[-1], data)
            else:
                return self.reply(404, {"error": "not found"})
            self.reply(201, {"ok": True})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.reply(400, {"error": str(exc)})
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            self.reply(503, {"error": str(exc)})


if __name__ == "__main__":
    print(f"Traceboard on http://{HOST}:{PORT}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
