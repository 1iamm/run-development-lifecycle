from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from comment_bridge import (  # noqa: E402
    bridge_dir,
    inject_bridge_config,
    make_handler,
    pending_payload,
    set_bridge_config,
)


def ledger_source(embedded_threads: list[dict] | None = None) -> str:
    comments = {
        "version": 1,
        "taskId": "DEV-20260821-999",
        "ledgerVersion": "v1.0",
        "threads": embedded_threads or [],
    }
    return (
        '<!doctype html><html data-task-id="DEV-20260821-999" data-ledger-version="v1.0">'
        '<head><script id="ledger-comment-bridge-config">globalThis.__LEDGER_COMMENT_BRIDGE__=null;</script></head>'
        '<body><section id="phase-P1-release">release</section>'
        f'<script id="ledger-comments-data" type="application/json">{json.dumps(comments)}</script>'
        "</body></html>"
    )


def thread(message_id: str, body: str, status: str = "open", updated_at: str = "2026-08-21T10:01:00+08:00") -> dict:
    return {
        "id": "CMT-1",
        "target": {
            "type": "resource",
            "sectionId": "phase-P1-release",
            "resourceId": "phase-P1-release",
            "resourceType": "section",
            "label": "release",
        },
        "severity": "question",
        "status": status,
        "createdAt": "2026-08-21T10:00:00+08:00",
        "updatedAt": updated_at,
        "messages": [{"id": message_id, "author": "user", "createdAt": "2026-08-21T10:00:00+08:00", "body": body}],
        "change": {"status": "none", "ledgerVersion": "v1.0", "summary": ""},
    }


class CommentBridgeTests(unittest.TestCase):
    def test_config_can_be_injected_without_writing_source(self) -> None:
        source = ledger_source()
        rendered = inject_bridge_config(source, {"endpoint": "http://127.0.0.1:1234/api/comments", "token": "secret", "mode": "loopback"})
        self.assertIn("127.0.0.1:1234", rendered)
        self.assertIn("globalThis.__LEDGER_COMMENT_BRIDGE__=null", source)

    def test_config_is_injected_and_restored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "index.html"
            ledger.write_text(ledger_source(), encoding="utf-8")
            set_bridge_config(ledger, {"endpoint": "http://127.0.0.1:1234/api/comments", "token": "secret", "mode": "loopback"})
            self.assertIn("127.0.0.1:1234", ledger.read_text(encoding="utf-8"))
            set_bridge_config(ledger, None)
            source = ledger.read_text(encoding="utf-8")
            self.assertIn("globalThis.__LEDGER_COMMENT_BRIDGE__=null", source)
            self.assertNotIn('"secret"', source)

    def test_pending_payload_filters_embedded_messages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "index.html"
            ledger.write_text(ledger_source([thread("MSG-OLD", "old")]), encoding="utf-8")
            local = {"version": 1, "taskId": "DEV-20260821-999", "ledgerVersion": "v1.0", "threads": [thread("MSG-NEW", "new")]}
            pending = bridge_dir(ledger) / "comments.pending.json"
            pending.write_text(json.dumps(local), encoding="utf-8")
            result = pending_payload(ledger)
            self.assertEqual(1, result["pendingThreadCount"])
            self.assertEqual("MSG-NEW", result["threads"][0]["messages"][0]["id"])

    def test_pending_payload_ignores_older_browser_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "index.html"
            embedded = thread("MSG-OLD", "old", "change-applied", "2026-08-21T14:00:00+08:00")
            ledger.write_text(ledger_source([embedded]), encoding="utf-8")
            local = {
                "version": 1,
                "taskId": "DEV-20260821-999",
                "ledgerVersion": "v1.0",
                "threads": [thread("MSG-OLD", "old", "open", "2026-08-21T10:01:00+08:00")],
            }
            pending = bridge_dir(ledger) / "comments.pending.json"
            pending.write_text(json.dumps(local), encoding="utf-8")
            self.assertEqual(0, pending_payload(ledger)["pendingThreadCount"])

    def test_pending_payload_keeps_newer_browser_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "index.html"
            embedded = thread("MSG-OLD", "old", "change-applied", "2026-08-21T14:00:00+08:00")
            ledger.write_text(ledger_source([embedded]), encoding="utf-8")
            local = {
                "version": 1,
                "taskId": "DEV-20260821-999",
                "ledgerVersion": "v1.0",
                "threads": [thread("MSG-OLD", "old", "resolved", "2026-08-21T15:00:00+08:00")],
            }
            pending = bridge_dir(ledger) / "comments.pending.json"
            pending.write_text(json.dumps(local), encoding="utf-8")
            result = pending_payload(ledger)
            self.assertEqual(1, result["pendingThreadCount"])
            self.assertEqual("resolved", result["threads"][0]["status"])

    def test_loopback_endpoint_requires_token_and_writes_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "index.html"
            ledger.write_text(ledger_source(), encoding="utf-8")
            pending = bridge_dir(ledger) / "comments.pending.json"
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(ledger, "bridge-token", pending))
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            endpoint = f"http://127.0.0.1:{server.server_address[1]}/api/comments"
            payload = json.dumps({"version": 1, "taskId": "DEV-20260821-999", "ledgerVersion": "v1.0", "threads": [thread("MSG-NEW", "new")]}).encode()
            bad = urllib.request.Request(endpoint, data=payload, method="PUT", headers={"Content-Type": "application/json", "Origin": "null", "X-Ledger-Comment-Token": "wrong"})
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(bad)
            self.assertEqual(403, error.exception.code)
            error.exception.close()
            good = urllib.request.Request(endpoint, data=payload, method="PUT", headers={"Content-Type": "application/json", "Origin": "null", "X-Ledger-Comment-Token": "bridge-token"})
            with urllib.request.urlopen(good) as response:
                self.assertEqual(200, response.status)
            self.assertEqual("MSG-NEW", json.loads(pending.read_text(encoding="utf-8"))["threads"][0]["messages"][0]["id"])
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)

    def test_loopback_page_injects_runtime_config_without_mutating_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "index.html"
            original = ledger_source()
            ledger.write_text(original, encoding="utf-8")
            pending = bridge_dir(ledger) / "comments.pending.json"
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(ledger, "bridge-token", pending))
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            with urllib.request.urlopen(f"http://127.0.0.1:{server.server_address[1]}/") as response:
                rendered = response.read().decode()
            self.assertIn('"bridge-token"', rendered)
            self.assertEqual(original, ledger.read_text(encoding="utf-8"))
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
