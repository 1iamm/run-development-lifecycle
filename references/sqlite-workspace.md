# Local SQLite workspace (V3)

## Storage and compatibility

The default workspace uses `~/.codex/lifecycle/workspace.sqlite3`. Set `LIFECYCLE_HOME` for a different directory, or pass `--database` to init/import/serve/list/cleanup. Use the same database for concurrent projects. SQLite uses WAL, foreign keys, full synchronous commits and a busy timeout. Update conflicts are explicit revision failures rather than silent overwrites.

Tables: `tasks` holds project/thread bindings and archive state; `documents` holds current task/Phase/comment objects with revisions; `events` holds append-only history; `deliverables` indexes task-local files; `archives` holds retention and retry metadata. The retained Phase JSON schema is version 2; storage version 3 is identified by `.lifecycle-store.json`. Do not confuse storage version with Phase schema version.

Each task has a UUID database key as well as its human DEV ID. Two explicitly imported tasks with coincidentally equal DEV IDs in different directories remain distinct. Import does not infer conversation identity, change approvals, or promote lifecycle state. New CLI tasks use SQLite automatically. V2 remains supported until explicitly imported; V1 HTML is never automatically converted.

SQLite is authoritative for V3. `task.json`, `phases/*.json`, `comments.json`, `events.jsonl` and `index.html` are compatibility/review exports. `resume`, `render` and `checkpoint` refresh them. Direct editing of these exports will not update the database. Review exports and task files stay outside Codex-managed worktrees by default.

Export fingerprints protect changes made by older in-flight agents: rendering or normal updates refuse to overwrite externally edited JSON exports. Preserve the edited file, read the database version, merge the intended changes into a separate input, and use `workspace update --expected-revision` to reconcile explicitly. Never discard such edits merely to get a checkpoint passing.

## Update workflow

```bash
python3 <skill-dir>/scripts/lifecycle.py workspace read <task-dir> --document phases/P1.json
python3 <skill-dir>/scripts/lifecycle.py workspace update <task-dir> --document phases/P1.json --file <prepared-json-input> --expected-revision <returned-revision>
python3 <skill-dir>/scripts/lifecycle.py checkpoint <task-dir> --gate design --phase P1
```

`read` returns `data` and `revision`; the input file contains the `data` object only. Do not read a generated export to obtain a revision. After a conflict, reload the current object and reapply only the intended change. Approvals remain subject to the existing `approve` command and user-confirmation rules; writing data does not authorize bypassing a validator.

Record `workItems` as `[{"id":"DEV-01","title":"...","status":"TODO"}]`, using `DONE` for actually completed items. Prefer Phase-level items for phased tasks; do not duplicate the same items at task and Phase levels. The board uses task-level items if present, otherwise all Phase items. With no declared items, it shows “待拆分子项” rather than manufacturing a percentage.

The board derives stages from lifecycle states. Product covers discovery/requirements review; technical/UI cover requirements-approved/design review; development covers approved design/implementation/fixes; testing covers local verification/E2E; release covers candidate/release/finalization/DONE. Use the separate design-stage hint for technical versus UI when actual work requires it. A hint never advances a gate or marks another stage complete.

## Execution status and user action

The board has three execution labels: **进行中**, **已阻塞**, **已完成**. Only an explicit current wait for the user is **已阻塞**. Research, implementation, debugging, unresolved technical questions, failed tests and parent synchronization remain **进行中** while the agent can continue. Review-stage names, issue severity, open issues and dirty exports do not establish user ownership. Those records stay visible under “问题与检查记录” and continue to affect the original lifecycle gates.

The active Phase stores execution separately from its lifecycle `state`:

```json
{
  "execution": {
    "status": "blocked",
    "summary": "方案已准备完成，等待范围确认后才能实施",
    "requiredAction": "确认是否采用方案 A；评审稿在本任务的技术设计中",
    "updatedAt": "2026-09-10T07:00:00+00:00"
  }
}
```

Use `active` with the current agent work in `summary` and an empty `requiredAction`. Use `blocked` only when the agent has reached a concrete user action or confirmation; both a reason and a specific action are required. Do not mark a future approval as a current wait while independent authorized work continues. `DONE` remains controlled by the existing lifecycle gate, never by this field.

```bash
python3 <skill-dir>/scripts/lifecycle.py workspace read <task-dir> --document phases/P1.json
python3 <skill-dir>/scripts/lifecycle.py workspace activity <task-dir> --phase P1 --status blocked --summary "评审稿已完成，等待范围确认" --required-action "确认技术设计中的方案 A" --expected-revision <returned-revision>
# After the user answers, read the new revision and resume:
python3 <skill-dir>/scripts/lifecycle.py workspace activity <task-dir> --phase P1 --status active --summary "按已确认方案实现并回归" --expected-revision <new-revision>
```

This command changes execution metadata only, preserves approvals/tests/phase state and appends an audit event. It refuses stale revisions and externally edited exports. Keep the record current at turn start/resume, meaningful handoffs, and after a user reply. Do not leave a previous user wait active after work resumes. The board polls SQLite; it is not a live Codex-process monitor. Old tasks without this record show **进行中** with an explicit “尚未登记执行状态” note until their responsible agent reconciles the current work. Never parse arbitrary prose or historical issue lists to invent a user action.

## Project, conversation and deliverables

```bash
python3 <skill-dir>/scripts/lifecycle.py workspace bind <task-dir> --project "项目名称" --project-root <repository> --thread-id <actual-codex-thread-id>
python3 <skill-dir>/scripts/lifecycle.py workspace bind <task-dir> --stage ui
python3 <skill-dir>/scripts/lifecycle.py workspace deliverable <task-dir> --phase P1 --kind ui --title "交互原型" --path <task-dir>/deliverables/ui/index.html --version v0.3
```

Kinds: `product`, `technical`, `ui`, `development`, `testing`, `release`. Registered files must reside under the task's `deliverables/` or `evidence/`; don't index arbitrary repository or home-directory files. Registration records the version and appends an event. The board exposes independent document pages, while task details remain in the board. Markdown/text/JSON render as escaped content, images render directly, and self-contained HTML prototypes run in an iframe without same-origin access. Prototype assets should be inline; remote resources and arbitrary network access are disabled. Other file types can be downloaded.

Use [html-deliverables.md](html-deliverables.md) for the shared HTML structure and portable technical/release field mapping. `workspace document <task-dir> --kind technical --phase P1 --version v0.1` exports and registers a self-contained version snapshot without overwriting prior versions.

Each Phase may have `releaseChecklist` entries with `id/title/checked`. The independent release page saves manual checks and records who checked and when. A checkbox is a user attestation, not an application deployment or gate approval. It does not change `DONE`, test evidence or candidate SHAs.

The native link format `codex://threads/<threadId>` was verified in the installed desktop app on 2026-09-10. Binding with `workspace bind --thread-id` verifies that Codex can read that exact ID. Do not invent IDs or bind by matching a title. When `init` receives the current `CODEX_THREAD_ID`, it records that explicit identity; no other conversations are searched or created.

If the user explicitly starts a new lifecycle task in the same conversation, use `init --transfer-thread` (or `workspace bind --transfer-thread`) to move the active binding. The old task remains unchanged in its lifecycle state and keeps an audit event containing the historical conversation ID. Do not use this option to resolve an ambiguous task identity.

## Manual archive and retention

1. Every lifecycle stage may be archived; completion alone never triggers archive. The user clicks **归档任务与对话** when ready. CLI archive is only for an explicit user request: `workspace archive <task-dir> --user-requested`.
2. Ensure a local Codex binding and lock the task against updates while archiving. Do not require DONE or run the completion gate; preserve the actual task/Phase state, unfinished work, blockers, failed tests and approvals.
3. Export and copy task/Phase/comment/event records, generated review HTML, evidence and registered deliverables to `archives/<archive-uuid>/`. Copy only these task-owned directories, reject symlinks, and verify a checksum manifest. Record minimal conversation metadata; do not duplicate raw command outputs, authentication material or entire Codex rollout history.
4. Read and archive the bound conversation through the local Codex App Server, then verify it appears in the archived list. Only then remove the task from the active board. Codex may also archive that conversation's spawned descendants according to its native behavior.
5. On timeout, keep the snapshot and show an uncertain state. Retry first checks whether Codex already archived it; it does not blindly repeat the mutation. Interrupted operations are reconciled after service restart. A currently running Codex turn remains unarchived until it stops. Missing completion evidence does not prevent manual archive.
6. Expiry is 30 days after verified archive completion. Cleanup deletes only the owned archive UUID directory whose manifest matches the database record. Original task/project files, database state/history/index and the Codex archived conversation remain. “本地副本已清理” never means the original source documents or Codex conversation were deleted.

Local Codex integration uses `codex app-server --stdio`, `initialize`, `thread/read`, `thread/list` and `thread/archive`. It never modifies Codex's SQLite or JSONL files directly, starts turns, creates conversations, requests model completions, or calls `thread/delete`. Set `LIFECYCLE_CODEX_BIN` when the installed Codex executable is not on PATH. Remote-host conversations are not silently redirected to the local host; archive reports unsupported until an appropriate adapter exists.

Official protocol reference: [Codex App Server](https://learn.chatgpt.com/docs/app-server). Generated protocol schemas from the installed CLI were checked on 2026-09-10.

## Running and maintaining the local service

```bash
python3 <skill-dir>/scripts/lifecycle.py workspace serve --port 8765
python3 <skill-dir>/scripts/lifecycle.py workspace list
python3 <skill-dir>/scripts/lifecycle.py workspace cleanup
python3 <skill-dir>/scripts/lifecycle.py workspace backup --output <new-database-backup-file>
```

The service binds `127.0.0.1` only. The board refreshes every five seconds; errors keep the last view visibly stale. Writes require a same-origin JSON request and a per-process CSRF token. No external server, third-party database or JavaScript dependency is required.

Cleanup runs on service startup and every 60 seconds while running. A sleeping, powered-off computer or stopped service performs overdue cleanup on the next start. There is no claim of an OS background job unless separately installed. `backup` uses SQLite's consistent backup API, never a raw copy of a live WAL database. Original document files need their own file backup; do not make indefinite backups of expiring archive copies.

Import an explicitly identified existing V2 task with `workspace import <task-dir> --project <name> --project-root <path>`. All source documents and history are imported in one database transaction; adding the task's storage marker is recoverable and import is idempotent. Keep a pre-upgrade skill backup and validate both the legacy test suite and SQLite/HTTP/retention tests before installing changes.
