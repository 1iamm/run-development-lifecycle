from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from lifecycle import (  # noqa: E402
    command_add_phase,
    command_checkpoint,
    command_init,
    command_approve,
    command_resume,
    command_sync_comments,
    effective_render_mode,
    effective_profile,
    load_phases,
    load_task,
    merge_pending_comments,
    render_task,
    resume_snapshot,
    required_artifacts,
    validate_task,
    write_json,
)


class LifecycleV2Tests(unittest.TestCase):
    def create_task(self, directory: str, profile: str = "STANDARD") -> Path:
        args = argparse.Namespace(
            title="Fast lifecycle test",
            root=directory,
            task_id="DEV-20260828-999",
            slug="fast-lifecycle-test",
            phase_name="首期交付",
            profile=profile,
        )
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, command_init(args))
        return Path(directory) / "DEV-20260828-999-fast-lifecycle-test"

    def complete_requirements(self, task_dir: Path) -> dict:
        task = load_task(task_dir)
        phase = load_phases(task_dir, task)["P1"]
        phase["scope"].update({
            "currentBehavior": "Existing endpoint returns the current state from the service.",
            "goals": ["Add the approved behavior"],
            "nonGoals": ["No deployment in this test"],
            "evidence": ["src/example.py:10"],
            "blockingDecisions": [],
        })
        phase["requirements"] = [{
            "id": "P1-REQ-001",
            "statement": "Expose the approved behavior",
            "acceptance": ["The endpoint returns the expected result"],
            "status": "ready",
            "evidence": ["requirement note"],
        }]
        entry = task["phases"][0]
        write_json(task_dir / entry["file"], phase)
        return phase

    def complete_design(self, task_dir: Path) -> None:
        task = load_task(task_dir)
        phases = load_phases(task_dir, task)
        phase = phases["P1"]
        for key in required_artifacts(effective_profile(task, phases), phase):
            phase["artifacts"][key] = {
                "status": "complete",
                "summary": f"Completed {key}",
                "evidence": [f"evidence/{key}.txt"],
                "details": [],
            }
        phase["tests"] = [{"id": "P1-TC-001", "expected": "Expected result", "status": "PLANNED", "evidence": []}]
        write_json(task_dir / task["phases"][0]["file"], phase)

    def test_init_creates_compact_structured_task_and_render(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            task_dir = self.create_task(directory)
            self.assertTrue((task_dir / "task.json").is_file())
            self.assertTrue((task_dir / "phases" / "P1.json").is_file())
            self.assertTrue((task_dir / "events.jsonl").is_file())
            html = (task_dir / "index.html").read_text(encoding="utf-8")
            self.assertIn('data-schema-version="2"', html)
            self.assertIn('id="ledger-data"', html)
            self.assertNotIn("__LEDGER_DATA__", html)
            errors, _ = validate_task(task_dir, "structure")
            self.assertEqual([], errors)

    def test_init_rejects_existing_v2_task_as_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            task_dir = self.create_task(directory)
            args = argparse.Namespace(
                title="A separate new requirement",
                root=str(task_dir),
                task_id="DEV-20260828-998",
                slug="separate-requirement",
                phase_name="首期交付",
                profile="STANDARD",
            )
            with self.assertRaisesRegex(ValueError, "parent task root"):
                command_init(args)
            self.assertFalse((task_dir / "DEV-20260828-998-separate-requirement").exists())

    def test_init_rejects_legacy_v1_task_as_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            task_dir = Path(directory) / "DEV-20260827-001-legacy"
            task_dir.mkdir()
            original_html = "<html>legacy ledger</html>"
            (task_dir / "index.html").write_text(original_html, encoding="utf-8")
            args = argparse.Namespace(
                title="A separate new requirement",
                root=str(task_dir),
                task_id="DEV-20260828-997",
                slug="separate-requirement",
                phase_name="首期交付",
                profile="STANDARD",
            )
            with self.assertRaisesRegex(ValueError, "parent task root"):
                command_init(args)
            self.assertEqual(original_html, (task_dir / "index.html").read_text(encoding="utf-8"))

    def test_render_escapes_title_in_static_html(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            args = argparse.Namespace(
                title="Unsafe </title><script>alert(1)</script>",
                root=directory,
                task_id="DEV-20260828-996",
                slug="safe-title",
                phase_name="P1",
                profile="STANDARD",
            )
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, command_init(args))
            html = (Path(directory) / "DEV-20260828-996-safe-title" / "index.html").read_text(encoding="utf-8")
            self.assertIn("Unsafe &lt;/title&gt;&lt;script&gt;alert(1)&lt;/script&gt;", html)
            self.assertNotIn("<title>Unsafe </title><script>", html)

    def test_requirements_and_design_use_structured_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            task_dir = self.create_task(directory)
            errors, _ = validate_task(task_dir, "requirements", "P1")
            self.assertTrue(errors)
            self.complete_requirements(task_dir)
            errors, _ = validate_task(task_dir, "requirements", "P1")
            self.assertEqual([], errors)
            self.complete_design(task_dir)
            errors, _ = validate_task(task_dir, "design", "P1")
            self.assertEqual([], errors)

    def test_risk_signal_promotes_task_to_strict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            task_dir = self.create_task(directory, "FAST")
            task = load_task(task_dir)
            phase = load_phases(task_dir, task)["P1"]
            self.assertEqual("FAST", effective_profile(task, {"P1": phase}))
            phase["applicability"]["schemaChange"] = True
            self.assertEqual("STRICT", effective_profile(task, {"P1": phase}))

    def test_add_phase_promotes_task_to_strict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            task_dir = self.create_task(directory)
            args = argparse.Namespace(task_dir=str(task_dir), name="第二阶段", phase_id=None, parent=None)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, command_add_phase(args))
            task = load_task(task_dir)
            phases = load_phases(task_dir, task)
            self.assertEqual("P2", task["activePhase"])
            self.assertEqual("STRICT", effective_profile(task, phases))

    def test_render_mode_is_independent_and_grows_with_complexity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            task_dir = self.create_task(directory, "STRICT")
            task = load_task(task_dir)
            phases = load_phases(task_dir, task)
            self.assertEqual("COMPACT", effective_render_mode(task, phases)["effective"])
            args = argparse.Namespace(task_dir=str(task_dir), name="第二阶段", phase_id=None, parent=None)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, command_add_phase(args))
            task = load_task(task_dir)
            phases = load_phases(task_dir, task)
            render = effective_render_mode(task, phases)
            self.assertEqual("DEEP", render["effective"])
            self.assertIn("multi-phase", render["reasons"])

    def test_resume_prefers_first_unfinished_phase_and_returns_decision_pack(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            task_dir = self.create_task(directory)
            args = argparse.Namespace(task_dir=str(task_dir), name="第二阶段", phase_id=None, parent=None)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, command_add_phase(args))
            snapshot = resume_snapshot(task_dir)
            self.assertEqual("P2", snapshot["activePhase"])
            self.assertEqual("P1", snapshot["recommendedPhase"])
            self.assertEqual("requirements", snapshot["firstBlockingGate"])
            self.assertTrue(snapshot["nextAction"])
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(0, command_resume(argparse.Namespace(task_dir=str(task_dir))))
            self.assertEqual("P1", json.loads(output.getvalue())["recommendedPhase"])

    def test_strict_task_rejects_combined_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            task_dir = self.create_task(directory, "STRICT")
            args = argparse.Namespace(task_dir=str(task_dir), phase="P1", gate="combined", by="user", note=None)
            with self.assertRaisesRegex(ValueError, "separate requirements and design"):
                command_approve(args)

    def test_checkpoint_records_failed_gate_and_regenerates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            task_dir = self.create_task(directory)
            args = argparse.Namespace(task_dir=str(task_dir), gate="requirements", phase="P1")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(1, command_checkpoint(args))
            result = json.loads(output.getvalue())
            self.assertFalse(result["ok"])
            events = (task_dir / "events.jsonl").read_text(encoding="utf-8")
            self.assertIn('"result":"FAIL"', events)
            self.assertTrue((task_dir / "index.html").is_file())
            self.assertEqual("FAIL", resume_snapshot(task_dir)["gateFailures"][0]["result"])

    def test_pending_comments_merge_into_durable_comments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            task_dir = self.create_task(directory)
            task = load_task(task_dir)
            pending = task_dir / ".ledger-comments" / "comments.pending.json"
            pending.parent.mkdir()
            pending.write_text(json.dumps({
                "version": 1,
                "taskId": task["taskId"],
                "ledgerVersion": "v2.1",
                "threads": [{
                    "id": "CMT-1",
                    "target": {"sectionId": "phase-P1-requirements"},
                    "severity": "question",
                    "status": "open",
                    "createdAt": "2026-08-28T10:00:00+08:00",
                    "updatedAt": "2026-08-28T10:00:00+08:00",
                    "messages": [{"id": "MSG-1", "author": "user", "createdAt": "2026-08-28T10:00:00+08:00", "body": "Question"}],
                }],
            }), encoding="utf-8")
            self.assertEqual(1, merge_pending_comments(task_dir, task))
            comments = json.loads((task_dir / "comments.json").read_text(encoding="utf-8"))
            self.assertEqual("CMT-1", comments["threads"][0]["id"])
            render_task(task_dir)
            self.assertIn("CMT-1", (task_dir / "index.html").read_text(encoding="utf-8"))

    def test_sync_comments_does_not_create_gate_event(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            task_dir = self.create_task(directory)
            task = load_task(task_dir)
            pending = task_dir / ".ledger-comments" / "comments.pending.json"
            pending.parent.mkdir()
            pending.write_text(json.dumps({
                "version": 1,
                "taskId": task["taskId"],
                "ledgerVersion": "v2.1",
                "threads": [{
                    "id": "CMT-SYNC-1",
                    "target": {"sectionId": "phase-P1-requirements"},
                    "severity": "suggestion",
                    "status": "open",
                    "createdAt": "2026-08-28T10:00:00+08:00",
                    "updatedAt": "2026-08-28T10:00:00+08:00",
                    "messages": [{"id": "MSG-1", "author": "user", "createdAt": "2026-08-28T10:00:00+08:00", "body": "Suggestion"}],
                }],
            }), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(0, command_sync_comments(argparse.Namespace(task_dir=str(task_dir))))
            result = json.loads(output.getvalue())
            self.assertEqual(1, result["merge"]["added"])
            events = (task_dir / "events.jsonl").read_text(encoding="utf-8")
            self.assertIn('"type":"comments-synced"', events)
            self.assertNotIn('"type":"gate-check"', events)

    def test_render_contains_adaptive_navigation_and_complete_print_hook(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            task_dir = self.create_task(directory)
            html = (task_dir / "index.html").read_text(encoding="utf-8")
            self.assertIn('"effective":"COMPACT"', html)
            self.assertIn("revealHashTarget", html)
            self.assertIn("querySelectorAll('details.group').forEach", html)
            self.assertIn("跨阶段集成", html)


if __name__ == "__main__":
    unittest.main()
