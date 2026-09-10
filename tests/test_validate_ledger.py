from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from validate_ledger import validate  # noqa: E402


DEMO = SKILL_ROOT / "assets" / "ledger-demo.html"


class LedgerValidationTests(unittest.TestCase):
    def validate_source(self, source: str, gate: str, phase: str | None = None) -> list[str]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.html"
            path.write_text(source, encoding="utf-8")
            errors, _ = validate(path, live=False, gate=gate, phase=phase)
            return errors

    def test_canonical_demo_passes_all_gates(self) -> None:
        for gate, phase in (("structure", None), ("requirements", "P1"), ("design", None), ("branch", "P2"), ("done", None)):
            errors, _ = validate(DEMO, live=False, gate=gate, phase=phase)
            self.assertEqual([], errors, f"gate={gate} phase={phase}: {errors}")

    def test_keyword_stuffed_code_architecture_fails(self) -> None:
        source = DEMO.read_text(encoding="utf-8")
        source = re.sub(
            r'(<section class="card" id="phase-P1-code-architecture"[^>]*>).*?(</section>)',
            r'\1<p>仓库 模块 入口 调用链 依赖方向 文件 证据 代码架构关键词。</p>\2',
            source,
            count=1,
            flags=re.S,
        )
        errors = self.validate_source(source, "design", "P1")
        self.assertTrue(any("phase-P1-code-architecture" in error for error in errors), errors)

    def test_missing_impact_category_fails(self) -> None:
        source = DEMO.read_text(encoding="utf-8")
        source = re.sub(r'<tr data-impact-category="security">.*?</tr>', "", source, count=1, flags=re.S)
        errors = self.validate_source(source, "design", "P1")
        self.assertTrue(any("missing categories: security" in error for error in errors), errors)

    def test_empty_data_inventory_fails(self) -> None:
        source = DEMO.read_text(encoding="utf-8")
        source = re.sub(
            r'(<section class="card" id="phase-P2-data-inventory"[^>]*>).*?(</section>)',
            r'\1<p>数据资产清单待补充。</p>\2',
            source,
            count=1,
            flags=re.S,
        )
        errors = self.validate_source(source, "design", "P2")
        self.assertTrue(any("phase-P2-data-inventory" in error for error in errors), errors)

    def test_er_diagram_requires_relationships(self) -> None:
        source = DEMO.read_text(encoding="utf-8")
        source = re.sub(
            r'(<section class="card" id="phase-P1-persistence-model"[^>]*>.*?</section>)',
            lambda match: match.group(1).replace("data-relationship=", "data-removed-relationship="),
            source,
            count=1,
            flags=re.S,
        )
        errors = self.validate_source(source, "design", "P1")
        self.assertTrue(any("ER relationships" in error for error in errors), errors)

    def test_er_entities_must_match_table_inventory(self) -> None:
        source = DEMO.read_text(encoding="utf-8").replace(
            'data-object="operation_audit_log" data-object-kind="table"',
            'data-object="missing_audit_table" data-object-kind="table"',
            1,
        )
        errors = self.validate_source(source, "design", "P1")
        self.assertTrue(any("ER entities missing from data inventory" in error for error in errors), errors)

    def test_data_architecture_requires_specific_diagram_kind(self) -> None:
        source = DEMO.read_text(encoding="utf-8").replace(
            'data-diagram-kind="data-architecture"',
            'data-diagram-kind="generic"',
            1,
        )
        errors = self.validate_source(source, "design", "P1")
        self.assertTrue(any("data-diagram-kind=data-architecture" in error for error in errors), errors)

    def test_child_base_must_equal_parent_candidate(self) -> None:
        source = DEMO.read_text(encoding="utf-8").replace(
            'id="phase-P2-branch" data-artifact="branch" data-status="complete" data-evidence-count="2" data-as-of="2026-08-21"\n    data-branch-name="feat/dev-20260821-001-p2-wechat-pay" data-base-sha="a1b2c3d4"',
            'id="phase-P2-branch" data-artifact="branch" data-status="complete" data-evidence-count="2" data-as-of="2026-08-21"\n    data-branch-name="feat/dev-20260821-001-p2-wechat-pay" data-base-sha="deadbee"',
        )
        errors = self.validate_source(source, "branch", "P2")
        self.assertTrue(any("base SHA must equal parent candidate SHA" in error for error in errors), errors)

    def test_phase_directory_requires_release_link(self) -> None:
        source = DEMO.read_text(encoding="utf-8").replace(
            '<a class="toc-link release-link" href="#phase-P1-release">上线资源</a>',
            "",
            1,
        )
        errors = self.validate_source(source, "structure")
        self.assertTrue(any("toc-phase-P1 missing links: phase-P1-release" in error for error in errors), errors)

    def test_every_global_tab_requires_directory(self) -> None:
        source = DEMO.read_text(encoding="utf-8").replace('id="toc-summary"', 'id="removed-toc-summary"', 1)
        errors = self.validate_source(source, "structure")
        self.assertTrue(any("toc-summary" in error for error in errors), errors)

    def test_comment_drawer_is_required(self) -> None:
        source = DEMO.read_text(encoding="utf-8").replace('id="comments-drawer"', 'id="removed-comments-drawer"', 1)
        errors = self.validate_source(source, "structure")
        self.assertTrue(any("comments-drawer" in error for error in errors), errors)

    def test_comment_bridge_config_is_required(self) -> None:
        source = DEMO.read_text(encoding="utf-8").replace(
            'id="ledger-comment-bridge-config"',
            'id="removed-ledger-comment-bridge-config"',
            1,
        )
        errors = self.validate_source(source, "structure")
        self.assertTrue(any("ledger-comment-bridge-config" in error for error in errors), errors)

    def test_comment_bridge_runtime_is_required(self) -> None:
        source = DEMO.read_text(encoding="utf-8").replace("syncCommentsToBridge", "removedCommentBridgeSync")
        errors = self.validate_source(source, "structure")
        self.assertTrue(any("syncCommentsToBridge" in error for error in errors), errors)

    def test_comment_json_must_be_valid(self) -> None:
        source = DEMO.read_text(encoding="utf-8")
        source = re.sub(
            r'(<script id="ledger-comments-data" type="application/json">).*?(</script>)',
            r'\1{invalid-json}\2',
            source,
            count=1,
            flags=re.S,
        )
        errors = self.validate_source(source, "structure")
        self.assertTrue(any("invalid ledger-comments-data JSON" in error for error in errors), errors)

    def test_open_blocker_comment_blocks_phase_gate(self) -> None:
        source = DEMO.read_text(encoding="utf-8")
        match = re.search(r'(<script id="ledger-comments-data" type="application/json">)(.*?)(</script>)', source, flags=re.S)
        self.assertIsNotNone(match)
        data = json.loads(match.group(2))
        data["threads"].append({
            "id": "CMT-TEST-BLOCKER",
            "target": {"type": "resource", "sectionId": "phase-P1-release", "resourceId": "phase-P1-release", "resourceType": "section", "label": "P1 上线资源"},
            "severity": "blocker",
            "status": "open",
            "createdAt": "2026-08-21T12:00:00+08:00",
            "updatedAt": "2026-08-21T12:00:00+08:00",
            "messages": [{"id": "MSG-TEST-BLOCKER", "author": "user", "createdAt": "2026-08-21T12:00:00+08:00", "body": "上线资源尚未确认"}],
            "change": {"status": "none", "ledgerVersion": "v2.0", "summary": ""},
        })
        replacement = match.group(1) + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + match.group(3)
        source = source[:match.start()] + replacement + source[match.end():]
        errors = self.validate_source(source, "design", "P1")
        self.assertTrue(any("unresolved blocker comment prevents gate=design" in error for error in errors), errors)

    def test_pending_bridge_blocker_blocks_phase_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.html"
            path.write_text(DEMO.read_text(encoding="utf-8"), encoding="utf-8")
            pending = path.parent / ".ledger-comments" / "comments.pending.json"
            pending.parent.mkdir()
            pending.write_text(json.dumps({
                "version": 1,
                "taskId": "DEV-20260821-001",
                "ledgerVersion": "v2.0",
                "threads": [{
                    "id": "CMT-BRIDGE-BLOCKER",
                    "target": {"type": "resource", "sectionId": "phase-P1-release", "resourceId": "phase-P1-release", "resourceType": "section", "label": "P1 上线资源"},
                    "severity": "blocker",
                    "status": "open",
                    "createdAt": "2026-08-21T12:00:00+08:00",
                    "updatedAt": "2026-08-21T12:00:00+08:00",
                    "messages": [{"id": "MSG-BRIDGE-BLOCKER", "author": "user", "createdAt": "2026-08-21T12:00:00+08:00", "body": "桥接评论尚未处理"}],
                    "change": {"status": "none", "ledgerVersion": "v2.0", "summary": ""},
                }],
            }), encoding="utf-8")
            errors, _ = validate(path, live=False, gate="design", phase="P1")
        self.assertTrue(any("unresolved blocker comment prevents gate=design" in error for error in errors), errors)

    def test_comment_target_section_must_exist(self) -> None:
        source = DEMO.read_text(encoding="utf-8").replace('"sectionId":"phase-P2-release"', '"sectionId":"missing-section"', 1)
        errors = self.validate_source(source, "structure")
        self.assertTrue(any("target section missing: missing-section" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
