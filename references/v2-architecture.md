# V2 structured lifecycle architecture

Storage note: new tasks now use the [V3 SQLite workspace](sqlite-workspace.md). This document describes the retained Phase schema and legacy V2 file-authority behavior. For a task with `.lifecycle-store.json`, SQLite is authoritative and the JSON/HTML files below are generated review exports.

## Purpose

V2 keeps the lifecycle traceable while removing the need to read or edit a large generated HTML file. Structured files are authoritative; `index.html` is a reproducible, offline review snapshot.

## Task directory

```text
<task>/
├── task.json
├── phases/
│   ├── P1.json
│   └── P2.json
├── events.jsonl
├── comments.json
├── evidence/
└── index.html
```

- `task.json`: task metadata, profile, overall state, active Phase, Phase index, repositories, blockers, next action, and global integration state.
- `phases/<id>.json`: the current effective requirement, design, branch, release, validation, and issue state for one Phase.
- `events.jsonl`: append-only decisions, approvals, state changes, failures, deployments, tests, fixes, and supersession events.
- `comments.json`: comments already merged into the durable task record.
- `index.html`: generated from the files above. Never edit it as the V2 source of truth.

Historical evidence remains append-only in `events.jsonl`; current effective state remains compact in JSON. A superseding event points to the earlier event ID instead of deleting it.

## Task identity and initialization

A task directory is an immutable identity boundary. New work receives a new `DEV-YYYYMMDD-NNN` directory even when it shares a repository or business area with an older task. Existing directories are resumed only from explicit identity evidence; recency and semantic similarity do not select a write target.

`lifecycle.py init --root` accepts a date-level parent directory, not an existing V1 or V2 task directory. After initialization, callers must use the returned `taskDir` for every update and render. `index.html` is never copied forward or used as the source for a new task.

## Profiles and automatic escalation

Profiles control documentation depth, not safety authorization.

| Profile | Intended use | Default gate shape |
|---|---|---|
| `FAST` | One repository, reversible local change, no public contract/data/security/deployment impact | Combined requirement and design review |
| `STANDARD` | Ordinary product or service development | Combined review unless unresolved product decisions require separation |
| `STRICT` | Multi-Phase, payment, auth, schema/data migration, public contract, irreversible operation, or external deployment | Separate requirement, design, and deployment approval |

Automatically promote to `STRICT` when any Phase has a true risk signal among `multiPhase`, `payment`, `auth`, `schemaChange`, `dataMigration`, `publicContract`, `irreversible`, or `externalDeploy`. Do not silently downgrade an automatically promoted task.

## Phase source model

Every Phase includes:

- scope: current behavior, goals, non-goals, evidence, assumptions, and blocking decisions;
- requirements: stable ID, statement, acceptance criteria, status, and evidence;
- applicability: UI, data, async, public contract, deployment, and other risk signals;
- artifacts: compact structured records for functional, application/code/data architecture, domain/persistence, state/flows, impact, branch, release, validation, and traceability;
- approvals: requirement and design approval records when required by profile;
- branch: parent Phase, parent candidate SHA, base/head/candidate SHA, and sync status;
- releases, tests, issues, and evidence links.

Use stable objects for decisions instead of free-text reminders: `id / question / recommended / status / answer / answerSource / answeredAt`. `resume` asks only open decisions and assigns compatibility IDs to legacy strings. Prefer typed evidence objects with `type / source / observedAt / ref / sha / path-or-url / scope`; existing string evidence remains readable for backward compatibility.

An artifact status is `pending`, `complete`, `unchanged`, `not-applicable`, or `superseded`.

- `complete` requires evidence.
- `unchanged` requires a concise current-state summary, unchanged constraints, and evidence.
- `not-applicable` is allowed only when the applicability model proves the feature is outside the Phase scope.
- `pending` blocks only a gate that requires that artifact.

## Risk-aware artifact requirements

All profiles require scope, requirements, functional behavior, code impact, test plan, and traceability.

- Application/code architecture is required when runtime code changes.
- UI design is required only for user-visible UI changes.
- Data architecture, domain model, ER model, and data inventory are required for new/changed persistence or when existing data constraints materially govern behavior. An evidenced `unchanged` record is sufficient when data is read but not changed.
- State machine and recovery flow are required for asynchronous, retryable, multi-state, payment, or externally coordinated behavior.
- Release inventory is required for deployment, configuration, DDL, messages, scheduled jobs, permissions, or external resources.
- The fixed impact categories remain available, but the HTML groups them and shows only impacted or unresolved rows by default.

## Generated HTML

Gate profile and render density are independent. `FAST/STANDARD/STRICT` controls documentation and approval depth; `AUTO → COMPACT/STRUCTURED/DEEP` controls only presentation. AUTO derives the view from actual Phase/repository count, applicable data/flow/deployment work, requirements, comments, issues, and event history. A high-risk but small task may remain compact; a multi-Phase task becomes deep.

The generated page keeps stable anchors and offline/print support, but renders a small initial DOM:

1. sticky task header and four primary facts: state, recommended Phase/gate, candidate version, and task version;
2. blockers or one derived next action before secondary metrics;
3. applicable Phase content grouped into `需求与决策 / 系统方案 / 流程与状态 / 数据与领域 / 研发影响 / 发布与验证 / 证据与历史`;
4. DEEP adds recent changes and a cross-Phase integration view; historical Phases, long tables, and complete events remain on demand;
5. directory links open the containing group before scrolling; print renders every applicable group expanded.

COMPACT omits empty modules and history navigation. STRUCTURED keeps applicable groups with progressive disclosure. DEEP adds Phase/integration lineage, current-versus-history separation, and recent change focus without pre-rendering every Phase. All modes always expose blockers, failures, `STALE_PARENT`, and the current recommended action.

The generated HTML embeds a snapshot of structured data and comments. It never becomes the V2 write target.

## Unified command

Resolve `<skill-dir>` from the loaded skill and use its script from any working directory:

```bash
python3 <skill-dir>/scripts/lifecycle.py init --title "..." --root <task-root>
python3 <skill-dir>/scripts/lifecycle.py resume <task-dir>
python3 <skill-dir>/scripts/lifecycle.py sync-comments <task-dir>
python3 <skill-dir>/scripts/lifecycle.py validate <task-dir> --gate design --phase P1
python3 <skill-dir>/scripts/lifecycle.py checkpoint <task-dir> --gate design --phase P1
python3 <skill-dir>/scripts/lifecycle.py approve <task-dir> --phase P1 --gate combined
python3 <skill-dir>/scripts/lifecycle.py event <task-dir> --type test --summary "..." --phase P1 --evidence <path>
python3 <skill-dir>/scripts/lifecycle.py render <task-dir>
python3 <skill-dir>/scripts/lifecycle.py serve <task-dir>
```

`checkpoint` merges bridge-pending comments, validates the requested gate, appends a success or failure event, updates derived metadata, and regenerates HTML in one command.
`resume` returns the first actionable Phase/gate, all Phase blockers, open decisions, comment counts, lineage, refresh requirements, recent events, and the minimal files to read. `sync-comments` merges browser-pending comments without manufacturing a gate attempt.

## V1 compatibility

If a task has only `index.html` and no `task.json`, it is V1. Continue it with `validate_ledger.py` and the legacy HTML contract unless the user explicitly selects migration. Never replace an existing V1 ledger during V2 initialization.
