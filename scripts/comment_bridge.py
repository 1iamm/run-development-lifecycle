#!/usr/bin/env python3
"""Loopback-only bridge that syncs lifecycle-ledger comments to a local JSON file."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


MAX_BODY_BYTES = 2 * 1024 * 1024
BRIDGE_DIR_NAME = ".ledger-comments"
BRIDGE_CONFIG_ID = "ledger-comment-bridge-config"
CONFIG_PATTERN = re.compile(
    rf'(<script\b[^>]*\bid=["\']{BRIDGE_CONFIG_ID}["\'][^>]*>)(.*?)(</script>)',
    flags=re.I | re.S,
)
COMMENTS_PATTERN = re.compile(
    r'(<script\b[^>]*\bid=["\']ledger-comments-data["\'][^>]*>)(.*?)(</script>)',
    flags=re.I | re.S,
)
TASK_PATTERN = re.compile(r'<html\b[^>]*\bdata-task-id=["\']([^"\']+)["\']', flags=re.I)
VERSION_PATTERN = re.compile(r'<html\b[^>]*\bdata-ledger-version=["\']([^"\']+)["\']', flags=re.I)


def iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def timestamp(value: Any) -> float:
    if not isinstance(value, str) or not value:
        return 0.0
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def resolve_ledger(raw: str | Path) -> Path:
    path = Path(raw).expanduser().resolve()
    if path.is_dir():
        path = path / "index.html"
    if not path.is_file():
        raise SystemExit(f"ledger not found: {path}")
    return path


def bridge_dir(ledger: Path) -> Path:
    directory = ledger.parent / BRIDGE_DIR_NAME
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        directory.chmod(0o700)
    except OSError:
        pass
    return directory


def atomic_write(path: Path, text: str, mode: int = 0o600) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    temp_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.chmod(mode)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def ledger_metadata(ledger: Path) -> tuple[str, str, dict[str, Any]]:
    source = ledger.read_text(encoding="utf-8")
    task_match = TASK_PATTERN.search(source)
    version_match = VERSION_PATTERN.search(source)
    comments_match = COMMENTS_PATTERN.search(source)
    if not task_match or not version_match or not comments_match:
        raise ValueError("ledger is missing task/version/comment metadata")
    comments = json.loads(comments_match.group(2))
    if not isinstance(comments, dict) or not isinstance(comments.get("threads", []), list):
        raise ValueError("ledger-comments-data is invalid")
    return task_match.group(1), version_match.group(1), comments


def bridge_config_source(config: dict[str, Any] | None) -> str:
    value = "null" if config is None else json.dumps(config, ensure_ascii=False, separators=(",", ":"))
    return f"globalThis.__LEDGER_COMMENT_BRIDGE__={value};"


def inject_bridge_config(source: str, config: dict[str, Any] | None) -> str:
    content = bridge_config_source(config)
    if CONFIG_PATTERN.search(source):
        return CONFIG_PATTERN.sub(lambda match: match.group(1) + content + match.group(3), source, count=1)
    marker = '<script id="ledger-comments-data"'
    position = source.find(marker)
    if position < 0:
        raise ValueError("ledger-comments-data script not found")
    tag = f'<script id="{BRIDGE_CONFIG_ID}">{content}</script>\n'
    return source[:position] + tag + source[position:]


def set_bridge_config(ledger: Path, config: dict[str, Any] | None) -> None:
    original_mode = ledger.stat().st_mode & 0o777
    source = ledger.read_text(encoding="utf-8")
    updated = inject_bridge_config(source, config)
    if updated != source:
        atomic_write(ledger, updated, original_mode)


def public_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in metadata.items() if key != "token"}


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def read_json(path: Path, fallback: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def validate_comment_state(payload: Any, expected_task_id: str) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError("comment payload version must be 1")
    if payload.get("taskId") != expected_task_id:
        raise ValueError("comment payload taskId mismatch")
    threads = payload.get("threads")
    if not isinstance(threads, list) or len(threads) > 500:
        raise ValueError("comment payload threads must be a list with at most 500 items")
    for thread in threads:
        if not isinstance(thread, dict) or not isinstance(thread.get("id"), str):
            raise ValueError("every comment thread requires a string id")
        if not isinstance(thread.get("target"), dict) or not isinstance(thread.get("messages", []), list):
            raise ValueError("every comment thread requires target and messages")
    return payload


def pending_payload(ledger: Path) -> dict[str, Any]:
    task_id, ledger_version, embedded = ledger_metadata(ledger)
    pending_file = ledger.parent / BRIDGE_DIR_NAME / "comments.pending.json"
    local = read_json(pending_file, {"version": 1, "taskId": task_id, "threads": []})
    local = validate_comment_state(local, task_id)
    embedded_threads = {thread.get("id"): thread for thread in embedded.get("threads", []) if isinstance(thread, dict)}
    embedded_message_ids = {
        message.get("id")
        for thread in embedded_threads.values()
        for message in thread.get("messages", [])
        if isinstance(message, dict) and message.get("id")
    }
    result = []
    for thread in local.get("threads", []):
        authoritative = embedded_threads.get(thread.get("id"))
        new_user_message = any(
            isinstance(message, dict)
            and message.get("author") == "user"
            and message.get("id") not in embedded_message_ids
            for message in thread.get("messages", [])
        )
        state_changed = authoritative is None or (
            thread.get("status") != authoritative.get("status")
            and timestamp(thread.get("updatedAt")) > timestamp(authoritative.get("updatedAt"))
        )
        if new_user_message or state_changed:
            result.append(thread)
    return {
        "protocol": "lifecycle-ledger-comments/v1",
        "action": "reply-and-edit-when-justified",
        "taskId": task_id,
        "ledgerVersion": ledger_version,
        "source": "local-comment-bridge",
        "pendingThreadCount": len(result),
        "threads": result,
    }


def make_handler(ledger: Path, token: str, pending_file: Path):
    task_id, _, _ = ledger_metadata(ledger)

    class Handler(BaseHTTPRequestHandler):
        server_version = "LifecycleCommentBridge/1"

        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def allowed_origin(self) -> str | None:
            origin = self.headers.get("Origin")
            same_origin = f"http://127.0.0.1:{self.server.server_address[1]}"
            return origin if origin in ("null", same_origin) else None

        def common_headers(self, content_type: str) -> None:
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            origin = self.allowed_origin()
            if origin:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")

        def write_json(self, status: int, value: dict[str, Any]) -> None:
            body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.common_headers("application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def authorized(self) -> bool:
            return secrets.compare_digest(self.headers.get("X-Ledger-Comment-Token", ""), token)

        def do_OPTIONS(self) -> None:  # noqa: N802
            if not self.allowed_origin():
                self.write_json(403, {"ok": False, "error": "origin rejected"})
                return
            self.send_response(204)
            self.common_headers("text/plain; charset=utf-8")
            self.send_header("Access-Control-Allow-Methods", "GET, PUT, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Ledger-Comment-Token")
            self.send_header("Access-Control-Max-Age", "600")
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            if self.path in ("/", "/index.html"):
                source = ledger.read_text(encoding="utf-8")
                body = inject_bridge_config(
                    source,
                    {
                        "endpoint": f"http://127.0.0.1:{self.server.server_address[1]}/api/comments",
                        "token": token,
                        "mode": "loopback",
                    },
                ).encode("utf-8")
                self.send_response(200)
                self.common_headers("text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path == "/api/health":
                self.write_json(200, {"ok": True, "taskId": task_id})
                return
            if self.path == "/api/comments" and self.authorized():
                self.write_json(200, read_json(pending_file, {"version": 1, "taskId": task_id, "threads": []}))
                return
            self.write_json(404, {"ok": False, "error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            self.save_comments()

        def do_PUT(self) -> None:  # noqa: N802
            self.save_comments()

        def save_comments(self) -> None:
            if self.path != "/api/comments":
                self.write_json(404, {"ok": False, "error": "not found"})
                return
            if not self.allowed_origin() or not self.authorized():
                self.write_json(403, {"ok": False, "error": "request rejected"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > MAX_BODY_BYTES:
                    raise ValueError("invalid content length")
                payload = validate_comment_state(json.loads(self.rfile.read(length)), task_id)
                atomic_write(pending_file, json.dumps(payload, ensure_ascii=False, separators=(",", ":")), 0o600)
                self.write_json(200, {"ok": True, "syncedAt": iso_now(), "threads": len(payload.get("threads", []))})
            except (ValueError, json.JSONDecodeError) as error:
                self.write_json(400, {"ok": False, "error": str(error)})

    return Handler


def serve(args: argparse.Namespace) -> None:
    ledger = resolve_ledger(args.ledger)
    directory = bridge_dir(ledger)
    metadata_path = directory / "bridge.json"
    pending_file = directory / "comments.pending.json"
    token = os.environ.get("LEDGER_COMMENT_BRIDGE_TOKEN") or secrets.token_urlsafe(32)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(ledger, token, pending_file))
    port = int(server.server_address[1])
    metadata = {
        "pid": os.getpid(),
        "host": "127.0.0.1",
        "port": port,
        "url": f"http://127.0.0.1:{port}/",
        "endpoint": f"http://127.0.0.1:{port}/api/comments",
        "token": token,
        "ledger": str(ledger),
        "startedAt": iso_now(),
    }
    atomic_write(metadata_path, json.dumps(metadata, ensure_ascii=False, separators=(",", ":")), 0o600)

    def terminate(_signum: int, _frame: Any) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        try:
            metadata_path.unlink()
        except FileNotFoundError:
            pass


def start(args: argparse.Namespace) -> None:
    ledger = resolve_ledger(args.ledger)
    directory = bridge_dir(ledger)
    metadata_path = directory / "bridge.json"
    existing = read_json(metadata_path, {})
    if isinstance(existing, dict) and pid_alive(int(existing.get("pid", 0))):
        print(json.dumps({"ok": True, "alreadyRunning": True, **public_metadata(existing)}, ensure_ascii=False))
        return
    try:
        metadata_path.unlink()
    except FileNotFoundError:
        pass
    token = secrets.token_urlsafe(32)
    log_path = directory / "bridge.log"
    environment = os.environ.copy()
    environment["LEDGER_COMMENT_BRIDGE_TOKEN"] = token
    with log_path.open("ab", buffering=0) as log_handle:
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "serve", str(ledger), "--port", str(args.port)],
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=log_handle,
            env=environment,
            start_new_session=True,
        )
    deadline = time.monotonic() + 5
    metadata = None
    while time.monotonic() < deadline:
        candidate = read_json(metadata_path, None)
        if isinstance(candidate, dict) and candidate.get("pid") == process.pid:
            metadata = candidate
            break
        if process.poll() is not None:
            break
        time.sleep(0.05)
    if metadata is None:
        raise SystemExit(f"comment bridge failed to start; see {log_path}")
    print(json.dumps({"ok": True, "alreadyRunning": False, **public_metadata(metadata)}, ensure_ascii=False))


def stop(args: argparse.Namespace) -> None:
    ledger = resolve_ledger(args.ledger)
    metadata_path = bridge_dir(ledger) / "bridge.json"
    metadata = read_json(metadata_path, {})
    pid = int(metadata.get("pid", 0)) if isinstance(metadata, dict) else 0
    if pid_alive(pid):
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + 5
        while pid_alive(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
    try:
        metadata_path.unlink()
    except FileNotFoundError:
        pass
    print(json.dumps({"ok": True, "stoppedPid": pid or None}, ensure_ascii=False))


def status(args: argparse.Namespace) -> None:
    ledger = resolve_ledger(args.ledger)
    metadata = read_json(bridge_dir(ledger) / "bridge.json", {})
    active = isinstance(metadata, dict) and pid_alive(int(metadata.get("pid", 0)))
    print(json.dumps({"ok": True, "active": active, "metadata": public_metadata(metadata) if active else None}, ensure_ascii=False))


def read_pending(args: argparse.Namespace) -> None:
    ledger = resolve_ledger(args.ledger)
    print(json.dumps(pending_payload(ledger), ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, function in (("start", start), ("stop", stop), ("status", status), ("read", read_pending)):
        command = subparsers.add_parser(name)
        command.add_argument("ledger")
        if name == "start":
            command.add_argument("--port", type=int, default=0)
        command.set_defaults(function=function)
    internal = subparsers.add_parser("serve", help=argparse.SUPPRESS)
    internal.add_argument("ledger")
    internal.add_argument("--port", type=int, default=0)
    internal.set_defaults(function=serve)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.function(args)


if __name__ == "__main__":
    main()
