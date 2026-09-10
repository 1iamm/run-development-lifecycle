---
name: run-development-lifecycle
description: Run or resume a structured development lifecycle with a local SQLite multi-project board, linked deliverables and Codex conversations, manual archive, Phase-aware gates, delivery, E2E and evidence. Use when the user invokes $run-development-lifecycle, references an existing DEV task/ledger, or explicitly asks for this lifecycle workspace. Do not activate for unrelated ordinary coding or deployment requests.
---

# Run Development Lifecycle

Run traceable tasks across projects in a local workspace. New tasks use SQLite as their source of truth; JSON and HTML are generated review exports. PRD, technical documents, UI prototypes, test evidence and release resources remain local files. Preserve existing lifecycle gates and append-only evidence.

## Host compatibility

Requires Python 3.10+ with SQLite. The core workspace and HTML export use only the Python standard library. Any agent with filesystem and shell access can follow this file. Native conversation links and coupled archive require local Codex App Server and a real bound Codex thread; do not fabricate bindings for other hosts. See [README.md](README.md) for installation and [docs/agent-quickstart.md](docs/agent-quickstart.md) for a command-driven walkthrough.

## Workspace entry

- Open the shared board with `python3 <skill-dir>/scripts/lifecycle.py workspace serve`. It listens only on `127.0.0.1`; open the returned URL with the browser available in the current agent host. The default database is `~/.codex/lifecycle/workspace.sqlite3`, or `$LIFECYCLE_HOME/workspace.sqlite3` when configured.
- The board has **产品 / 技术 / UI / 开发 / 测试 / 上线** columns and an all-task table. Cards show projects and current phases; task details expand in place. Deliverables open independent pages. Actual Codex conversations use the bound thread ID, never a title match.
- Board **已阻塞** means the current next step requires the user to act or confirm. Agent research, implementation, debugging, test failures and pending technical decisions remain **进行中** while the agent can continue. Keep the active Phase `execution` record current when starting/resuming, handing work back, or receiving a user answer; use `workspace activity` as documented in [references/sqlite-workspace.md](references/sqlite-workspace.md). A blocked record must explain why and exactly what the user needs to do. Never infer user waiting from an issue severity or a review-stage name.
- A board stage is a presentation of lifecycle state, not a replacement approval gate. Use `workspace bind --stage technical|ui` to distinguish those two design activities when needed; it does not approve design or advance implementation.
- Read [references/sqlite-workspace.md](references/sqlite-workspace.md) for database updates, project/thread bindings, deliverables, imports, archive/retention, local service operation or troubleshooting.
- Task completion does **not** archive the task or Codex conversation. Only the user's archive button or explicit archive request authorizes archive. Any lifecycle stage may be manually archived; archive does not imply completion and must preserve its current state, unfinished work and failed evidence.
- Initializing/updating the local workspace database, registering deliverables and maintaining its metadata are ordinary lifecycle bookkeeping authorized by the lifecycle request. Do not confuse this with business-database SQL, schema migration or deployment approvals.

## Dispatch cheaply

1. Classify the request as **new task** or **resume** before locating or opening any ledger. Resume only when the user supplies a task ID/path/ledger, or explicitly refers to the lifecycle task already bound in this conversation. Same repository, business domain, feature, or a similar title is not identity evidence.
2. A request described as new, another requirement, or a separate piece of work creates a new task and a new HTML. Do not search for a similar historical ledger, reuse the last task found in the workspace, or add a Phase to avoid creating a task. Add a Phase only when the user explicitly scopes the work as a later Phase of an identified task with shared delivery lineage.
3. For a new task, run `init` first under the date-level task root and use only the returned `taskDir` for subsequent writes. Never pass an existing task directory as `--root`, and never edit an old `index.html` while initializing a new task.
4. For a resume, locate the identified task directory. `.lifecycle-store.json` means SQLite-backed V3; `task.json` alone means V2; an `index.html` without `task.json` means legacy V1. If identity is ambiguous and choosing wrong would mutate an old task, ask one targeted identity question before writing.
5. Resolve `<skill-dir>` from the loaded `SKILL.md`; commands must use `python3 <skill-dir>/scripts/lifecycle.py` so they work from any repository. For V2/V3 continuation, first run `resume <task-dir>`; for V3 this refreshes review exports from SQLite. Read only the returned files. Never reconstruct state from generated HTML, and never edit V3 JSON exports as the write target.
6. Read [references/conversation-protocol.md](references/conversation-protocol.md) for new, resumed, requirement, or design work.
7. Read [references/v2-architecture.md](references/v2-architecture.md) for the retained Phase model, validator schema and generated review format; read [references/sqlite-workspace.md](references/sqlite-workspace.md) for V3 storage and CLI changes. Read [references/design-deliverables-v2.md](references/design-deliverables-v2.md) only while preparing or validating design.
8. Read [references/state-machine.md](references/state-machine.md) only for a state transition or gate dispute; [references/comments.md](references/comments.md) only when comments are involved; [references/phased-delivery.md](references/phased-delivery.md) only for multiple Phases or parent drift; [references/design-expert-gates.md](references/design-expert-gates.md) only for user-visible UI work; [references/git-and-openspec.md](references/git-and-openspec.md) before repository mutation; and [references/deployment-validation.md](references/deployment-validation.md) before push, deployment, browser E2E, or observability queries.
9. For V1, load the legacy [references/ledger-contract.md](references/ledger-contract.md) and [references/design-deliverables.md](references/design-deliverables.md), continue with `validate_ledger.py`, and never overwrite it with V2 unless the user explicitly requests migration.

## Preserve the hard boundaries

- Keep at most one task bound as the active lifecycle task in a conversation. Binding makes explicit continuation convenient; it does not turn a newly stated requirement into a Phase or authorize reuse of the bound task. When a new task is initialized, bind the conversation to the new returned task ID/path and leave the old task unchanged.
- Use read-only research worktrees; preserve the user's checkout and dirty changes. Create business branches, OpenSpec, commits, pushes, deployments, SQL execution, or other mutations only at the corresponding approved boundary.
- Advance gates from explicit evidence and explicit user confirmation. Silence is not approval. `checkpoint` validates and records attempts; only run `lifecycle.py approve` after the user actually confirms.
- Append decisions, failures, deployments, tests, fixes, and supersession events. Never erase a failed record or invent facts, SHAs, hosts, SQL, screenshots, results, or approvals.
- Follow the target repository's verified default or explicitly chosen base branch; never hard-code main/master/develop. Preserve exact parent candidate SHAs for later Phases and mark parent drift `STALE_PARENT`. Read [references/git-and-openspec.md](references/git-and-openspec.md) for repository isolation and project-specific delivery rules.
- Keep secrets and sensitive business data out of task files, evidence, screenshots, logs, and repositories.
- Use the current agent host's available, authorized browser and deployment/log tools. Respect explicit browser preferences. Missing optional tools must not block local task/document work; report unavailable external validation accurately.
- Never infer credentials or another person's account. Passwords, OTPs, QR approvals and security keys are user-entered and never stored in task evidence.
- Keep gate risk and review density independent. Let V2 render simple tasks compactly and grow to structured/deep views only from actual Phase, repository, data/flow, deployment, comment, issue, and history complexity; never hide blockers, failures, stale lineage, or superseded facts.

## Run the lifecycle

### Start or resume

- New task: initialize immediately with available context:

  ```bash
  python3 <skill-dir>/scripts/lifecycle.py init --title "<title>" --root <task-root> --project "<project-name>" --project-root <repository> --profile STANDARD
  ```

  Here `<task-root>` is the date-level parent such as `.../dev-tasks/YYYY-MM-DD`, never a directory that already contains `task.json` or `index.html`. Treat the command's returned `taskDir`, `taskId`, and `ledger` as the write boundary for this task.

- `init` defaults to SQLite and returns `database` and `taskKey` too. Bind the current conversation using its actual `CODEX_THREAD_ID` when available, or an ID obtained from the Codex task tools. Never select a different conversation by repository or semantic similarity. Keep each active conversation bound to at most one lifecycle task; when starting another task in the same conversation, explicitly transfer the binding without archiving the prior task.

- Use `FAST` only for a single-repository reversible local change with no public-contract, data, auth, payment, or deployment risk. `STANDARD` is the default. The CLI automatically treats multi-Phase, payment, auth, schema/data migration, public-contract, irreversible, and external-deployment work as `STRICT`.
- Inspect authorized sources before asking questions. Populate observed facts and assumptions, then send one decision pack containing all current blockers, at most three grouped decisions, each with a recommendation.
- Continue through safe discovery, JSON updates, rendering, and gate checks without stopping after every artifact.

### Requirements and design

- For V3, read the current structured document with `workspace read`, prepare a JSON input outside the generated exports, and save it with `workspace update --expected-revision`. SQLite commits the update and refreshes the JSON/HTML review exports. Re-read and merge when a revision conflict occurs. V2 continues using its original JSON write flow.
- For PRD and technical design, follow [references/visual-narrative.md](references/visual-narrative.md): use conclusion → diagram/table detail → decisions/acceptance/risks both across the document and within every module. Prefer rendered Mermaid/PlantUML/SVG for relationships and tables for exact requirements, interfaces and test mappings; minimize long prose and retain diagram source files.
- Read [references/html-deliverables.md](references/html-deliverables.md) when preparing PRD, technical, UI, testing or release documents. Use the shared HTML format; technical and release sections use the documented reusable structures. Render current views from SQLite and export versioned HTML with `workspace document` for review milestones. Keep UI prototypes as separately registered self-contained HTML.
- Keep raw evidence under `evidence/`; put standalone deliverables under `deliverables/` and register them with `workspace deliverable`. Record product, technical, UI, development, testing and release deliverables as applicable. A structured record is not proof that a UI prototype file or test run exists.
- Maintain actual `workItems` (`id/title/status`) in the task or active Phase for progress. The workspace derives percentages from these declared items; do not invent percentages from elapsed time or guess completed work. Keep test failures and re-runs as separate evidence events.
- `FAST` and `STANDARD` normally present requirements and design together for one explicit combined confirmation. Separate them only when unresolved product decisions would invalidate the design. `STRICT` keeps separate confirmations.
- Collaboration mode is not a lifecycle gate. Do not ask the user to switch between Plan and Default; the lifecycle state itself forbids business-repository mutation before design approval.
- Run one checkpoint after the full review candidate is ready:

  ```bash
  python3 <skill-dir>/scripts/lifecycle.py checkpoint <task-dir> --gate requirements --phase P1
  python3 <skill-dir>/scripts/lifecycle.py checkpoint <task-dir> --gate design --phase P1
  ```

- After explicit confirmation, record it with `approve --gate requirements|design|combined`. Do not use confirmation to waive validator failures.

### Implement, deliver, and finish

- Before repository work, follow `git-and-openspec.md`. Create the Phase branch/worktree after design approval; use OpenSpec only when the target project already uses it.
- Keep implementation and fixes on the current task branch. Use the project's existing review and CI/CD process; do not require a particular deployment vendor or specification tool.
- Update structured current state at meaningful checkpoints, append evidence events, and regenerate HTML with `lifecycle.py checkpoint` instead of editing `index.html`. SQLite-backed updates automatically appear in the board; do not maintain a second manual board ledger.
- Before external delivery, prepare the exact component, candidate, target and rollback details. Reuse existing authorization when it covers the unchanged action, and account for automatic deployment triggered by push/merge.
- Use available browser and observability tools for applicable E2E; preserve failures and add regression records.
- `DONE` requires applicable tests/evidence, resolved or accepted deferrals, final SHAs, release/rollback facts, archived OpenSpec when applicable, and a passing `checkpoint --gate done`.

## Commands

| Intent | Command |
|---|---|
| Multi-turn resume pack | `python3 <skill-dir>/scripts/lifecycle.py resume <task-dir>` |
| Compact status | `python3 <skill-dir>/scripts/lifecycle.py status <task-dir> --format json` |
| Sync comments without a gate | `python3 <skill-dir>/scripts/lifecycle.py sync-comments <task-dir>` |
| Add Phase | `python3 <skill-dir>/scripts/lifecycle.py add-phase <task-dir> --name "..." --parent P1` |
| Validate/checkpoint/approve | `python3 <skill-dir>/scripts/lifecycle.py <validate|checkpoint|approve> ...` |
| Append event/render/serve | `python3 <skill-dir>/scripts/lifecycle.py <event|render|serve> ...` |
| Open the multi-project workspace | `python3 <skill-dir>/scripts/lifecycle.py workspace serve` |
| Record current work or user wait | `python3 <skill-dir>/scripts/lifecycle.py workspace activity <task-dir> --phase <active-phase> --status <active-or-blocked> --summary "..." --expected-revision <revision> [--required-action "..."]` |
| Read/update SQLite state | `python3 <skill-dir>/scripts/lifecycle.py workspace <read|update> <task-dir> ...` |
| Bind project, conversation or design stage | `python3 <skill-dir>/scripts/lifecycle.py workspace bind <task-dir> ...` |
| Export and register a versioned HTML document | `python3 <skill-dir>/scripts/lifecycle.py workspace document <task-dir> --kind technical --phase P1 --version v0.1` |
| Register a deliverable | `python3 <skill-dir>/scripts/lifecycle.py workspace deliverable <task-dir> ...` |
| Import one identified V2 task | `python3 <skill-dir>/scripts/lifecycle.py workspace import <task-dir> ...` |

## Response cadence

Give the full task/Phase/state/update/blocker/next-action block only when a gate or state changes, a blocker appears or clears, the user asks for status, or work is handed back. Use short commentary during uninterrupted work and never repeat unchanged commands or facts.

Keep tasks visible until the user manually archives them, at any lifecycle stage. Archiving does not run the DONE gate or change lifecycle states, approvals, pending items, or test results. Save and verify a local copy of the current state, then archive the bound local Codex conversation using app-server. A currently running turn must stop before archiving; an unfinished lifecycle task is allowed. Failure remains visible and retryable; do not claim success from a timeout. Keep local archive copies for 30 days, then delete only those copies. Retain original task/project files, the database index/audit and Codex's archived conversation. Cleanup runs while the workspace service is running and catches up on its next start. Never call Codex delete or delete project/worktree sources as part of retention.
