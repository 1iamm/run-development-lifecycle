# Low-friction conversation protocol

## Default behavior

Continue autonomously through read-only discovery, structured task updates, rendering, and validation until the next real approval boundary. Do not stop after creating a ledger, completing one artifact, running one command, or making a non-blocking assumption.

Ask only when the answer:

- cannot be discovered from authorized repositories, task files, linked internal documents, deployment metadata, or existing browser state;
- would materially change user-visible behavior, data ownership, compatibility, security, delivery target, or an irreversible action; and
- has no safe reversible default.

Record other unknowns as explicit assumptions with source, confidence, and validation plan.

## Decision packs

Never drip questions across turns when the blockers are already known. Present one decision pack with at most three grouped decisions:

```text
需要你确认（3 项）：
1. <decision> — 推荐：<option>；影响：<short impact>
2. ...
3. ...

其余信息已从 <sources> 获取；若采用推荐项，可回复“按推荐继续”。
```

Each item contains the recommendation and consequence. Do not ask for repository paths, current behavior, appkeys, or test entrypoints when they are discoverable.
Persist every blocking item with a stable decision ID and status; do not re-ask an answered decision unless its upstream facts changed or it was explicitly reopened.

## Approval consolidation

- `FAST`: present requirement and design together and accept one explicit combined confirmation.
- `STANDARD`: default to one combined confirmation; separate them only when unresolved product decisions would invalidate the design.
- `STRICT`: keep separate requirement and design confirmations.
- Do not require switching between Plan and Default mode. The lifecycle state itself prevents repository mutation before design approval.
- External push, deployment, SQL execution, data migration, deletion, production action, or other material mutation still requires the applicable explicit authorization.
- Ask for deployment target, component, exact SHA, and rollback point together only when ready to execute. After the user confirms that complete packet, execute without a duplicate confirmation unless facts changed or the active browser policy requires an action-time confirmation.

## Response cadence

Send a full lifecycle status block only when:

- a state or gate changes;
- a blocker appears or clears;
- the user asks for status; or
- work is being handed back to the user.

During uninterrupted work, send short progress commentary no more often than useful and no less often than required by the host. Do not repeat unchanged commands or ledger facts.

## Start and resume

Resolve task identity before reading a ledger:

- Resume only from an explicit task ID, task directory, ledger path, or an unambiguous reference to the lifecycle task already bound in this conversation.
- Repository overlap, domain overlap, similar wording, and the most recently modified ledger are discovery hints, not identity evidence.
- “新需求”, “另一个需求”, or separately scoped work starts a new task even when it touches the same code. Initialize it under the date-level root, then bind all writes to the returned `taskDir`.
- Add a Phase only when the user identifies the parent task and says the work is a later Phase or shared-lineage continuation. A Phase is not a substitute for a new task.
- If the request could plausibly mean either resume or new task and a wrong choice would modify existing records, ask one identity question before any write. Continue safe repository discovery while waiting when useful.

For a new task:

1. initialize a SQLite-backed task immediately with the context already provided;
2. use the newly returned task ID and directory exclusively; do not open a similar old ledger as the write target;
3. inspect authorized sources before asking questions;
4. populate observed facts, assumptions, and evidence;
5. ask one decision pack only if blockers remain.

For a resumed task, run `python3 <skill-dir>/scripts/lifecycle.py resume <task-dir>` and read only its `filesToRead`. Start from `recommendedPhase` and `firstBlockingGate`, refresh only the facts listed under `requiredRefreshes`, and do not read generated HTML to reconstruct SQLite state.

## Comments

Run `sync-comments` once to merge pending comments without a gate attempt. Reply to every currently actionable thread before asking the user another question; run the applicable checkpoint only after structured content has been updated. Questions and suggestions do not block gates unless their content changes a required decision; unresolved `blocker` threads do.
