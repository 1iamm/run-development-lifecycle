# 生命周期状态机

## 目录

1. 状态
2. 转换
3. 人工门禁
4. 模式约束
5. 继续、重开与关联任务

## 1. 状态

使用整体任务状态和 Phase 子状态组成的显式状态机，并维护只追加事件记录。不要只依赖对话记忆。单阶段任务也使用 `P1`。V2 在 `events.jsonl` 记录转换，Phase JSON 保存当前有效状态；V1 继续使用 HTML 审计区。

| 状态 | 含义 | 退出条件 |
|---|---|---|
| `IDLE` | 没有进行中的任务 | 用户新建或继续任务 |
| `DISCOVERY` | 收集背景、远端 master 代码与内外部证据 | 现状、范围、冲突和问题可供评审 |
| `REQUIREMENTS_REVIEW` | 迭代需求、验收和决策 | 用户显式确认需求版本 |
| `REQUIREMENTS_APPROVED` | 需求门禁已通过 | 进入方案评审 |
| `DESIGN_REVIEW` | 迭代 UI 适用性/方向、架构、数据、时序、影响、资源和测试 | 用户显式确认方案版本 |
| `DESIGN_APPROVED` | 方案门禁已通过 | 准备开发 |
| `IMPLEMENTING` | feat worktree、OpenSpec、编码 | 实现完成并进入本地验证 |
| `LOCAL_VERIFY` | 单测、集成、Build、Lint、类型检查 | 全部适用检查通过 |
| `SPEC_ARCHIVED` | 代码/单测范围的 OpenSpec 已验证并归档 | 候选提交准备完成 |
| `CANDIDATE_PUSHED` | 可部署 feat SHA 已推送 | 发布路径、目标和回滚点获确认 |
| `READY_DEPLOY` | 部署门禁等待或已满足 | 用户确认分支、SHA、环境和资源 |
| `DEPLOYING` | 部署平台或本地应用启动中 | 组件健康且平台 SHA 匹配 |
| `E2E` | 当前主机提供的浏览器测试和 项目日志/可观测性核验 | 所有适用用例通过或进入修复 |
| `FIXING` | 保留失败证据，在 feat 修复 | 本地验证、候选 push、集成和重部署完成 |
| `FINALIZING` | 最终 push、总结、校验 | 所有必需证据齐全 |
| `DONE` | 生命周期完成 | 重开或新建任务 |

每个 Phase 独立运行上述状态。整体任务状态从 Phase 和跨阶段集成状态派生；任一 Phase 未完成或跨阶段验证未通过时，整体不能进入 `DONE`。

## 2. 转换

正常路径：

```text
IDLE
→ DISCOVERY
→ REQUIREMENTS_REVIEW
→ REQUIREMENTS_APPROVED
→ DESIGN_REVIEW
→ DESIGN_APPROVED
→ IMPLEMENTING
→ LOCAL_VERIFY
→ SPEC_ARCHIVED
→ CANDIDATE_PUSHED
→ READY_DEPLOY
→ DEPLOYING
→ E2E
→ FINALIZING
→ DONE
```

失败与变更回环：

- 单测失败：`LOCAL_VERIFY → IMPLEMENTING`。
- 动效评审 `Block`：保留 findings，`LOCAL_VERIFY → IMPLEMENTING`；修复、重跑本地检查并取得后续 `Approve`。
- 部署失败：保留尝试，`DEPLOYING → READY_DEPLOY`。
- E2E 失败：`E2E → FIXING → LOCAL_VERIFY → CANDIDATE_PUSHED → READY_DEPLOY → DEPLOYING → E2E`。
- E2E 修复改变已归档规格：在 `FIXING` 创建关联 OpenSpec change；本地验证后归档该 follow-up，再生成新候选 SHA。
- 新信息改变已确认需求：保留原确认，标记被替代，回到 `REQUIREMENTS_REVIEW`，并把下游方案/代码/测试标记为待重新确认。
- 新信息只改变方案：回到 `DESIGN_REVIEW`，并标记受影响实现和测试。
- 缺少信息、权限或外部确认：停留在当前状态并写明等待条件；不得越过门禁。
- 父 Phase 候选 SHA 在子 Phase 分支创建后变化：子 Phase 标记 `STALE_PARENT`，保持当前业务状态但阻止候选 push、部署和完成；同步父分支并重新验证后解除。
- 评论改变已确认需求或方案：保留原确认和评论线程，回到对应 `REQUIREMENTS_REVIEW` 或 `DESIGN_REVIEW`，把受影响下游产物标为待重新确认。

不要因为失败重建任务或删除旧记录。每个转换都追加时间、触发人、前后状态、原因和证据。

## 3. 人工门禁

### 范围门禁

要求目标、仓库、非目标、验收标准和允许的操作范围明确。缺少仓库或目标时可以先建立台账，但不得宣称调研完成。

### 需求门禁

仅在以下项目齐备时请求确认：

- 背景和现状有证据；
- 目标与非目标明确；
- 每条需求有验收标准；
- 冲突和假设已解决或显式接受；
- 待确认项没有阻断方案设计。

记录确认人、时间和台账版本。V2 先运行 `python3 <skill-dir>/scripts/lifecycle.py checkpoint <task-dir> --gate requirements --phase <id>`；V1 使用 `<skill-dir>/scripts/validate_ledger.py`。只有校验成功和明确肯定答复同时存在才通过。

`FAST/STANDARD` 可在需求和方案均完整时一次展示、一次合并确认；仍要分别通过 requirements/design 校验，并把两个状态转换追加到事件流。`STRICT` 保留独立需求确认。

### 方案门禁

V2 按 `design-deliverables-v2.md` 和风险适用性要求结构化产物；`STRICT` 检查全部产物键，确实不适用时允许有证据的 `not-applicable`。V1 继续要求 `design-deliverables.md` 的完整固定产物。ER 图中的表和数据清单必须逐项一致。

请求确认前，V2 运行 `python3 <skill-dir>/scripts/lifecycle.py checkpoint <task-dir> --gate design --phase <id>`，V1 使用 `<skill-dir>/scripts/validate_ledger.py`。空结论、无来源的 `unchanged/not-applicable`、用 DDL 替代数据清单、只画正常路径或缺少适用产物均不能通过。

目标属于当前 Phase 的未解决 `blocker` 评论同样阻止方案门禁。请求确认前报告所有未解决 question/suggestion，并询问用户是否还有尚未复制给 AI 的浏览器本地评论。

同时要求先记录 UI 设计门禁适用性：

- 无用户可见 UI 变化时，记录 `N/A` 和理由；
- 有 UI 变化但无方向分歧时，记录复用的设计系统、组件、Token、响应式与无障碍约束；
- 有实质方向分歧时，必须提供独立原型证据并由用户显式选择；
- 有新增或修改动效时，方案中必须定义目的、频率、关键参数、Reduced Motion 和验证范围。

适用项没有选定方向或确认记录时不得通过方案门禁。

### 开发门禁

要求该 Phase 的需求和方案均确认、基线 SHA 明确、Phase feat worktree 就绪、项目规格记录已建立（采用 OpenSpec 的项目建立对应 change）。Codex 协作模式不替代此门禁。

- P1 从本次 fresh fetch 并记录 SHA 的 已核实的远端基线分支 创建。
- P2..N 从父 Phase 的确切候选 SHA 创建；父 Phase 至少为 `CANDIDATE_PUSHED`。
- 创建下游分支前，V2 运行 `python3 <skill-dir>/scripts/lifecycle.py checkpoint <task-dir> --gate branch --phase <id>`；V1 使用 `<skill-dir>/scripts/validate_ledger.py`。
- 父候选 SHA 漂移时，下游进入 `STALE_PARENT`，同步和重验前不得 push 新候选或部署。

### 部署门禁

要求用户明确：

- 项目实际测试或发布环境，不假设固定环境；
- 组件和精确目标；
- 仓库、分支、候选 SHA；
- DDL/配置执行责任与顺序；
- 验证与回滚版本。

生产、DDL 执行、数据迁移、删除、强制操作分别需要独立明确授权。本 Skill 的默认发布范围是测试环境，不把测试环境授权扩展到生产。

### 完成门禁

要求每个 Phase 的适用需求、代码、本地测试、适用的规格流程、部署、E2E、日志核验、问题回归、最终 push 和总结都有证据；跨阶段契约、分支谱系、共享数据/资源、部署顺序和集成回归也必须通过。V2 运行 `python3 <skill-dir>/scripts/lifecycle.py checkpoint <task-dir> --gate done`，V1 使用 `<skill-dir>/scripts/validate_ledger.py`。允许延期的项目必须记录接受人、范围、负责人和期限。

## 4. 执行约束

- Codex 协作模式不是生命周期门禁，不要求用户为需求、方案或开发来回切换模式。
- `DISCOVERY / REQUIREMENTS_REVIEW / DESIGN_REVIEW` 允许只读调研、任务数据更新和仓库外独立原型；在 `DESIGN_APPROVED` 前不得写业务代码、创建开发提交、push、部署或执行有外部副作用的 E2E。
- `DESIGN_APPROVED` 后才可按授权创建 worktree、项目采用的规格记录、编码和测试。外部 push、部署、SQL、数据迁移和删除仍需要各自适用的明确授权。
- 当前主机提供的浏览器 E2E 和 项目日志/可观测性检查遵循发布验证规则；遵守用户明确指定的浏览器约束。
- 查看状态、读取结构化任务数据和回答问题不改变状态。

## 5. 继续、重开与关联任务

### 继续

V2 先运行 `python3 <skill-dir>/scripts/lifecycle.py resume <task-dir>`，按返回的 `recommendedPhase / firstBlockingGate / filesToRead / requiredRefreshes` 恢复，再核对必要的仓库/worktree 真实状态；V1 才读取 HTML。先报告依赖顺序中的首个未通过门禁和所有 `STALE_PARENT`，不要重做已完成且仍有效的阶段。

### 重开

仅对 `DONE` 任务创建新迭代，例如 `DEV-20260807-001/R1`。保留原完成快照，增加重开原因和父版本。根据影响回到需求、方案或开发；代码变更使用新的 OpenSpec change。

### 关联任务

创建独立 Task ID 和 ledger，记录 `parentTaskId`。一个会话只能有一个执行中的生命周期；若当前任务未完成，把关联任务登记为排队，等待用户明确切换。

### 完成后的会话

`DONE` 不关闭会话。继续支持追问、补充验收、查看状态、重开、新建关联任务或全新任务。
