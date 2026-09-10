# V2 design deliverables

For SQLite-backed tasks, use [html-deliverables.md](html-deliverables.md) for the HTML reading/export format. This reference continues to govern structured evidence and gate applicability.

## Principle

Design evidence is structured and proportional to actual risk. Do not satisfy gates with keyword padding, repeated prose, or empty diagrams. Store current effective content in the active Phase JSON and detailed raw evidence under `evidence/`.

Every required artifact contains:

```json
{
  "status": "complete | unchanged | not-applicable | pending",
  "summary": "concise decision-ready conclusion",
  "evidence": ["source path, commit, document, query, or evidence file"],
  "details": []
}
```

`complete`, `unchanged`, and `not-applicable` require a summary and evidence. Use `details` for structured diagrams, tables, decisions, or constraints only when they materially improve review.

## Always required

- Functional breakdown: role, entry/trigger, operation, visible result, automation, failure/recovery, and owning requirement.
- Code architecture: repositories, modules, real entrypoints, call chain, dependency direction, and expected change points.
- Impact: impacted categories, compatibility, verification, monitoring, rollback, and evidence. Keep unaffected categories compact.
- Validation: planned and actual tests with requirement links, versions, status, and evidence.
- Traceability: requirement to design, code, data, tests, and release resources.

## Conditional artifacts

- Application architecture: required for runtime component or service responsibility changes.
- UI design: required only for user-visible UI changes.
- Data architecture/domain/ER/inventory: required for new or changed persistence and for existing data constraints that materially govern behavior. If existing data is only read and unchanged, use an evidenced `unchanged` artifact rather than reproducing the full schema.
- State machine/main/recovery flows: required for asynchronous, retryable, multi-state, payment, or externally coordinated behavior.
- Release: required for deployment, DDL, configuration, switches, messages, scheduled jobs, permissions, or external platform resources.

`STRICT` validates every artifact key, but truly inapplicable artifacts may use evidenced `not-applicable`. `FAST` and `STANDARD` validate only always-required and applicable artifacts.

## Structured diagram details

Use details only when a relationship or exact mapping is easier to review visually than as prose. Keep one decision-ready summary above the detail and raw evidence outside the main reading flow.

- `diagram`, `dependencyGraph`, `branchGraph`, and `recoveryFlow`: nodes and labeled edges;
- `sequence`: actor/system lanes with ordered steps and transaction or async boundaries;
- `stateMachine`: states plus labeled transitions, failure branches, retry loops, and terminal states;
- `erd`: entities, fields, keys, and physical/logical relationships;
- `table`: exact records; `matrix`: affected/unresolved rows first and unaffected rows compact;
- `releaseStepper`: ordered release/verification/rollback steps; `timeline`: time-ordered changes.

Use a generic diagram detail for a small linear relationship:

```json
{
  "type": "diagram",
  "nodes": [{"id": "api", "label": "API", "detail": "entry"}],
  "edges": [{"from": "api", "to": "service", "label": "RPC"}]
}
```

Use an ER detail for persistence:

```json
{
  "type": "erd",
  "entities": [{"name": "table_name", "fields": ["PK id", "UK tenant_id + request_id"]}],
  "relationships": ["parent 1:N child logical REF"]
}
```

Entity names must match the data inventory. Label keys, indexes, cardinality, and physical versus logical relationships. Keep executable SQL in a dedicated evidence file and reference it from the release artifact.

Do not draw a diagram merely to restate one sentence. Simple tasks should omit empty and inapplicable modules. Complex tasks should use diagrams for relationships, tables for exact mappings, and concise prose only for conclusions, constraints, and exceptions.

## Gate preparation

Before asking for approval:

1. populate observed facts and evidence;
2. resolve or group blocking decisions into one decision pack;
3. add planned tests;
4. run `python3 <skill-dir>/scripts/lifecycle.py checkpoint <task-dir> --gate requirements|design --phase <id>`;
5. ask for the profile-appropriate explicit confirmation only after the checkpoint passes;
6. run `python3 <skill-dir>/scripts/lifecycle.py approve ...` only after that confirmation.
