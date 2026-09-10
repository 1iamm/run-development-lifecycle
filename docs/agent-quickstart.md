# Agent quickstart

Read the installed `SKILL.md` first. The commands below demonstrate storage and document operations; they do not grant approval to change a business repository, deploy software, or archive real conversations.

## 1. Locate and verify the installation

Clone `https://github.com/1iamm/run-development-lifecycle.git` into the host's actual skill directory or a persistent directory explicitly selected by the user. Keep the entire repository together. If the destination exists, inspect its source and local changes before updating it.

For the Codex install example:

```bash
skill_dir="${CODEX_HOME:-$HOME/.codex}/skills/run-development-lifecycle"
python3 "$skill_dir/scripts/lifecycle.py" --help
python3 -c 'import sys, sqlite3; print(sys.version); print(sqlite3.sqlite_version)'
```

Requires Python 3.10+ with standard-library SQLite. No dependency installation is required for the workspace. Browser automation, diagram renderers, deployment tools and Codex integration are optional host capabilities; do not invent them when unavailable.

## 2. Verify with temporary data

Run the included tests from the installation directory:

```bash
cd "$skill_dir"
python3 -m unittest discover -s tests -v
```

Tests create temporary SQLite databases and use a fake Codex adapter. They never need to archive a real Codex conversation. Local HTTP tests need loopback socket permission; follow the host's permission process if sandboxing blocks them.

Do not use the user's production task database for an installation demonstration.

## 3. Start a real task

First decide whether the request means a **new task** or continuation of an explicitly identified existing task. Similar titles/repositories are not identity evidence.

Replace the project path with the actual authorized checkout; choose a date-level task root outside both the repository and any managed worktree:

```bash
python3 "$skill_dir/scripts/lifecycle.py" init \
  --title "Describe the actual requirement" \
  --project "Actual project name" \
  --project-root /absolute/path/to/project \
  --root "$HOME/Documents/Codex/dev-tasks/$(date +%F)" \
  --profile STANDARD
```

`init` returns `taskDir`, `taskId`, `ledger`, `database` and `taskKey`. Use the returned `taskDir` for all later writes, never a guessed directory. New tasks default to SQLite.

In Codex, `CODEX_THREAD_ID` supplies the current actual conversation identity when available. Outside Codex, leave the binding empty. Never fabricate a UUID or select another conversation from a similar title. Creating tasks does not create Codex conversations.

A shared board means every project uses the same `LIFECYCLE_HOME`/database. Runtime data is separate from the installation directory. The default database is `~/.codex/lifecycle/workspace.sqlite3`; set `LIFECYCLE_HOME` consistently in all sessions to change it.

## 4. Resume and read

```bash
python3 "$skill_dir/scripts/lifecycle.py" resume /absolute/returned/taskDir
python3 "$skill_dir/scripts/lifecycle.py" workspace read /absolute/returned/taskDir \
  --document phases/P1.json
```

`workspace read` returns `{document, revision, data}`. Resume reports current state, blockers, recommended Phase and the next checks. Read current SQLite-backed state, not generated HTML or stale JSON exports.

## 5. Update with optimistic concurrency

Prepare a **separate JSON input file** containing only the updated `data` object. Preserve unrelated fields. Include discovered facts and actual evidence, not estimates or fabricated approvals.

```bash
python3 "$skill_dir/scripts/lifecycle.py" workspace update /absolute/returned/taskDir \
  --document phases/P1.json \
  --file /absolute/path/to/prepared-phase-input.json \
  --expected-revision 3
```

`3` is an example; use the exact revision returned by your latest read. If another agent changed the record, read again and merge only your intended changes. The command refreshes review exports.

If an older agent edited generated JSON externally, preserve those changes and reconcile them explicitly into a new input. Never delete the edited file to force a refresh.

Progress comes from `workItems`, for example:

```json
[{"id":"DEV-01","title":"Implement the approved API","status":"TODO"}]
```

Use `DONE` only after the actual item is complete. Do not duplicate the same work at both task and Phase level. Missing work items produce an unknown progress indicator.

Before starting/resuming work and whenever handing it back, record the active Phase's current execution ownership. A failed test or open issue does not mean the user must act:

```bash
python3 "$skill_dir/scripts/lifecycle.py" workspace activity /absolute/returned/taskDir \
  --phase P1 --status active --summary "Implementing the approved API and running regression tests" \
  --expected-revision 4
```

Use the latest revision, not the example `4`. When waiting for the user, use `--status blocked`, a reason in `--summary`, and a concrete `--required-action`. After the user replies, record `active` again, which clears the old required action. Only these explicit user waits show **已阻塞**. The board reads recorded state, not live process activity. See [execution status](../references/sqlite-workspace.md#execution-status-and-user-action) for the full contract.

## 6. Prepare, validate and approve

Populate scope, requirements, applicable artifacts and planned tests. Follow the documented risk profile and the [visual narrative rules](../references/visual-narrative.md): PRD and technical documents use conclusion → diagram/table detail → decision/acceptance/risk, both overall and inside each module.

```bash
python3 "$skill_dir/scripts/lifecycle.py" checkpoint /absolute/returned/taskDir \
  --gate requirements --phase P1
python3 "$skill_dir/scripts/lifecycle.py" checkpoint /absolute/returned/taskDir \
  --gate design --phase P1
```

Checkpoint validates and records the attempt. It does not supply user approval. Only after the user actually confirms the applicable review:

```bash
python3 "$skill_dir/scripts/lifecycle.py" approve /absolute/returned/taskDir \
  --gate combined --phase P1 --by user
```

FAST/STANDARD normally accept one combined requirements/design confirmation; STRICT keeps them separate. Observe the skill's gates and the project's own instructions. Missing optional OpenSpec or vendor deployment tooling must not block ordinary local task bookkeeping.

## 7. Deliver HTML and diagrams

Standard HTML snapshot from current structured records:

```bash
python3 "$skill_dir/scripts/lifecycle.py" workspace document /absolute/returned/taskDir \
  --phase P1 --kind product --version v0.1
python3 "$skill_dir/scripts/lifecycle.py" workspace document /absolute/returned/taskDir \
  --phase P1 --kind technical --version v0.1
```

The exporter creates and registers `deliverables/P1/<kind>/<version>.html`. Existing versions are never overwritten. Empty inputs remain visibly incomplete; export is not a design or quality approval.

For a diagram-rich PRD, technical document or interactive UI prototype, create a self-contained HTML file under the task's `deliverables/` or `evidence/`. Render Mermaid/PlantUML using available authorized tools, embed the visible result, retain editable sources, and register the HTML:

```bash
python3 "$skill_dir/scripts/lifecycle.py" workspace deliverable /absolute/returned/taskDir \
  --phase P1 --kind technical --title "Technical design with diagrams" \
  --path /absolute/returned/taskDir/deliverables/technical-v0.2.html --version v0.2
```

Kinds: `product`, `technical`, `ui`, `development`, `testing`, `release`. HTML runs in a sandbox and cannot load remote assets; inline its CSS/JS/images. Register the actual interactive prototype separately from its explanatory document. See [HTML format](../references/html-deliverables.md) for fields and resource tables.

## 8. Open the shared board

```bash
python3 "$skill_dir/scripts/lifecycle.py" workspace serve --port 8765
```

Open the returned loopback URL with the host's available browser. Keep the service process alive. One instance serves all projects in the database. An existing instance at the same port/database is reused. Restarting the computer preserves data; rerun this command to start the service again. No autostart is installed.

The service binds only to `127.0.0.1`. Do not expose it as a multi-user Internet service; remote hosting and authentication are outside this local workspace's implementation.

## 9. Bind Codex only when supported

If `init` did not get the current real ID, obtain it from the current Codex host's task tools and verify the exact binding:

```bash
python3 "$skill_dir/scripts/lifecycle.py" workspace bind /absolute/returned/taskDir \
  --thread-id ACTUAL-CODEX-THREAD-ID
```

This command verifies that local Codex can read that ID. The native URI is `codex://threads/<id>`. Use `LIFECYCLE_CODEX_BIN` if the actual Codex executable is not on PATH. Other agents can use the core workspace without a Codex binding; their native conversations are not supported by this archive adapter.

At most one active lifecycle task is bound to a Codex conversation. Use `--transfer-thread` only when the user explicitly starts a new task in that same conversation, not to resolve ambiguous identity.

## 10. Manual archive and retention

Only the user's archive button or explicit archive request authorizes archive. Any lifecycle stage is allowed; DONE is not required. Do not archive automatically after completion.

For an explicit user archive request only:

```bash
python3 "$skill_dir/scripts/lifecycle.py" workspace archive /absolute/returned/taskDir \
  --user-requested
```

A real local Codex binding is required. If its current turn is running, wait for it to stop. The archive keeps current states, failures and unfinished items, creates and verifies a local snapshot, calls Codex archive, then checks the result. On uncertainty, retain the snapshot and retry to reconcile; do not claim success from a timeout.

The snapshot is retained for 30 days. Service startup and its periodic cleanup delete only expired owned archive copies; original task/project files, SQLite metadata/audit and Codex's archived conversation remain. This is not a full Codex transcript export.

## 11. Existing data and upgrades

Import an explicitly identified V2 JSON task without changing its lifecycle state:

```bash
python3 "$skill_dir/scripts/lifecycle.py" workspace import /absolute/existing/taskDir \
  --project "Actual project" --project-root /absolute/project
```

V1 HTML tasks have a separate legacy validator and are not automatically migrated. Keep task identity explicit.

Before updating this installation, inspect its Git status and origin, then use `git pull --ff-only` when appropriate. Restart the local service after a code update. Never include databases, real task files, private evidence or credentials in a skill source commit.
