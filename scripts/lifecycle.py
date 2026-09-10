#!/usr/bin/env python3
"""Manage SQLite lifecycle workspaces, structured tasks and review views."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import unicodedata
import uuid
from pathlib import Path
from typing import Any

from workspace_store import Store, binding, default_database


SKILL_ROOT = Path(__file__).resolve().parents[1]
SHELL_PATH = SKILL_ROOT / "assets" / "ledger-v2-shell.html"
TASK_FILE = "task.json"
EVENTS_FILE = "events.jsonl"
COMMENTS_FILE = "comments.json"
HTML_FILE = "index.html"

PROFILES = {"FAST", "STANDARD", "STRICT"}
RENDER_MODES = {"AUTO", "COMPACT", "STRUCTURED", "DEEP"}
GATES = {"structure", "requirements", "design", "branch", "done"}
PHASE_STATES = {
    "DISCOVERY",
    "REQUIREMENTS_REVIEW",
    "REQUIREMENTS_APPROVED",
    "DESIGN_REVIEW",
    "DESIGN_APPROVED",
    "IMPLEMENTING",
    "LOCAL_VERIFY",
    "SPEC_ARCHIVED",
    "CANDIDATE_PUSHED",
    "READY_DEPLOY",
    "DEPLOYING",
    "E2E",
    "FIXING",
    "FINALIZING",
    "DONE",
}

ARTIFACT_KEYS = (
    "functionalBreakdown",
    "applicationArchitecture",
    "codeArchitecture",
    "uiDesign",
    "dataArchitecture",
    "domainModel",
    "persistenceModel",
    "dataInventory",
    "stateMachine",
    "mainFlow",
    "recoveryFlow",
    "impact",
    "release",
    "validation",
    "traceability",
)

ARTIFACT_LABELS = {
    "functionalBreakdown": "功能拆解",
    "applicationArchitecture": "应用架构",
    "codeArchitecture": "代码架构",
    "uiDesign": "UI 与交互",
    "dataArchitecture": "数据读写架构",
    "domainModel": "领域模型",
    "persistenceModel": "表级 ER 模型",
    "dataInventory": "数据资产清单",
    "stateMachine": "状态机",
    "mainFlow": "主流程",
    "recoveryFlow": "异常恢复",
    "impact": "影响分析",
    "release": "上线资源",
    "validation": "测试与证据",
    "traceability": "需求追踪",
}

ARTIFACT_SUFFIXES = {
    "functionalBreakdown": "functional-breakdown",
    "applicationArchitecture": "architecture",
    "codeArchitecture": "code-architecture",
    "uiDesign": "ui",
    "dataArchitecture": "data-architecture",
    "domainModel": "domain-model",
    "persistenceModel": "persistence-model",
    "dataInventory": "data-inventory",
    "stateMachine": "state-machine",
    "mainFlow": "sequence-main",
    "recoveryFlow": "sequence-recovery",
    "impact": "impact",
    "release": "release",
    "validation": "validation",
    "traceability": "traceability",
}

STRICT_RISK_SIGNALS = {
    "multiPhase",
    "payment",
    "auth",
    "schemaChange",
    "dataMigration",
    "publicContract",
    "irreversible",
    "externalDeploy",
}

DEEP_RENDER_SIGNALS = {
    "schemaChange",
    "dataMigration",
    "asyncFlow",
    "stateful",
    "payment",
    "externalIntegration",
    "externalDeploy",
}

STRUCTURED_RENDER_SIGNALS = {
    "uiChange",
    "dataDependency",
    "dataChange",
    "configChange",
    "messageChange",
    "scheduledJob",
}

STATE_NEXT_ACTIONS = {
    "DISCOVERY": "补充现状、目标、验收、适用性和代码证据",
    "REQUIREMENTS_REVIEW": "完成需求评审候选并运行 requirements checkpoint",
    "REQUIREMENTS_APPROVED": "完成方案与测试设计并运行 design checkpoint",
    "DESIGN_REVIEW": "完成方案与测试设计并运行 design checkpoint",
    "DESIGN_APPROVED": "按已批准方案创建 feat worktree 和 OpenSpec change",
    "IMPLEMENTING": "完成实现并进入本地验证",
    "LOCAL_VERIFY": "完成适用的单测、集成、构建和静态检查",
    "SPEC_ARCHIVED": "生成并推送可部署 feat 候选 SHA",
    "CANDIDATE_PUSHED": "核对项目评审/部署流程，准备候选版本、环境和回滚信息",
    "READY_DEPLOY": "执行已授权的项目发布流程并核验实际版本",
    "DEPLOYING": "只读核对自动部署任务、实际构建版本、实例健康和回滚点；不要重复手工部署",
    "E2E": "执行浏览器 E2E、日志核验和必要回归",
    "FIXING": "回任务分支修复、验证新候选并按项目流程重新发布",
    "FINALIZING": "核对最终 SHA、证据、遗留项和完成门禁",
    "DONE": "任务已完成；仅在验收补充、重开或新任务时继续",
}


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def today_text() -> str:
    return dt.date.today().isoformat()


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return slug[:48] or "task"


def atomic_write(path: Path, content: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(content, encoding="utf-8")
    os.chmod(temp, mode)
    os.replace(temp, path)


def write_json(path: Path, value: Any, mode: int = 0o644) -> None:
    bound = binding(path)
    if bound:
        store, key, name = bound
        store.put_document(key, name, value)
        return
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n", mode)


def read_json(path: Path) -> Any:
    bound = binding(path)
    if bound:
        return bound[0].get_document(bound[1], bound[2])[0]
    return json.loads(path.read_text(encoding="utf-8"))


def load_events(task_dir: Path) -> list[dict[str, Any]]:
    bound = binding(task_dir)
    if bound:
        return bound[0].events(bound[1])
    path = task_dir / EVENTS_FILE
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{EVENTS_FILE}:{line_number} must contain a JSON object")
        events.append(value)
    return events


def append_event(task_dir: Path, event_type: str, summary: str, **extra: Any) -> dict[str, Any]:
    event = {
        "id": f"EVT-{dt.datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}",
        "at": now_iso(),
        "type": event_type,
        "summary": summary,
        **extra,
    }
    path = task_dir / EVENTS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    bound = binding(task_dir)
    if bound:
        bound[0].event(bound[1], event)
        return event
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
    return event


def allocate_task_id(root: Path) -> str:
    date_key = dt.date.today().strftime("%Y%m%d")
    pattern = re.compile(rf"^DEV-{date_key}-(\d{{3}})(?:-|$)")
    used = []
    if root.is_dir():
        for child in root.iterdir():
            match = pattern.match(child.name)
            if match:
                used.append(int(match.group(1)))
    return f"DEV-{date_key}-{max(used, default=0) + 1:03d}"


def artifact_record() -> dict[str, Any]:
    return {"status": "pending", "summary": "", "evidence": [], "details": []}


def phase_record(phase_id: str, name: str, parent_phase: str = "NONE") -> dict[str, Any]:
    return {
        "schemaVersion": 2,
        "id": phase_id,
        "name": name,
        "state": "DISCOVERY",
        "parentPhaseId": parent_phase,
        "scope": {
            "currentBehavior": "",
            "goals": [],
            "nonGoals": [],
            "evidence": [],
            "assumptions": [],
            "blockingDecisions": [],
        },
        "requirements": [],
        "applicability": {
            "runtimeCode": True,
            "uiChange": False,
            "dataDependency": False,
            "dataChange": False,
            "schemaChange": False,
            "dataMigration": False,
            "asyncFlow": False,
            "stateful": False,
            "payment": False,
            "auth": False,
            "publicContract": False,
            "externalIntegration": False,
            "externalDeploy": False,
            "configChange": False,
            "messageChange": False,
            "scheduledJob": False,
            "irreversible": False,
        },
        "artifacts": {key: artifact_record() for key in ARTIFACT_KEYS},
        "approvals": {"requirements": None, "design": None},
        "branch": {
            "name": "",
            "parentBranch": "",
            "parentCandidateSha": "",
            "baseSha": "",
            "headSha": "",
            "candidateSha": "",
            "syncStatus": "PLANNED",
        },
        "releases": [],
        "releaseChecklist": [
            {"id": f"REL-{i:02d}", "title": title, "checked": False}
            for i, title in enumerate(("核对目标版本与发布范围", "检查配置与资源变更", "确认回滚版本与操作步骤", "完成部署并核对版本", "完成核心路径验证", "记录观察结果与最终结论"), 1)
        ],
        "workItems": [],
        "tests": [],
        "issues": [],
        "traceability": [],
        "nextAction": "补充现状、目标、验收和代码证据",
    }


def task_record(task_id: str, title: str, profile: str, phase: dict[str, Any]) -> dict[str, Any]:
    stamp = now_iso()
    return {
        "schemaVersion": 2,
        "taskId": task_id,
        "title": title,
        "profile": profile,
        "renderMode": "AUTO",
        "state": "DISCOVERY",
        "activePhase": phase["id"],
        "version": 1,
        "createdAt": stamp,
        "updatedAt": stamp,
        "owner": "待确认",
        "repositories": [],
        "phases": [{
            "id": phase["id"],
            "name": phase["name"],
            "parentPhaseId": phase["parentPhaseId"],
            "file": f"phases/{phase['id']}.json",
        }],
        "blockers": [],
        "nextAction": phase["nextAction"],
        "integration": {
            "dependencies": [],
            "branchLineage": [],
            "sharedResources": [],
            "releasePlan": [],
            "tests": [],
        },
    }


def resolve_task_dir(value: str | Path) -> Path:
    task_dir = Path(value).expanduser().resolve()
    if not (task_dir / TASK_FILE).is_file():
        raise ValueError(f"V2 task not found: {task_dir / TASK_FILE}")
    return task_dir


def load_task(task_dir: Path) -> dict[str, Any]:
    value = read_json(task_dir / TASK_FILE)
    if not isinstance(value, dict):
        raise ValueError(f"{TASK_FILE} must contain an object")
    return value


def phase_path(task_dir: Path, entry: dict[str, Any]) -> Path:
    base = task_dir.resolve()
    relative = Path(str(entry.get("file", "")))
    path = (base / relative).resolve()
    if base not in path.parents or path.suffix != ".json":
        raise ValueError(f"unsafe phase file path: {relative}")
    return path


def load_phases(task_dir: Path, task: dict[str, Any]) -> dict[str, dict[str, Any]]:
    phases: dict[str, dict[str, Any]] = {}
    for entry in task.get("phases", []):
        if not isinstance(entry, dict):
            raise ValueError("task phases must be objects")
        value = read_json(phase_path(task_dir, entry))
        if not isinstance(value, dict):
            raise ValueError(f"phase {entry.get('id')} must contain an object")
        phases[str(entry.get("id", ""))] = value
    return phases


def load_comments(task_dir: Path, task_id: str, version: int) -> dict[str, Any]:
    path = task_dir / COMMENTS_FILE
    if not path.is_file():
        return {"version": 1, "taskId": task_id, "ledgerVersion": f"v2.{version}", "threads": []}
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"{COMMENTS_FILE} must contain an object")
    return value


def effective_profile(task: dict[str, Any], phases: dict[str, dict[str, Any]]) -> str:
    requested = str(task.get("profile", "STANDARD")).upper()
    if requested == "STRICT" or len(phases) > 1:
        return "STRICT"
    for phase in phases.values():
        applicability = phase.get("applicability", {})
        if isinstance(applicability, dict) and any(bool(applicability.get(key)) for key in STRICT_RISK_SIGNALS):
            return "STRICT"
    return requested if requested in PROFILES else "STANDARD"


def ordered_phases(task: dict[str, Any], phases: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for entry in task.get("phases", []):
        if isinstance(entry, dict) and str(entry.get("id", "")) in phases:
            result.append(phases[str(entry["id"])])
    return result


def recommended_phase(task: dict[str, Any], phases: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    ordered = ordered_phases(task, phases)
    for phase in ordered:
        if str(phase.get("branch", {}).get("syncStatus", "")).upper() == "STALE_PARENT":
            return phase
    for phase in ordered:
        if phase.get("state") != "DONE":
            return phase
    return phases.get(str(task.get("activePhase"))) or (ordered[0] if ordered else None)


def derived_next_action(task: dict[str, Any], phase: dict[str, Any] | None, blockers: list[str] | None = None) -> str:
    blockers = blockers or []
    if blockers:
        return f"先解除阻塞：{blockers[0]}"
    if not phase:
        return str(task.get("nextAction") or "确认当前生命周期任务")
    if str(phase.get("branch", {}).get("syncStatus", "")).upper() == "STALE_PARENT":
        return "同步确切父 feat 候选 SHA，更新谱系并重跑受影响验证"
    return STATE_NEXT_ACTIONS.get(str(phase.get("state")), str(phase.get("nextAction") or task.get("nextAction") or "继续当前 Phase"))


def first_blocking_gate(phase: dict[str, Any] | None) -> str | None:
    if not phase or phase.get("state") == "DONE":
        return None
    state = str(phase.get("state", "DISCOVERY"))
    if state in {"DISCOVERY", "REQUIREMENTS_REVIEW"}:
        return "requirements"
    if state in {"REQUIREMENTS_APPROVED", "DESIGN_REVIEW"}:
        return "design"
    if state == "DESIGN_APPROVED":
        return "branch"
    if state in {"IMPLEMENTING", "LOCAL_VERIFY", "SPEC_ARCHIVED"}:
        return "candidate"
    if state in {"CANDIDATE_PUSHED", "READY_DEPLOY", "DEPLOYING"}:
        return "deployment"
    if state in {"E2E", "FIXING"}:
        return "validation"
    return "done"


def effective_render_mode(
    task: dict[str, Any],
    phases: dict[str, dict[str, Any]],
    events: list[dict[str, Any]] | None = None,
    comments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    requested = str(task.get("renderMode", "AUTO")).upper()
    if requested not in RENDER_MODES:
        requested = "AUTO"
    reasons: list[str] = []
    repositories = task.get("repositories", [])
    repository_count = len(repositories) if isinstance(repositories, list) else 0
    flags: set[str] = set()
    requirements_count = 0
    issues_count = 0
    for phase in phases.values():
        applicability = phase.get("applicability", {})
        if isinstance(applicability, dict):
            flags.update(key for key, value in applicability.items() if bool(value))
        requirements_count += len(phase.get("requirements", [])) if isinstance(phase.get("requirements"), list) else 0
        issues_count += len(phase.get("issues", [])) if isinstance(phase.get("issues"), list) else 0
    open_comments = sum(
        1
        for thread in (comments or {}).get("threads", [])
        if isinstance(thread, dict) and thread.get("status") != "resolved"
    )
    event_count = len(events or [])
    if len(phases) > 1:
        reasons.append("multi-phase")
    if repository_count >= 3:
        reasons.append("three-or-more-repositories")
    if flags & DEEP_RENDER_SIGNALS:
        reasons.append("complex-data-flow-or-deployment")
    if issues_count >= 3 or open_comments >= 8 or event_count >= 40:
        reasons.append("large-iteration-history")
    if reasons:
        automatic = "DEEP"
    else:
        structured_reasons: list[str] = []
        if repository_count > 1:
            structured_reasons.append("multiple-repositories")
        if flags & STRUCTURED_RENDER_SIGNALS:
            structured_reasons.append("applicable-ui-data-or-release-artifacts")
        if requirements_count > 4 or event_count >= 15 or open_comments >= 3:
            structured_reasons.append("moderate-content-volume")
        reasons.extend(structured_reasons)
        automatic = "STRUCTURED" if structured_reasons else "COMPACT"
    effective = automatic if requested == "AUTO" else requested
    return {"requested": requested, "effective": effective, "automatic": automatic, "reasons": reasons or ["single-phase-low-complexity"]}


def required_refreshes(phase: dict[str, Any] | None) -> list[str]:
    if not phase or phase.get("state") == "DONE":
        return []
    state = str(phase.get("state", "DISCOVERY"))
    if state in {"DESIGN_APPROVED", "IMPLEMENTING"}:
        return ["创建或同步任务分支前刷新已核实的远端基线或确切父候选 SHA"]
    if state in {"CANDIDATE_PUSHED", "READY_DEPLOY"}:
        return ["集成前核对项目流程、目标分支和当前候选 SHA", "发布前核对实际目标、候选版本、回滚点及自动部署联动"]
    if state in {"DEPLOYING", "E2E"}:
        return ["E2E 前核对平台实际源码/镜像 SHA 与实例健康"]
    if str(phase.get("branch", {}).get("syncStatus", "")).upper() == "STALE_PARENT":
        return ["刷新父 Phase 远端候选 SHA 并验证 ancestry"]
    return []


def changes_since_last_review(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    approval_at = ""
    for event in events:
        if event.get("type") == "approval":
            approval_at = max(approval_at, str(event.get("at", "")))
    selected = [event for event in events if not approval_at or str(event.get("at", "")) > approval_at]
    return selected[-8:]


def latest_gate_failures(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for event in reversed(events):
        if event.get("type") != "gate-check":
            continue
        key = (str(event.get("phaseId") or "ALL"), str(event.get("gate") or "unknown"))
        if key not in latest:
            latest[key] = event
    return [event for event in latest.values() if event.get("result") == "FAIL"]


def artifact_applicable(key: str, phase: dict[str, Any]) -> bool:
    values = phase.get("applicability", {})
    if not isinstance(values, dict):
        return True
    if key == "uiDesign":
        return bool(values.get("uiChange"))
    if key in {"dataArchitecture", "domainModel", "persistenceModel", "dataInventory"}:
        return any(bool(values.get(name)) for name in ("dataDependency", "dataChange", "schemaChange", "dataMigration", "payment"))
    if key in {"stateMachine", "mainFlow", "recoveryFlow"}:
        return any(bool(values.get(name)) for name in ("asyncFlow", "stateful", "payment", "externalIntegration"))
    if key == "release":
        return any(bool(values.get(name)) for name in ("externalDeploy", "configChange", "schemaChange", "messageChange", "scheduledJob"))
    if key == "applicationArchitecture":
        return bool(values.get("runtimeCode", True))
    return True


def required_artifacts(profile: str, phase: dict[str, Any]) -> set[str]:
    base = {"functionalBreakdown", "codeArchitecture", "impact", "validation", "traceability"}
    if profile == "STRICT":
        return set(ARTIFACT_KEYS)
    if artifact_applicable("applicationArchitecture", phase):
        base.add("applicationArchitecture")
    for key in ARTIFACT_KEYS:
        if artifact_applicable(key, phase) and key in {
            "uiDesign", "dataArchitecture", "domainModel", "persistenceModel", "dataInventory",
            "stateMachine", "mainFlow", "recoveryFlow", "release",
        }:
            base.add(key)
    if profile == "FAST":
        base.discard("applicationArchitecture")
        if bool(phase.get("applicability", {}).get("runtimeCode", True)):
            base.add("codeArchitecture")
    return base


def unresolved_blockers(task: dict[str, Any], phase: dict[str, Any] | None, comments: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for blocker in task.get("blockers", []):
        if isinstance(blocker, str):
            result.append(blocker)
        elif isinstance(blocker, dict) and blocker.get("status", "open") not in {"resolved", "closed"}:
            result.append(str(blocker.get("summary") or blocker.get("id") or "task blocker"))
    if phase:
        scope = phase.get("scope", {})
        for decision in scope.get("blockingDecisions", []) if isinstance(scope, dict) else []:
            if isinstance(decision, str):
                result.append(decision)
            elif isinstance(decision, dict) and decision.get("status", "open") not in {"resolved", "closed"}:
                result.append(str(decision.get("question") or decision.get("id") or "blocking decision"))
    phase_id = phase.get("id") if phase else None
    for thread in comments.get("threads", []):
        if not isinstance(thread, dict) or thread.get("severity") != "blocker" or thread.get("status") == "resolved":
            continue
        target = thread.get("target", {})
        section_id = target.get("sectionId", "") if isinstance(target, dict) else ""
        if not phase_id or not section_id.startswith("phase-") or section_id.startswith(f"phase-{phase_id}-"):
            result.append(str(thread.get("id") or "comment blocker"))
    return result


def validate_structure(task_dir: Path, task: dict[str, Any], phases: dict[str, dict[str, Any]], comments: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if task.get("schemaVersion") != 2:
        errors.append("task schemaVersion must be 2")
    if not re.fullmatch(r"DEV-\d{8}-\d{3}", str(task.get("taskId", ""))):
        errors.append("taskId must match DEV-YYYYMMDD-NNN")
    if not str(task.get("title", "")).strip():
        errors.append("task title is required")
    if str(task.get("profile", "")).upper() not in PROFILES:
        errors.append("task profile must be FAST, STANDARD, or STRICT")
    if str(task.get("renderMode", "AUTO")).upper() not in RENDER_MODES:
        errors.append("task renderMode must be AUTO, COMPACT, STRUCTURED, or DEEP")
    if task.get("state") not in PHASE_STATES:
        errors.append("task has invalid state")
    entries = task.get("phases", [])
    if not isinstance(entries, list) or not entries:
        errors.append("task requires at least one Phase")
    ids = [str(entry.get("id", "")) for entry in entries if isinstance(entry, dict)]
    if len(ids) != len(set(ids)):
        errors.append("phase ids must be unique")
    if task.get("activePhase") not in phases:
        errors.append("activePhase must reference an existing Phase")
    for phase_id, phase in phases.items():
        if not re.fullmatch(r"P[1-9]\d*", phase_id):
            errors.append(f"invalid phase id: {phase_id}")
        if phase.get("schemaVersion") != 2 or phase.get("id") != phase_id:
            errors.append(f"phase {phase_id} schema/id mismatch")
        if phase.get("state") not in PHASE_STATES:
            errors.append(f"phase {phase_id} has invalid state")
        artifacts = phase.get("artifacts")
        if not isinstance(artifacts, dict):
            errors.append(f"phase {phase_id} artifacts must be an object")
        else:
            missing = sorted(set(ARTIFACT_KEYS) - set(artifacts))
            if missing:
                errors.append(f"phase {phase_id} missing artifacts: {', '.join(missing)}")
            for key, value in artifacts.items():
                if not isinstance(value, dict):
                    errors.append(f"phase {phase_id} artifact {key} must be an object")
                elif value.get("status") not in {"pending", "complete", "unchanged", "not-applicable", "superseded"}:
                    errors.append(f"phase {phase_id} artifact {key} has invalid status")
    if comments.get("taskId") != task.get("taskId"):
        errors.append("comments taskId must match taskId")
    for thread in comments.get("threads", []):
        if not isinstance(thread, dict) or not thread.get("id"):
            errors.append("each comment thread requires an id")
            continue
        target = thread.get("target", {})
        section_id = target.get("sectionId", "") if isinstance(target, dict) else ""
        match = re.match(r"^phase-(P\d+)-", str(section_id))
        if match and match.group(1) not in phases:
            errors.append(f"comment {thread.get('id')} targets unknown phase {match.group(1)}")
    try:
        load_events(task_dir)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        errors.append(str(error))
    return errors


def validate_requirements(phase: dict[str, Any], errors: list[str]) -> None:
    phase_id = str(phase.get("id", "?"))
    scope = phase.get("scope", {})
    if not isinstance(scope, dict):
        errors.append(f"phase {phase_id} scope must be an object")
        return
    if not str(scope.get("currentBehavior", "")).strip():
        errors.append(f"phase {phase_id} currentBehavior is required")
    if not scope.get("goals"):
        errors.append(f"phase {phase_id} requires at least one goal")
    if not isinstance(scope.get("nonGoals"), list):
        errors.append(f"phase {phase_id} nonGoals must be a list")
    if not scope.get("evidence"):
        errors.append(f"phase {phase_id} scope requires evidence")
    requirements = phase.get("requirements", [])
    if not isinstance(requirements, list) or not requirements:
        errors.append(f"phase {phase_id} requires at least one requirement")
    else:
        seen: set[str] = set()
        for index, item in enumerate(requirements, 1):
            if not isinstance(item, dict):
                errors.append(f"phase {phase_id} requirement {index} must be an object")
                continue
            req_id = str(item.get("id", ""))
            if not req_id or req_id in seen:
                errors.append(f"phase {phase_id} requirement ids must be non-empty and unique")
            seen.add(req_id)
            if not str(item.get("statement", "")).strip() or not item.get("acceptance"):
                errors.append(f"phase {phase_id} requirement {req_id or index} needs statement and acceptance")
            if not item.get("evidence"):
                errors.append(f"phase {phase_id} requirement {req_id or index} needs evidence")


def validate_artifact(key: str, value: Any, phase: dict[str, Any], errors: list[str]) -> None:
    phase_id = str(phase.get("id", "?"))
    if not isinstance(value, dict):
        errors.append(f"phase {phase_id} artifact {key} must be an object")
        return
    status = value.get("status")
    allowed = {"complete", "unchanged", "not-applicable"}
    if status not in allowed:
        errors.append(f"phase {phase_id} artifact {key} must be complete, unchanged, or not-applicable")
        return
    if status == "not-applicable" and artifact_applicable(key, phase):
        errors.append(f"phase {phase_id} artifact {key} is applicable and cannot be not-applicable")
    if not str(value.get("summary", "")).strip():
        errors.append(f"phase {phase_id} artifact {key} requires a summary")
    if not value.get("evidence"):
        errors.append(f"phase {phase_id} artifact {key} requires evidence")


def approval_present(phase: dict[str, Any], gate: str) -> bool:
    approvals = phase.get("approvals", {})
    value = approvals.get(gate) if isinstance(approvals, dict) else None
    return isinstance(value, dict) and bool(value.get("at")) and bool(value.get("by"))


def validate_design(phase: dict[str, Any], profile: str, errors: list[str]) -> None:
    validate_requirements(phase, errors)
    phase_id = str(phase.get("id", "?"))
    if profile == "STRICT" and not approval_present(phase, "requirements"):
        errors.append(f"phase {phase_id} STRICT design requires requirements approval")
    artifacts = phase.get("artifacts", {})
    for key in sorted(required_artifacts(profile, phase)):
        validate_artifact(key, artifacts.get(key), phase, errors)
    tests = phase.get("tests", [])
    if not isinstance(tests, list) or not tests:
        errors.append(f"phase {phase_id} design requires at least one planned test")
    else:
        for item in tests:
            if not isinstance(item, dict) or not item.get("id") or not item.get("expected"):
                errors.append(f"phase {phase_id} each test needs id and expected result")
                break


def validate_branch(phase: dict[str, Any], phases: dict[str, dict[str, Any]], profile: str, errors: list[str]) -> None:
    validate_design(phase, profile, errors)
    phase_id = str(phase.get("id", "?"))
    if not approval_present(phase, "design"):
        errors.append(f"phase {phase_id} branch gate requires design approval")
    branch = phase.get("branch", {})
    sha = re.compile(r"[0-9a-f]{7,40}")
    if not isinstance(branch, dict) or phase_id.lower() not in str(branch.get("name", "")).lower():
        errors.append(f"phase {phase_id} branch name must contain {phase_id.lower()}")
        return
    if not sha.fullmatch(str(branch.get("baseSha", ""))):
        errors.append(f"phase {phase_id} requires a concrete baseSha")
    parent = str(phase.get("parentPhaseId", "NONE"))
    if parent != "NONE":
        parent_phase = phases.get(parent)
        if not parent_phase:
            errors.append(f"phase {phase_id} has unknown parent {parent}")
        else:
            candidate = str(parent_phase.get("branch", {}).get("candidateSha", ""))
            if not sha.fullmatch(candidate):
                errors.append(f"parent phase {parent} requires a candidateSha")
            if branch.get("parentCandidateSha") != candidate or branch.get("baseSha") != candidate:
                errors.append(f"phase {phase_id} base/parentCandidateSha must equal {parent} candidateSha")


def validate_done(task: dict[str, Any], phases: dict[str, dict[str, Any]], profile: str, comments: dict[str, Any], errors: list[str]) -> None:
    sha = re.compile(r"[0-9a-f]{7,40}")
    if task.get("state") != "DONE":
        errors.append("task state is not DONE")
    for phase in phases.values():
        validate_design(phase, profile, errors)
        phase_id = str(phase.get("id", "?"))
        if phase.get("state") != "DONE":
            errors.append(f"phase {phase_id} is not DONE")
        if not approval_present(phase, "design"):
            errors.append(f"phase {phase_id} lacks design approval")
        applicability = phase.get("applicability", {})
        if isinstance(applicability, dict) and applicability.get("runtimeCode", True):
            candidate = str(phase.get("branch", {}).get("candidateSha", ""))
            if not sha.fullmatch(candidate):
                errors.append(f"phase {phase_id} runtime code requires a final candidateSha")
        if isinstance(applicability, dict) and applicability.get("externalDeploy") and not phase.get("releases"):
            errors.append(f"phase {phase_id} external deployment requires release evidence")
        for test in phase.get("tests", []):
            if not isinstance(test, dict):
                continue
            status = test.get("status")
            if status not in {"PASS", "DEFERRED"}:
                errors.append(f"phase {phase_id} test {test.get('id')} is not PASS or DEFERRED")
            if status == "PASS" and not test.get("evidence"):
                errors.append(f"phase {phase_id} passing test {test.get('id')} requires evidence")
            if status == "DEFERRED" and (not test.get("owner") or not test.get("reason")):
                errors.append(f"phase {phase_id} deferred test {test.get('id')} requires owner and reason")
        for issue in phase.get("issues", []):
            if isinstance(issue, dict) and issue.get("status") not in {"closed", "deferred"}:
                errors.append(f"phase {phase_id} issue {issue.get('id')} is unresolved")
    if unresolved_blockers(task, None, comments):
        errors.append("task has unresolved blockers")
    if len(phases) > 1:
        integration = task.get("integration", {})
        integration_tests = integration.get("tests", []) if isinstance(integration, dict) else []
        if not integration_tests:
            errors.append("multi-Phase task requires integration tests")
        for test in integration_tests:
            if not isinstance(test, dict) or test.get("status") not in {"PASS", "DEFERRED"}:
                errors.append("integration tests must be PASS or DEFERRED")
                continue
            if test.get("status") == "PASS" and not test.get("evidence"):
                errors.append("passing integration tests require evidence")
            if test.get("status") == "DEFERRED" and (not test.get("owner") or not test.get("reason")):
                errors.append("deferred integration tests require owner and reason")


def validate_task(task_dir: Path, gate: str, phase_id: str | None = None) -> tuple[list[str], list[str]]:
    task = load_task(task_dir)
    phases = load_phases(task_dir, task)
    comments = load_comments(task_dir, str(task.get("taskId", "")), int(task.get("version", 1)))
    errors = validate_structure(task_dir, task, phases, comments)
    warnings: list[str] = []
    if errors or gate == "structure":
        return errors, warnings
    profile = effective_profile(task, phases)
    selected: list[dict[str, Any]]
    if phase_id:
        if phase_id not in phases:
            return [f"unknown phase: {phase_id}"], warnings
        selected = [phases[phase_id]]
    else:
        selected = list(phases.values())
    for phase in selected:
        blockers = unresolved_blockers(task, phase, comments)
        if blockers and gate != "done":
            errors.append(f"phase {phase.get('id')} has unresolved blockers: {', '.join(blockers)}")
        if gate == "requirements":
            validate_requirements(phase, errors)
        elif gate == "design":
            validate_design(phase, profile, errors)
        elif gate == "branch":
            if not phase_id:
                errors.append("branch gate requires --phase")
            else:
                validate_branch(phase, phases, profile, errors)
    if gate == "done":
        validate_done(task, phases, profile, comments, errors)
    return errors, warnings


def resume_snapshot(task_dir: Path) -> dict[str, Any]:
    task = load_task(task_dir)
    phases = load_phases(task_dir, task)
    events = load_events(task_dir)
    comments = load_comments(task_dir, str(task.get("taskId", "")), int(task.get("version", 1)))
    phase = recommended_phase(task, phases)
    phase_blockers = {
        phase_id: unresolved_blockers(task, value, comments)
        for phase_id, value in phases.items()
        if unresolved_blockers(task, value, comments)
    }
    open_decisions: list[dict[str, Any]] = []
    for phase_id, value in phases.items():
        scope = value.get("scope", {})
        for index, decision in enumerate(scope.get("blockingDecisions", []) if isinstance(scope, dict) else [], 1):
            if isinstance(decision, str):
                open_decisions.append({"id": f"{phase_id}-DEC-LEGACY-{index}", "phaseId": phase_id, "question": decision, "status": "open"})
            elif isinstance(decision, dict) and decision.get("status", "open") not in {"resolved", "closed"}:
                open_decisions.append({"phaseId": phase_id, **decision})
    open_threads = [
        thread
        for thread in comments.get("threads", [])
        if isinstance(thread, dict) and thread.get("status") != "resolved"
    ]
    selected_blockers = phase_blockers.get(str(phase.get("id")), []) if phase else []
    gate_failures = latest_gate_failures(events)
    action_blockers = list(selected_blockers)
    if gate_failures and gate_failures[0].get("errors"):
        action_blockers.append(str(gate_failures[0]["errors"][0]))
    render = effective_render_mode(task, phases, events, comments)
    lineage = [
        {
            "phaseId": value.get("id"),
            "parentPhaseId": value.get("parentPhaseId"),
            "branch": value.get("branch", {}).get("name"),
            "parentCandidateSha": value.get("branch", {}).get("parentCandidateSha"),
            "baseSha": value.get("branch", {}).get("baseSha"),
            "candidateSha": value.get("branch", {}).get("candidateSha"),
            "syncStatus": value.get("branch", {}).get("syncStatus"),
        }
        for value in ordered_phases(task, phases)
    ]
    return {
        "taskId": task.get("taskId"),
        "taskDir": str(task_dir),
        "title": task.get("title"),
        "version": f"v2.{task.get('version', 1)}",
        "state": task.get("state"),
        "requestedProfile": task.get("profile"),
        "effectiveProfile": effective_profile(task, phases),
        "render": render,
        "activePhase": task.get("activePhase"),
        "recommendedPhase": phase.get("id") if phase else None,
        "phaseStates": {phase_id: value.get("state") for phase_id, value in phases.items()},
        "firstBlockingGate": first_blocking_gate(phase),
        "blockersByPhase": phase_blockers,
        "openDecisions": open_decisions,
        "pendingComments": {
            "total": len(open_threads),
            "blockers": sum(1 for thread in open_threads if thread.get("severity") == "blocker"),
            "questions": sum(1 for thread in open_threads if thread.get("severity") == "question"),
            "suggestions": sum(1 for thread in open_threads if thread.get("severity") == "suggestion"),
        },
        "branchLineage": lineage,
        "requiredRefreshes": required_refreshes(phase),
        "gateFailures": gate_failures,
        "nextAction": derived_next_action(task, phase, action_blockers),
        "recentEvents": events[-12:],
        "nextEventCursor": events[-1].get("id") if events else None,
        "filesToRead": [
            str(task_dir / TASK_FILE),
            str(task_dir / "phases" / f"{phase.get('id')}.json") if phase else None,
            str(task_dir / EVENTS_FILE),
        ],
        "updatedAt": task.get("updatedAt"),
    }


def json_for_script(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def render_task(task_dir: Path) -> Path:
    bound = binding(task_dir)
    if bound:
        bound[0].export(bound[1])
    task = load_task(task_dir)
    phases = load_phases(task_dir, task)
    events = load_events(task_dir)
    comments = load_comments(task_dir, str(task.get("taskId", "")), int(task.get("version", 1)))
    resume = resume_snapshot(task_dir)
    snapshot = {
        "task": task,
        "phases": phases,
        "events": events,
        "effectiveProfile": effective_profile(task, phases),
        "render": resume["render"],
        "resume": resume,
        "recentChanges": changes_since_last_review(events),
        "requiredArtifacts": {phase_id: sorted(required_artifacts(effective_profile(task, phases), phase)) for phase_id, phase in phases.items()},
        "artifactLabels": ARTIFACT_LABELS,
        "artifactSuffixes": ARTIFACT_SUFFIXES,
    }
    shell = SHELL_PATH.read_text(encoding="utf-8")
    replacements = {
        "__TASK_ID__": str(task.get("taskId", "")),
        "__LEDGER_VERSION__": f"v2.{task.get('version', 1)}",
        "__TITLE__": html.escape(str(task.get("title", "Lifecycle task")), quote=True),
        "__LEDGER_DATA__": json_for_script(snapshot),
        "__LEDGER_COMMENTS__": json_for_script(comments),
    }
    for marker, value in replacements.items():
        shell = shell.replace(marker, value)
    output = task_dir / HTML_FILE
    atomic_write(output, shell)
    return output


def merge_threads(existing: list[Any], incoming: list[Any]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {str(item.get("id")): item for item in existing if isinstance(item, dict) and item.get("id")}
    for item in incoming:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        thread_id = str(item["id"])
        current = merged.get(thread_id)
        if not current:
            merged[thread_id] = item
            continue
        messages = {str(message.get("id")): message for message in current.get("messages", []) if isinstance(message, dict) and message.get("id")}
        for message in item.get("messages", []):
            if isinstance(message, dict) and message.get("id"):
                messages[str(message["id"])] = message
        if str(item.get("updatedAt", "")) >= str(current.get("updatedAt", "")):
            current.update(item)
        current["messages"] = sorted(messages.values(), key=lambda value: str(value.get("createdAt", "")))
    return sorted(merged.values(), key=lambda value: str(value.get("createdAt", "")))


def merge_pending_comment_details(task_dir: Path, task: dict[str, Any]) -> dict[str, Any]:
    comments = load_comments(task_dir, str(task["taskId"]), int(task.get("version", 1)))
    pending_path = task_dir / ".ledger-comments" / "comments.pending.json"
    if not pending_path.is_file():
        write_json(task_dir / COMMENTS_FILE, comments)
        return {"changed": False, "added": 0, "updated": 0, "total": len(comments.get("threads", []))}
    pending = read_json(pending_path)
    if not isinstance(pending, dict) or pending.get("taskId") != task.get("taskId"):
        raise ValueError("pending comments taskId mismatch")
    existing = {str(item.get("id")): item for item in comments.get("threads", []) if isinstance(item, dict) and item.get("id")}
    merged = merge_threads(comments.get("threads", []), pending.get("threads", []))
    merged_by_id = {str(item.get("id")): item for item in merged if isinstance(item, dict) and item.get("id")}
    changed_ids = [thread_id for thread_id, value in merged_by_id.items() if existing.get(thread_id) != value]
    comments["threads"] = merged
    comments["ledgerVersion"] = f"v2.{task.get('version', 1)}"
    write_json(task_dir / COMMENTS_FILE, comments)
    return {
        "changed": bool(changed_ids),
        "added": sum(1 for thread_id in changed_ids if thread_id not in existing),
        "updated": sum(1 for thread_id in changed_ids if thread_id in existing),
        "total": len(merged),
    }


def merge_pending_comments(task_dir: Path, task: dict[str, Any]) -> int:
    return int(merge_pending_comment_details(task_dir, task)["added"])


def touch_task(task_dir: Path, task: dict[str, Any]) -> None:
    task["version"] = int(task.get("version", 1)) + 1
    task["updatedAt"] = now_iso()
    write_json(task_dir / TASK_FILE, task)
    comments = load_comments(task_dir, str(task["taskId"]), int(task["version"]))
    comments["ledgerVersion"] = f"v2.{task['version']}"
    write_json(task_dir / COMMENTS_FILE, comments)


def command_init(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    task_markers = [name for name in (TASK_FILE, HTML_FILE) if (root / name).exists()]
    if task_markers:
        markers = ", ".join(task_markers)
        raise ValueError(
            f"--root must be a parent task root, not an existing task directory "
            f"({root} contains {markers})"
        )
    task_id = args.task_id or allocate_task_id(root)
    if not re.fullmatch(r"DEV-\d{8}-\d{3}", task_id):
        raise ValueError("--task-id must match DEV-YYYYMMDD-NNN")
    slug = args.slug or slugify(args.title)
    task_dir = root / f"{task_id}-{slug}"
    if task_dir.exists():
        raise FileExistsError(f"task directory already exists: {task_dir}")
    phase = phase_record("P1", args.phase_name)
    task = task_record(task_id, args.title, args.profile, phase)
    write_json(task_dir / TASK_FILE, task)
    write_json(task_dir / "phases" / "P1.json", phase)
    write_json(task_dir / COMMENTS_FILE, {"version": 1, "taskId": task_id, "ledgerVersion": "v2.1", "threads": []})
    (task_dir / "evidence").mkdir(parents=True, exist_ok=True)
    append_event(task_dir, "task-created", f"Created V2 lifecycle task {task_id}", phaseId="P1", profile=args.profile)
    output = render_task(task_dir)
    result = {"ok": True, "taskDir": str(task_dir), "ledger": str(output), "taskId": task_id}
    if getattr(args, 'storage', 'json') == 'sqlite':
        store = Store(getattr(args, 'database', None))
        key = store.import_task(task_dir, getattr(args,'project',None), getattr(args,'project_root',''))
        if getattr(args,'thread_id',None):
            store.configure(key,thread_id=args.thread_id,transfer_thread=getattr(args,'transfer_thread',False))
        result.update(database=str(store.path), taskKey=key, storage='sqlite')
    print(json.dumps(result, ensure_ascii=False))
    return 0


def command_status(args: argparse.Namespace) -> int:
    task_dir = resolve_task_dir(args.task_dir)
    resume = resume_snapshot(task_dir)
    value = {key: resume[key] for key in (
        "taskId", "title", "state", "requestedProfile", "effectiveProfile", "activePhase",
        "recommendedPhase", "phaseStates", "firstBlockingGate", "nextAction", "version", "updatedAt",
    )}
    value["blockers"] = resume["blockersByPhase"].get(str(resume["recommendedPhase"]), [])
    value["renderMode"] = resume["render"]["effective"]
    if args.format == "json":
        print(json.dumps(value, ensure_ascii=False, indent=2))
    else:
        print(f"{value['taskId']} {value['title']}")
        print(f"state={value['state']} phase={value['activePhase']} profile={value['effectiveProfile']} version={value['version']}")
        print(f"blockers={len(value['blockers'])} next={value['nextAction']}")
    return 0


def command_resume(args: argparse.Namespace) -> int:
    task_dir = resolve_task_dir(args.task_dir)
    bound = binding(task_dir)
    if bound:
        bound[0].export(bound[1])
    print(json.dumps(resume_snapshot(task_dir), ensure_ascii=False, indent=2))
    return 0


def command_sync_comments(args: argparse.Namespace) -> int:
    task_dir = resolve_task_dir(args.task_dir)
    task = load_task(task_dir)
    details = merge_pending_comment_details(task_dir, task)
    if details["changed"]:
        append_event(
            task_dir,
            "comments-synced",
            f"Synced {details['added']} new and {details['updated']} updated comment threads",
            result="PASS",
            **details,
        )
        touch_task(task_dir, task)
    output = render_task(task_dir)
    comments = load_comments(task_dir, str(task.get("taskId", "")), int(task.get("version", 1)))
    actionable = [
        {
            "id": thread.get("id"),
            "severity": thread.get("severity"),
            "status": thread.get("status"),
            "sectionId": thread.get("target", {}).get("sectionId") if isinstance(thread.get("target"), dict) else None,
        }
        for thread in comments.get("threads", [])
        if isinstance(thread, dict) and thread.get("status") != "resolved"
    ]
    print(json.dumps({"ok": True, "merge": details, "actionable": actionable, "ledger": str(output)}, ensure_ascii=False, indent=2))
    return 0


def command_validate(args: argparse.Namespace) -> int:
    task_dir = resolve_task_dir(args.task_dir)
    errors, warnings = validate_task(task_dir, args.gate, args.phase)
    result = {"ok": not errors, "gate": args.gate, "phase": args.phase, "errors": errors, "warnings": warnings}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


def command_render(args: argparse.Namespace) -> int:
    task_dir = resolve_task_dir(args.task_dir)
    output = render_task(task_dir)
    print(json.dumps({"ok": True, "ledger": str(output)}, ensure_ascii=False))
    return 0


def command_checkpoint(args: argparse.Namespace) -> int:
    task_dir = resolve_task_dir(args.task_dir)
    task = load_task(task_dir)
    comment_merge = merge_pending_comment_details(task_dir, task)
    errors, warnings = validate_task(task_dir, args.gate, args.phase)
    append_event(
        task_dir,
        "gate-check",
        f"Gate {args.gate} {'passed' if not errors else 'failed'}",
        gate=args.gate,
        phaseId=args.phase,
        result="PASS" if not errors else "FAIL",
        errors=errors,
        mergedComments=comment_merge["added"],
        commentMerge=comment_merge,
    )
    touch_task(task_dir, task)
    output = render_task(task_dir)
    result = {"ok": not errors, "gate": args.gate, "phase": args.phase, "errors": errors, "warnings": warnings, "mergedComments": comment_merge["added"], "commentMerge": comment_merge, "ledger": str(output)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


def command_approve(args: argparse.Namespace) -> int:
    task_dir = resolve_task_dir(args.task_dir)
    task = load_task(task_dir)
    phases = load_phases(task_dir, task)
    if args.phase not in phases:
        raise ValueError(f"unknown phase: {args.phase}")
    if args.gate == "combined" and effective_profile(task, phases) == "STRICT":
        raise ValueError("STRICT tasks require separate requirements and design approvals")
    phase = phases[args.phase]
    gates = ["requirements", "design"] if args.gate == "combined" else [args.gate]
    for gate in gates:
        validation_gate = "design" if gate == "design" else "requirements"
        errors, _ = validate_task(task_dir, validation_gate, args.phase)
        if errors:
            print(json.dumps({"ok": False, "gate": gate, "errors": errors}, ensure_ascii=False, indent=2))
            return 1
        phase["approvals"][gate] = {"by": args.by, "at": now_iso(), "note": args.note or "Explicit user confirmation"}
    if "design" in gates:
        phase["state"] = "DESIGN_APPROVED"
    elif "requirements" in gates:
        phase["state"] = "REQUIREMENTS_APPROVED"
    entry = next(item for item in task["phases"] if item["id"] == args.phase)
    write_json(phase_path(task_dir, entry), phase)
    task["state"] = phase["state"]
    append_event(task_dir, "approval", f"Approved {args.gate} for {args.phase}", phaseId=args.phase, gate=args.gate, by=args.by)
    touch_task(task_dir, task)
    output = render_task(task_dir)
    print(json.dumps({"ok": True, "phase": args.phase, "gate": args.gate, "ledger": str(output)}, ensure_ascii=False))
    return 0


def command_add_phase(args: argparse.Namespace) -> int:
    task_dir = resolve_task_dir(args.task_dir)
    task = load_task(task_dir)
    phases = load_phases(task_dir, task)
    next_number = max((int(value[1:]) for value in phases), default=0) + 1
    phase_id = args.phase_id or f"P{next_number}"
    if phase_id in phases or not re.fullmatch(r"P[1-9]\d*", phase_id):
        raise ValueError(f"invalid or duplicate phase id: {phase_id}")
    parent = args.parent or str(task.get("activePhase"))
    if parent not in phases:
        raise ValueError(f"unknown parent phase: {parent}")
    phase = phase_record(phase_id, args.name, parent)
    relative = f"phases/{phase_id}.json"
    write_json(task_dir / relative, phase)
    task["phases"].append({"id": phase_id, "name": args.name, "parentPhaseId": parent, "file": relative})
    task["activePhase"] = phase_id
    task["profile"] = "STRICT"
    task["state"] = "DISCOVERY"
    append_event(task_dir, "phase-added", f"Added {phase_id} {args.name}", phaseId=phase_id, parentPhaseId=parent)
    touch_task(task_dir, task)
    output = render_task(task_dir)
    print(json.dumps({"ok": True, "phase": phase_id, "ledger": str(output)}, ensure_ascii=False))
    return 0


def command_event(args: argparse.Namespace) -> int:
    task_dir = resolve_task_dir(args.task_dir)
    task = load_task(task_dir)
    evidence = args.evidence or []
    event = append_event(
        task_dir,
        args.type,
        args.summary,
        phaseId=args.phase,
        result=args.result,
        evidence=evidence,
    )
    touch_task(task_dir, task)
    output = render_task(task_dir)
    print(json.dumps({"ok": True, "eventId": event["id"], "ledger": str(output)}, ensure_ascii=False))
    return 0


def command_serve(args: argparse.Namespace) -> int:
    task_dir = resolve_task_dir(args.task_dir)
    render_task(task_dir)
    sys.path.insert(0, str(SKILL_ROOT / "scripts"))
    from comment_bridge import start  # type: ignore

    start(argparse.Namespace(ledger=task_dir / HTML_FILE, port=args.port))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="create a V2 task")
    init.add_argument("--title", required=True)
    init.add_argument("--root", default=str(Path.home() / "Documents" / "Codex" / "dev-tasks" / today_text()))
    init.add_argument("--task-id")
    init.add_argument("--slug")
    init.add_argument("--phase-name", default="首期交付")
    init.add_argument("--profile", choices=sorted(PROFILES), default="STANDARD")
    init.add_argument('--storage',choices=('sqlite','json'),default='sqlite',help='SQLite is the default; JSON is for legacy compatibility')
    init.add_argument('--database',default=str(default_database()))
    init.add_argument('--project',help='Project name displayed in the board')
    init.add_argument('--project-root',default=str(Path.cwd()))
    init.add_argument('--thread-id',default=os.environ.get('CODEX_THREAD_ID'))
    init.add_argument('--transfer-thread',action='store_true')
    init.set_defaults(function=command_init)

    status = commands.add_parser("status", help="show compact task state")
    status.add_argument("task_dir")
    status.add_argument("--format", choices=("text", "json"), default="text")
    status.set_defaults(function=command_status)

    resume = commands.add_parser("resume", help="show a decision-ready multi-turn resume snapshot")
    resume.add_argument("task_dir")
    resume.set_defaults(function=command_resume)

    sync_comments = commands.add_parser("sync-comments", help="merge pending comments without running a gate")
    sync_comments.add_argument("task_dir")
    sync_comments.set_defaults(function=command_sync_comments)

    validate = commands.add_parser("validate", help="validate one gate")
    validate.add_argument("task_dir")
    validate.add_argument("--gate", choices=sorted(GATES), required=True)
    validate.add_argument("--phase")
    validate.set_defaults(function=command_validate)

    checkpoint = commands.add_parser("checkpoint", help="merge comments, validate, append event, and render")
    checkpoint.add_argument("task_dir")
    checkpoint.add_argument("--gate", choices=sorted(GATES), required=True)
    checkpoint.add_argument("--phase")
    checkpoint.set_defaults(function=command_checkpoint)

    render = commands.add_parser("render", help="regenerate index.html")
    render.add_argument("task_dir")
    render.set_defaults(function=command_render)

    approve = commands.add_parser("approve", help="record explicit gate approval after validation")
    approve.add_argument("task_dir")
    approve.add_argument("--phase", required=True)
    approve.add_argument("--gate", choices=("requirements", "design", "combined"), required=True)
    approve.add_argument("--by", default="user")
    approve.add_argument("--note")
    approve.set_defaults(function=command_approve)

    add_phase = commands.add_parser("add-phase", help="add a dependent Phase")
    add_phase.add_argument("task_dir")
    add_phase.add_argument("--name", required=True)
    add_phase.add_argument("--phase-id")
    add_phase.add_argument("--parent")
    add_phase.set_defaults(function=command_add_phase)

    event = commands.add_parser("event", help="append a lifecycle evidence event and render")
    event.add_argument("task_dir")
    event.add_argument("--type", required=True)
    event.add_argument("--summary", required=True)
    event.add_argument("--phase")
    event.add_argument("--result")
    event.add_argument("--evidence", action="append")
    event.set_defaults(function=command_event)

    serve = commands.add_parser("serve", help="serve the generated ledger and comment bridge on loopback")
    serve.add_argument("task_dir")
    serve.add_argument("--port", type=int, default=0)
    serve.set_defaults(function=command_serve)
    from workspace_cli import add_commands
    add_commands(commands)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return int(args.function(args))
    except (FileNotFoundError, FileExistsError, OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
