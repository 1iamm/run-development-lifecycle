#!/usr/bin/env python3
"""Validate a phase-aware lifecycle ledger and its semantic gate artifacts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path


GLOBAL_REQUIRED_IDS = {
    "panel-overview",
    "panel-integration",
    "panel-summary",
    "toc-overview",
    "toc-integration",
    "toc-summary",
    "overview-status",
    "overview-phase-map",
    "overview-branch-lineage",
    "overview-blockers",
    "overview-commands",
    "overview-links",
    "integration-dependencies",
    "integration-branches",
    "integration-resources",
    "integration-release",
    "integration-validation",
    "summary-outcome",
    "summary-risks",
    "summary-audit",
    "summary-continue",
    "toggle-all",
    "print-button",
    "comment-mode-button",
    "comments-button",
    "comments-count",
    "comment-selection-action",
    "comments-drawer",
    "comments-close",
    "comments-filter",
    "comments-list",
    "comments-copy",
    "comments-export",
    "comment-composer",
    "comment-target-preview",
    "comment-severity",
    "comment-textarea",
    "comment-save",
    "comment-cancel",
    "ledger-comments-data",
    "ledger-comment-bridge-config",
}

GLOBAL_TOC_TARGETS = {
    "toc-overview": {
        "overview-status",
        "overview-phase-map",
        "overview-branch-lineage",
        "overview-blockers",
        "overview-commands",
        "overview-links",
    },
    "toc-integration": {
        "integration-dependencies",
        "integration-branches",
        "integration-resources",
        "integration-release",
        "integration-validation",
    },
    "toc-summary": {
        "summary-outcome",
        "summary-risks",
        "summary-audit",
        "summary-continue",
    },
}

PHASE_REQUIRED_SUFFIXES = (
    "context",
    "requirements",
    "functional-breakdown",
    "architecture",
    "code-architecture",
    "ui",
    "data-architecture",
    "domain-model",
    "persistence-model",
    "data-inventory",
    "state-machine",
    "sequence-main",
    "sequence-recovery",
    "impact",
    "branch",
    "release",
    "validation",
    "traceability",
)

IMPACT_CATEGORIES = {
    "ui",
    "frontend",
    "backend",
    "api",
    "data",
    "async",
    "config",
    "auth",
    "upstream",
    "downstream",
    "observability",
    "capacity",
    "release",
    "security",
}

LIVE_FORBIDDEN_MARKERS = (
    "这是信息架构与视觉样式 Demo",
    "DEMO ONLY",
    "BT-DEMO",
    "TL-DEMO",
    "demo-934",
    "develop@8be32f1",
    "develop@7a20c4d",
)

VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}


@dataclass
class ElementStats:
    attrs: dict[str, str] = field(default_factory=dict)
    text_parts: list[str] = field(default_factory=list)
    tags: Counter[str] = field(default_factory=Counter)
    rows: int = 0
    diagrams: int = 0
    diagram_kinds: set[str] = field(default_factory=set)
    entities: set[str] = field(default_factory=set)
    relationships: set[str] = field(default_factory=set)
    data_objects: set[str] = field(default_factory=set)
    table_objects: set[str] = field(default_factory=set)
    link_targets: set[str] = field(default_factory=set)
    impact_categories: set[str] = field(default_factory=set)

    @property
    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.text_parts)).strip()


@dataclass(frozen=True)
class ArtifactRule:
    suffix: str
    min_chars: int
    terms: tuple[str, ...]
    min_rows: int = 0
    min_diagrams: int = 0
    diagram_kind: str | None = None
    min_entities: int = 0
    min_relationships: int = 0


DESIGN_RULES = (
    ArtifactRule("functional-breakdown", 320, ("角色", "生命周期", "入口", "触发", "操作", "可见", "人工", "自动", "异常", "REQ"), min_rows=4, min_diagrams=1),
    ArtifactRule("architecture", 160, ("职责", "边界", "依赖", "证据"), min_diagrams=1),
    ArtifactRule("code-architecture", 220, ("仓库", "模块", "入口", "调用链", "依赖方向", "文件", "证据"), min_rows=2, min_diagrams=1),
    ArtifactRule("data-architecture", 240, ("主数据源", "写链路", "读链路", "恢复链路", "事务", "异步边界", "写入方", "查询方", "证据"), min_diagrams=1, diagram_kind="data-architecture"),
    ArtifactRule("domain-model", 160, ("聚合", "实体", "规则", "不变量", "所有权", "证据"), min_diagrams=1),
    ArtifactRule("persistence-model", 240, ("ER 图", "主键", "唯一", "索引", "关系", "基数", "逻辑引用", "物理外键", "写入方", "证据"), min_diagrams=1, diagram_kind="erd", min_entities=3, min_relationships=2),
    ArtifactRule("data-inventory", 260, ("类型", "数据源", "对象名", "新增或既有", "操作类型", "主数据", "写入方", "读取方", "索引", "保留", "回滚", "证据"), min_rows=2),
    ArtifactRule("state-machine", 140, ("状态", "触发", "终态", "非法", "证据"), min_diagrams=1),
    ArtifactRule("sequence-main", 160, ("创建", "校验", "写入", "执行", "查询", "完成", "事务", "异步", "证据"), min_diagrams=1),
    ArtifactRule("sequence-recovery", 180, ("失败", "重试", "补偿", "补扫", "对账", "中断恢复", "证据"), min_diagrams=1),
    ArtifactRule("impact", 520, ("对象", "判定", "兼容", "验证", "监控", "回滚", "证据"), min_rows=15),
    ArtifactRule("branch", 180, ("phaseId", "parentPhaseId", "branch", "parentCandidateSHA", "baseSHA", "headSHA", "syncStatus", "证据"), min_rows=2),
    ArtifactRule("release", 280, ("DDL", "配置", "开关", "消息", "定时任务", "部署顺序", "验证", "回滚", "负责人", "证据"), min_rows=2),
    ArtifactRule("validation", 200, ("TC-ID", "REQ-ID", "前置", "操作路径", "预期", "实际", "版本", "状态", "证据"), min_rows=2),
    ArtifactRule("traceability", 180, ("REQ", "架构", "代码", "数据", "测试", "发布", "证据"), min_rows=2),
)


class LedgerParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.elements: dict[str, ElementStats] = {}
        self.hash_links: list[str] = []
        self.tab_controls: list[str] = []
        self.external_assets: list[str] = []
        self.has_copy_control = False
        self.phase_panels: dict[str, str] = {}
        self.document_attrs: dict[str, str] = {}
        self._active_ids: list[str] = []
        self._tag_stack: list[tuple[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag == "html":
            self.document_attrs = values.copy()
        element_id = values.get("id") or None
        if element_id:
            self.ids.append(element_id)
            self.elements[element_id] = ElementStats(attrs=values.copy())

        targets = [*self._active_ids]
        if element_id:
            targets.append(element_id)
        for target in targets:
            stats = self.elements[target]
            stats.tags[tag] += 1
            if tag == "tr":
                stats.rows += 1
            if tag == "svg" or "data-diagram" in values:
                stats.diagrams += 1
            diagram_kind = values.get("data-diagram-kind")
            if diagram_kind:
                stats.diagram_kinds.add(diagram_kind)
            entity = values.get("data-entity")
            if entity:
                stats.entities.add(entity)
            relationship = values.get("data-relationship")
            if relationship:
                stats.relationships.add(relationship)
            data_object = values.get("data-object")
            if data_object:
                stats.data_objects.add(data_object)
                if values.get("data-object-kind") == "table":
                    stats.table_objects.add(data_object)
            category = values.get("data-impact-category")
            if category:
                stats.impact_categories.add(category)

        href = values.get("href", "")
        if href.startswith("#") and len(href) > 1:
            route = href[1:]
            self.hash_links.append(route)
            for target in targets:
                self.elements[target].link_targets.add(route)
        if values.get("role") == "tab" and values.get("aria-controls"):
            self.tab_controls.append(values["aria-controls"])
        if "data-copy-text" in values or "data-copy-target" in values:
            self.has_copy_control = True
        if tag == "script" and values.get("src", "").startswith(("http://", "https://")):
            self.external_assets.append(values["src"])
        if tag == "link" and values.get("href", "").startswith(("http://", "https://")):
            self.external_assets.append(values["href"])

        phase_id = values.get("data-phase-id")
        if phase_id and element_id:
            self.phase_panels[phase_id] = element_id

        if tag not in VOID_TAGS:
            self._tag_stack.append((tag, element_id))
            if element_id:
                self._active_ids.append(element_id)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        while self._tag_stack:
            open_tag, element_id = self._tag_stack.pop()
            if element_id and element_id in self._active_ids:
                self._active_ids.remove(element_id)
            if open_tag == tag:
                break

    def handle_data(self, data: str) -> None:
        value = data.strip()
        if not value:
            return
        for target in self._active_ids:
            self.elements[target].text_parts.append(value)


def parse_ledger(path: Path) -> tuple[str, LedgerParser, list[str]]:
    errors: list[str] = []
    if not path.is_file():
        return "", LedgerParser(), [f"file not found: {path}"]
    source = path.read_text(encoding="utf-8")
    parser = LedgerParser()
    try:
        parser.feed(source)
    except Exception as exc:
        errors.append(f"HTML parse error: {exc}")
    return source, parser, errors


def parse_comment_data(source: str, parser: LedgerParser, errors: list[str]) -> dict[str, object]:
    element = parser.elements.get("ledger-comments-data")
    if element and element.attrs.get("type") != "application/json":
        errors.append("ledger-comments-data type must be application/json")
    match = re.search(r'<script\b[^>]*\bid=["\']ledger-comments-data["\'][^>]*>(.*?)</script>', source, flags=re.I | re.S)
    if not match:
        errors.append("missing embedded ledger-comments-data JSON")
        return {"threads": []}
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        errors.append(f"invalid ledger-comments-data JSON: {exc.msg}")
        return {"threads": []}
    if not isinstance(data, dict):
        errors.append("ledger-comments-data must be a JSON object")
        return {"threads": []}
    if data.get("version") != 1:
        errors.append("ledger-comments-data version must be 1")
    if data.get("taskId") != parser.document_attrs.get("data-task-id"):
        errors.append("comment taskId must match html data-task-id")
    if data.get("ledgerVersion") != parser.document_attrs.get("data-ledger-version"):
        errors.append("comment ledgerVersion must match html data-ledger-version")
    threads = data.get("threads")
    if not isinstance(threads, list):
        errors.append("ledger-comments-data threads must be a list")
        data["threads"] = []
        return data

    thread_ids: set[str] = set()
    message_ids: set[str] = set()
    allowed_status = {"open", "answered", "change-applied", "needs-clarification", "stale-target", "resolved"}
    allowed_severity = {"question", "suggestion", "blocker"}
    for index, thread in enumerate(threads):
        label = f"comment thread[{index}]"
        if not isinstance(thread, dict):
            errors.append(f"{label} must be an object")
            continue
        thread_id = thread.get("id")
        if not isinstance(thread_id, str) or not thread_id:
            errors.append(f"{label} missing id")
        elif thread_id in thread_ids:
            errors.append(f"duplicate comment id: {thread_id}")
        else:
            thread_ids.add(thread_id)
        if thread.get("severity") not in allowed_severity:
            errors.append(f"{label} invalid severity")
        if thread.get("status") not in allowed_status:
            errors.append(f"{label} invalid status")
        target = thread.get("target")
        if not isinstance(target, dict):
            errors.append(f"{label} missing target")
        else:
            section_id = target.get("sectionId")
            if section_id not in parser.elements:
                errors.append(f"{label} target section missing: {section_id}")
            if target.get("type") not in {"text", "resource"}:
                errors.append(f"{label} target type must be text or resource")
            if target.get("type") == "text" and not target.get("quote"):
                errors.append(f"{label} text target requires quote")
            if target.get("type") == "text" and section_id in parser.elements and target.get("quote") not in parser.elements[section_id].text and thread.get("status") != "stale-target":
                errors.append(f"{label} text quote no longer matches target section")
        messages = thread.get("messages")
        if not isinstance(messages, list) or not messages:
            errors.append(f"{label} requires at least one message")
            continue
        for message in messages:
            if not isinstance(message, dict):
                errors.append(f"{label} message must be an object")
                continue
            message_id = message.get("id")
            if not isinstance(message_id, str) or not message_id:
                errors.append(f"{label} message missing id")
            elif message_id in message_ids:
                errors.append(f"duplicate comment message id: {message_id}")
            else:
                message_ids.add(message_id)
            if message.get("author") not in {"user", "ai"}:
                errors.append(f"{label} message author must be user or ai")
            if not isinstance(message.get("body"), str) or not message.get("body", "").strip():
                errors.append(f"{label} message body is empty")
    return data


def require_terms(stats: ElementStats, terms: tuple[str, ...], label: str, errors: list[str]) -> None:
    missing = [term for term in terms if term not in stats.text]
    if missing:
        errors.append(f"{label} missing terms: {', '.join(missing)}")


def validate_metadata(element_id: str, stats: ElementStats, errors: list[str]) -> None:
    if stats.attrs.get("data-status") != "complete":
        errors.append(f"{element_id} data-status must be complete")
    try:
        evidence_count = int(stats.attrs.get("data-evidence-count", "0"))
    except ValueError:
        evidence_count = 0
    if evidence_count < 1:
        errors.append(f"{element_id} requires data-evidence-count >= 1")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", stats.attrs.get("data-as-of", "")):
        errors.append(f"{element_id} requires data-as-of=YYYY-MM-DD")


def validate_toc(toc_id: str, expected_targets: set[str], parser: LedgerParser, errors: list[str]) -> None:
    if toc_id not in parser.elements:
        errors.append(f"missing section directory: {toc_id}")
        return
    toc = parser.elements[toc_id]
    if "data-section-toc" not in toc.attrs:
        errors.append(f"{toc_id} missing data-section-toc")
    if "目录" not in toc.text:
        errors.append(f"{toc_id} missing visible 目录 label")
    missing = sorted(expected_targets - toc.link_targets)
    if missing:
        errors.append(f"{toc_id} missing links: {', '.join(missing)}")


def validate_structure(source: str, parser: LedgerParser, comment_data: dict[str, object], live: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    counts = Counter(parser.ids)
    duplicates = sorted(item for item, count in counts.items() if count > 1)
    if duplicates:
        errors.append("duplicate ids: " + ", ".join(duplicates))

    missing = sorted(GLOBAL_REQUIRED_IDS - set(parser.ids))
    if missing:
        errors.append("missing global ids: " + ", ".join(missing))
    if not parser.phase_panels:
        errors.append("at least one data-phase-id panel is required")
    if parser.document_attrs.get("data-comments-enabled") != "true":
        errors.append("html must declare data-comments-enabled=true")
    if not parser.document_attrs.get("data-task-id") or not parser.document_attrs.get("data-ledger-version"):
        errors.append("html must declare data-task-id and data-ledger-version")

    expected_controls = {"panel-overview", "panel-integration", "panel-summary", *parser.phase_panels.values()}
    actual_controls = set(parser.tab_controls)
    if actual_controls != expected_controls:
        errors.append(
            "tab controls mismatch; missing="
            + ",".join(sorted(expected_controls - actual_controls))
            + " extra="
            + ",".join(sorted(actual_controls - expected_controls))
        )

    for toc_id, targets in GLOBAL_TOC_TARGETS.items():
        validate_toc(toc_id, targets, parser, errors)

    for phase_id, panel_id in parser.phase_panels.items():
        panel = parser.elements[panel_id]
        expected_panel_id = f"panel-phase-{phase_id}"
        if panel_id != expected_panel_id:
            errors.append(f"phase {phase_id} panel id must be {expected_panel_id}")
        if not re.fullmatch(r"P[1-9]\d*", phase_id):
            errors.append(f"invalid phase id: {phase_id}")
        for attr in ("data-phase-order", "data-phase-name", "data-phase-status", "data-parent-phase"):
            if not panel.attrs.get(attr):
                errors.append(f"{panel_id} missing {attr}")
        for suffix in PHASE_REQUIRED_SUFFIXES:
            element_id = f"phase-{phase_id}-{suffix}"
            if element_id not in parser.elements:
                errors.append(f"missing phase artifact id: {element_id}")
        toc_id = f"toc-phase-{phase_id}"
        expected_targets = {f"phase-{phase_id}-{suffix}" for suffix in PHASE_REQUIRED_SUFFIXES}
        validate_toc(toc_id, expected_targets, parser, errors)
        if toc_id in parser.elements and "上线资源" not in parser.elements[toc_id].text:
            errors.append(f"{toc_id} missing visible 上线资源 link")

    unresolved = []
    for route in parser.hash_links:
        target = route.replace("/", "-")
        if target not in counts:
            unresolved.append(f"#{route} -> #{target}")
    if unresolved:
        errors.append("unresolved anchor routes: " + ", ".join(sorted(set(unresolved))))
    if parser.external_assets:
        errors.append("external CSS/JS assets are not allowed: " + ", ".join(parser.external_assets))
    if not parser.has_copy_control:
        errors.append("missing copy task/evidence control")
    for runtime_token in (
        "prepareCommentables",
        "copyOpenCommentsForAI",
        "syncCommentsToBridge",
        "__LEDGER_COMMENT_BRIDGE__",
        "localStorage",
        "data-commentable",
    ):
        if runtime_token not in source:
            errors.append(f"missing comment runtime capability: {runtime_token}")
    comment_text = " ".join(parser.elements[element_id].text for element_id in ("comments-drawer", "comment-composer") if element_id in parser.elements)
    for label in ("台账讨论", "复制待处理评论", "导出 JSON", "新增评论"):
        if label not in comment_text:
            errors.append(f"missing comment UI label: {label}")

    visible_text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", source))
    for label in ("总览", "跨阶段集成", "总结与审计"):
        if label not in visible_text:
            errors.append(f"missing global tab label: {label}")
    if not re.search(r"DEV-\d{8}-\d{3}", visible_text):
        errors.append("missing canonical task id DEV-YYYYMMDD-NNN")

    demo_markers = [marker for marker in LIVE_FORBIDDEN_MARKERS if marker in source]
    if live and demo_markers:
        errors.append("live ledger still contains demo markers: " + ", ".join(demo_markers))
    elif demo_markers:
        warnings.append("demo markers present (allowed only without --live)")
    return errors, warnings


def validate_comment_gate(comment_data: dict[str, object], phases: list[str], gate: str, errors: list[str]) -> None:
    selected = set(phases)
    for thread in comment_data.get("threads", []):
        if not isinstance(thread, dict) or thread.get("severity") != "blocker" or thread.get("status") == "resolved":
            continue
        target = thread.get("target") if isinstance(thread.get("target"), dict) else {}
        section_id = str(target.get("sectionId", ""))
        matched_phase = next((phase for phase in selected if section_id.startswith(f"phase-{phase}-")), None)
        if matched_phase or gate == "done" and not section_id.startswith("phase-"):
            errors.append(f"unresolved blocker comment prevents gate={gate}: {thread.get('id')} target={section_id}")


def selected_phases(parser: LedgerParser, phase: str | None, errors: list[str]) -> list[str]:
    if phase:
        if phase not in parser.phase_panels:
            errors.append(f"unknown phase: {phase}")
            return []
        return [phase]
    return sorted(parser.phase_panels, key=lambda value: int(value[1:]))


def validate_requirements(parser: LedgerParser, phases: list[str], errors: list[str]) -> None:
    for phase_id in phases:
        context_id = f"phase-{phase_id}-context"
        requirements_id = f"phase-{phase_id}-requirements"
        context = parser.elements[context_id]
        requirements = parser.elements[requirements_id]
        validate_metadata(context_id, context, errors)
        validate_metadata(requirements_id, requirements, errors)
        if len(context.text) < 180:
            errors.append(f"{context_id} requires at least 180 visible characters")
        require_terms(context, ("现状", "真实入口", "痛点", "目标", "非目标", "证据"), context_id, errors)
        if requirements.rows < 2:
            errors.append(f"{requirements_id} requires a header and at least one requirement row")
        require_terms(requirements, ("REQ", "验收标准", "优先级", "状态", "证据"), requirements_id, errors)


def validate_design(parser: LedgerParser, phases: list[str], errors: list[str]) -> None:
    validate_requirements(parser, phases, errors)
    for phase_id in phases:
        for rule in DESIGN_RULES:
            element_id = f"phase-{phase_id}-{rule.suffix}"
            stats = parser.elements[element_id]
            validate_metadata(element_id, stats, errors)
            if len(stats.text) < rule.min_chars:
                errors.append(f"{element_id} requires at least {rule.min_chars} visible characters")
            if stats.rows < rule.min_rows:
                errors.append(f"{element_id} requires at least {rule.min_rows} table rows")
            if stats.diagrams < rule.min_diagrams:
                errors.append(f"{element_id} requires at least {rule.min_diagrams} visible diagram")
            if rule.diagram_kind and rule.diagram_kind not in stats.diagram_kinds:
                errors.append(f"{element_id} requires data-diagram-kind={rule.diagram_kind}")
            if len(stats.entities) < rule.min_entities:
                errors.append(f"{element_id} requires at least {rule.min_entities} ER entities")
            if len(stats.relationships) < rule.min_relationships:
                errors.append(f"{element_id} requires at least {rule.min_relationships} ER relationships")
            require_terms(stats, rule.terms, element_id, errors)

        ui_id = f"phase-{phase_id}-ui"
        ui = parser.elements[ui_id]
        validate_metadata(ui_id, ui, errors)
        if len(ui.text) < 120:
            errors.append(f"{ui_id} requires UI applicability, evidence and constraints")
        require_terms(ui, ("适用性", "理由", "响应式", "无障碍", "Reduced Motion", "证据"), ui_id, errors)

        impact = parser.elements[f"phase-{phase_id}-impact"]
        missing_categories = sorted(IMPACT_CATEGORIES - impact.impact_categories)
        if missing_categories:
            errors.append(f"phase-{phase_id}-impact missing categories: {', '.join(missing_categories)}")

        erd = parser.elements[f"phase-{phase_id}-persistence-model"]
        inventory = parser.elements[f"phase-{phase_id}-data-inventory"]
        missing_inventory = sorted(erd.entities - inventory.table_objects)
        missing_erd = sorted(inventory.table_objects - erd.entities)
        if missing_inventory:
            errors.append(f"phase-{phase_id} ER entities missing from data inventory: {', '.join(missing_inventory)}")
        if missing_erd:
            errors.append(f"phase-{phase_id} data inventory tables missing from ER diagram: {', '.join(missing_erd)}")


def validate_branch(parser: LedgerParser, phases: list[str], errors: list[str]) -> None:
    validate_design(parser, phases, errors)
    sha_pattern = re.compile(r"[0-9a-f]{7,40}")
    for phase_id in phases:
        panel = parser.elements[parser.phase_panels[phase_id]]
        branch_id = f"phase-{phase_id}-branch"
        branch = parser.elements[branch_id]
        parent_phase = panel.attrs.get("data-parent-phase", "")
        branch_name = branch.attrs.get("data-branch-name", "")
        base_sha = branch.attrs.get("data-base-sha", "")
        if phase_id.lower() not in branch_name.lower():
            errors.append(f"{branch_id} branch name must include {phase_id.lower()}")
        if not sha_pattern.fullmatch(base_sha):
            errors.append(f"{branch_id} requires a concrete data-base-sha")
        if branch.attrs.get("data-sync-status") not in {"CURRENT", "PLANNED"}:
            errors.append(f"{branch_id} data-sync-status must be CURRENT or PLANNED")

        if parent_phase == "NONE":
            continue
        if parent_phase not in parser.phase_panels:
            errors.append(f"{branch_id} unknown parent phase {parent_phase}")
            continue
        parent_branch = parser.elements[f"phase-{parent_phase}-branch"]
        parent_candidate = parent_branch.attrs.get("data-candidate-sha", "")
        recorded_parent = branch.attrs.get("data-parent-candidate-sha", "")
        if not sha_pattern.fullmatch(parent_candidate):
            errors.append(f"parent phase {parent_phase} has no concrete candidate SHA")
        if recorded_parent != parent_candidate:
            errors.append(f"{branch_id} parent candidate SHA does not match {parent_phase}")
        if base_sha != recorded_parent:
            errors.append(f"{branch_id} base SHA must equal parent candidate SHA")


def validate_done(parser: LedgerParser, phases: list[str], errors: list[str]) -> None:
    validate_design(parser, phases, errors)
    sha_pattern = re.compile(r"[0-9a-f]{7,40}")
    for phase_id in phases:
        panel = parser.elements[parser.phase_panels[phase_id]]
        if panel.attrs.get("data-phase-status") != "DONE":
            errors.append(f"phase {phase_id} is not DONE")
        branch = parser.elements[f"phase-{phase_id}-branch"]
        for attr in ("data-head-sha", "data-candidate-sha"):
            if not sha_pattern.fullmatch(branch.attrs.get(attr, "")):
                errors.append(f"phase-{phase_id}-branch requires concrete {attr}")

    integration_rules = {
        "integration-dependencies": (140, ("Phase", "接口", "数据", "兼容", "证据")),
        "integration-branches": (140, ("父 SHA", "同步", "状态", "证据")),
        "integration-resources": (140, ("资源", "所有者", "Phase", "回滚", "证据")),
        "integration-release": (160, ("部署顺序", "保护", "验证", "回滚", "证据")),
        "integration-validation": (160, ("用例", "预期", "实际", "版本", "状态", "证据")),
    }
    for element_id, (min_chars, terms) in integration_rules.items():
        stats = parser.elements[element_id]
        validate_metadata(element_id, stats, errors)
        if len(stats.text) < min_chars:
            errors.append(f"{element_id} requires at least {min_chars} visible characters")
        require_terms(stats, terms, element_id, errors)


def validate(path: Path, live: bool, gate: str, phase: str | None) -> tuple[list[str], list[str]]:
    source, parser, parse_errors = parse_ledger(path)
    if parse_errors:
        return parse_errors, []
    comment_errors: list[str] = []
    comment_data = parse_comment_data(source, parser, comment_errors)
    pending_file = path.parent / ".ledger-comments" / "comments.pending.json"
    if pending_file.is_file():
        try:
            from comment_bridge import pending_payload

            pending = pending_payload(path)
            merged = {thread.get("id"): thread for thread in comment_data.get("threads", []) if isinstance(thread, dict)}
            for thread in pending.get("threads", []):
                if not isinstance(thread, dict):
                    continue
                target = thread.get("target")
                section_id = target.get("sectionId") if isinstance(target, dict) else None
                if not isinstance(section_id, str) or section_id not in parser.elements:
                    comment_errors.append(f"pending comment target section missing: {section_id}")
                    continue
                current = merged.get(thread.get("id"))
                if current:
                    messages = {message.get("id"): message for message in current.get("messages", []) if isinstance(message, dict)}
                    for message in thread.get("messages", []):
                        if isinstance(message, dict) and message.get("id"):
                            messages[message.get("id")] = message
                    current.update(thread)
                    current["messages"] = list(messages.values())
                else:
                    merged[thread.get("id")] = thread
            comment_data["threads"] = list(merged.values())
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            comment_errors.append(f"invalid bridge-pending comments: {exc}")
    errors, warnings = validate_structure(source, parser, comment_data, live)
    errors.extend(comment_errors)
    phases = selected_phases(parser, phase, errors)
    if errors and gate == "structure":
        return errors, warnings
    if gate == "requirements":
        validate_requirements(parser, phases, errors)
    elif gate == "design":
        validate_design(parser, phases, errors)
    elif gate == "branch":
        if not phase:
            errors.append("--gate branch requires --phase")
        else:
            validate_branch(parser, phases, errors)
    elif gate == "done":
        validate_done(parser, phases, errors)
    if gate != "structure":
        validate_comment_gate(comment_data, phases, gate, errors)
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path, help="path to index.html")
    parser.add_argument("--live", action="store_true", help="reject bundled demo values")
    parser.add_argument(
        "--gate",
        choices=("structure", "requirements", "design", "branch", "done"),
        default="structure",
        help="semantic gate to validate",
    )
    parser.add_argument("--phase", help="phase id such as P1; omit to validate all phases")
    args = parser.parse_args()

    errors, warnings = validate(args.ledger.expanduser().resolve(), args.live, args.gate, args.phase)
    for warning in warnings:
        print(f"[WARN] {warning}")
    for error in errors:
        print(f"[ERROR] {error}")
    if errors:
        print(f"[FAIL] {len(errors)} validation error(s)")
        return 1
    target = f" phase={args.phase}" if args.phase else ""
    print(f"[OK] lifecycle ledger gate={args.gate}{target} is valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
