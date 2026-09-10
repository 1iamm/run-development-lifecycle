# Legacy V1 HTML 台账契约

仅用于没有 `task.json` 的既有 V1 任务。V2 任务遵循 [v2-architecture.md](v2-architecture.md)，结构化 JSON/JSONL 是事实源，`index.html` 是生成视图；不要把本文件的单体 HTML 强制结构套到 V2。

## 1. 文件与信息架构

- 生成单文件、离线可打开的 HTML；不要依赖 CDN、在线字体或构建工具。
- 所有开发任务都建模为至少一个 Phase；单阶段任务使用 `P1`。
- 一级 Tab 使用动态结构：`总览 / Phase 1..N / 跨阶段集成 / 总结与审计`。
- Phase Tab 数量由已确认阶段决定，不硬编码为 7 个，也不把多个业务阶段塞进同一方案 Tab。
- 使用 `assets/ledger-demo.html` 的视觉语言；不要复用其中的任务事实。
- 提供 Tab 切换、每个 Tab 的区块目录、锚点定位、展开全部、打印/PDF、复制任务 ID、窄屏内部横向滚动。
- 全局任务头显示任务 ID、标题、整体状态、负责人、创建/更新时间、台账版本和阶段数。
- 未完成内容显示 `待确认`。强制方案产物不能仅用 `N/A` 代替；“无变化”也要记录现状、证据和不变约束。

## 2. Tab 内区块目录

每个一级 Tab 在标题后、正文前放置可见目录，使用 `data-section-toc`：

```html
<nav id="toc-phase-P1" class="section-toc" data-section-toc aria-label="P1 区块目录">
  <a href="#phase-P1-context">现状</a>
  <a href="#phase-P1-release">上线资源</a>
</nav>
```

稳定目录 ID：

- 总览：`toc-overview`；
- Phase：`toc-phase-<phaseId>`；
- 跨阶段集成：`toc-integration`；
- 总结与审计：`toc-summary`。

目录规则：

- 必须链接本 Tab 的所有固定区块，不能只列部分热门内容；
- Phase 目录按 `需求 / 方案 / 交付` 分组；`上线资源`必须独立可见并链接 `phase-<id>-release`；
- 宽目录在窄屏内横向滚动，不造成页面级横向溢出；
- 锚点目标设置滚动定位偏移，避免标题被顶部 Tab/目录遮挡；
- 直接打开带 hash 的地址时，脚本应激活目标所属 Tab 再定位；
- 打印时目录可隐藏，但正文和标题不能隐藏。

校验器必须验证目录存在、`data-section-toc` 存在、所有必需锚点齐全且目标真实存在。

## 3. 评论与 AI 追评

每个台账都启用 [comments.md](comments.md) 的离线评论协议，并包含以下稳定 ID：

```text
comment-mode-button / comments-button / comments-count /
comment-selection-action / comments-drawer / comments-close /
comments-filter / comments-list / comments-copy / comments-export /
comment-composer / comment-target-preview / comment-severity /
comment-textarea / comment-save / comment-cancel / ledger-comments-data /
ledger-comment-bridge-config
```

要求：

- `<html>` 声明 `data-comments-enabled="true"`、Task ID 和台账版本；
- `ledger-comments-data` 是合法的 `script[type="application/json"]`，包含 `version/taskId/ledgerVersion/threads`；
- `ledger-comment-bridge-config` 默认设置 `globalThis.__LEDGER_COMMENT_BRIDGE__=null`，由 loopback bridge 运行时临时注入 endpoint/token；
- 文本框选保存 section、quote、prefix、suffix；资源评论保存稳定 resourceId/type/label；
- 页面加载时为区块、表格、数据行、图、ER 实体、代码块和证据准备 `data-commentable`；
- 评论线程只追加消息，可过滤 open/resolved，可追评、解决或重新打开；
- “复制待处理评论”生成 AI 可处理 payload，但不得自动发送；“导出 JSON”只下载本地备份；
- bridge 激活时，每次保存/追评/解决或重新打开都自动同步到任务目录；页面明显展示自动同步状态，复制/导出继续作为降级；
- AI 写回回复或正文修改时更新内嵌 JSON、台账版本和审计；用户刷新后可继续追评；
- 打印隐藏评论控件、抽屉、选区按钮和评论模式轮廓；
- 评论中的 `blocker` 未解决时，校验器阻止对应 Phase 门禁。

## 4. 稳定的全局区块

### 总览 `panel-overview`

- `overview-status`：整体状态和核心指标。
- `overview-phase-map`：Phase 依赖图、状态和门禁。
- `overview-branch-lineage`：各 Phase 分支、父阶段、父候选 SHA、base/head SHA 和漂移状态。
- `overview-blockers`：阻塞、待确认、负责人和解除条件。
- `overview-commands`：唯一推荐动作和 2–4 个当前可用操作。
- `overview-links`：代码、学城、部署、测试和证据链接。

### 跨阶段集成 `panel-integration`

- `integration-dependencies`：跨 Phase API、事件、表、字段、状态和配置依赖。
- `integration-branches`：分支谱系、父 SHA 漂移和同步记录。
- `integration-resources`：共享 DDL、配置、开关、消息、任务和所有权。
- `integration-release`：部署顺序、兼容窗口、未就绪保护、总回滚策略。
- `integration-validation`：跨阶段契约、数据兼容、集成和回归用例。

### 总结与审计 `panel-summary`

- `summary-outcome`：每个 Phase 的结论、交付物、最终 SHA 和部署结果。
- `summary-risks`：风险、监控、遗留 Todo、负责人和期限。
- `summary-audit`：创建、确认、分支、同步、提交、部署、测试、修复、归档和完成时间线。
- `summary-continue`：追问、补充验收、重开和关联任务。

## 5. 动态 Phase Tab

每个 Phase 使用：

```html
<section
  id="panel-phase-P1"
  role="tabpanel"
  data-phase-id="P1"
  data-phase-order="1"
  data-phase-name="进件"
  data-phase-status="DESIGN_REVIEW"
  data-parent-phase="NONE">
```

对应一级 Tab 使用 `role="tab"` 和 `aria-controls="panel-phase-P1"`。Phase 内稳定区块以 `phase-<phaseId>-` 为前缀：

| ID | 内容 |
|---|---|
| `phase-P1-context` | 现状、真实入口、痛点、目标、非目标和证据 |
| `phase-P1-requirements` | REQ、验收、决策、冲突和待确认项 |
| `phase-P1-functional-breakdown` | 按角色拆解入口、操作、可见结果、人工责任、自动触发/任务、异常处理和全生命周期阶段；位于需求之后、技术架构之前 |
| `phase-P1-architecture` | 应用组件架构、职责、边界和外部依赖 |
| `phase-P1-code-architecture` | 仓库/模块/包/类或函数、调用链、依赖方向和代码落点 |
| `phase-P1-ui` | UI 适用性、复用边界、响应式、无障碍和 Reduced Motion |
| `phase-P1-data-architecture` | 主数据源、读写链路、事务/异步边界、查询方与恢复入口 |
| `phase-P1-domain-model` | 领域对象、聚合、规则、不变量和所有权 |
| `phase-P1-persistence-model` | 字段级 ER 图、PK/UK/IDX/FK或REF、基数及逻辑/物理关系 |
| `phase-P1-data-inventory` | 所有表、缓存、索引、Topic 和外部主数据源清单 |
| `phase-P1-state-machine` | 状态、合法转换、触发、终态和非法转换保护 |
| `phase-P1-sequence-main` | 创建、执行、查询和完成的主流程 |
| `phase-P1-sequence-recovery` | 失败、重试、补偿、补扫、对账和中断恢复 |
| `phase-P1-impact` | 固定 14 类影响矩阵 |
| `phase-P1-branch` | 父阶段、分支、父候选 SHA、base/head 和同步记录 |
| `phase-P1-release` | DDL/配置/开关/消息/任务、部署顺序、验证和回滚 |
| `phase-P1-validation` | 测试用例、实际结果、截图/日志和问题 |
| `phase-P1-traceability` | REQ 到设计、代码、数据、测试和发布的追踪 |

每个 Phase 的详细交付物遵循 [design-deliverables.md](design-deliverables.md)。多阶段分支和依赖遵循 [phased-delivery.md](phased-delivery.md)。

## 6. 分支区块契约

`phase-<id>-branch` 至少包含：

```text
phaseId / parentPhaseId / branch / parentBranch / parentCandidateSHA /
baseSHA / headSHA / createdAt / syncStatus / lastSyncCommit / evidence
```

- P1 的 `parentPhaseId` 为 `NONE`，`baseSHA` 来自本次记录的 已核实的远端基线分支。
- P2..N 的 `parentPhaseId` 必须指向前置 Phase；`baseSHA` 必须等于创建时的 `parentCandidateSHA`。
- 下游分支创建后父候选变化，显示 `STALE_PARENT`，不得保持绿色完成态。
- 每次父分支同步都追加新记录，不覆盖旧父 SHA。

## 7. 需求、影响、资源与验证

- 需求表字段：`REQ-ID / 描述 / 验收标准 / 优先级 / 状态 / 证据`。
- 功能拆解必须紧随需求区块，至少覆盖参与角色、生命周期阶段、入口/触发、操作、可见状态或输出、人工责任、系统自动动作、失败/恢复入口和对应 REQ；不得用数据表或类名清单替代产品功能。
- 影响矩阵必须覆盖 [design-deliverables.md](design-deliverables.md) 的 14 类；每类都有判定、理由、兼容、验证、监控/回滚和证据。
- 上线资源不只记录 SQL。必须盘点数据库、配置、开关、权限、消息、定时任务、缓存、ES、外部平台、监控与告警。
- DDL 存在时提供真实库表、完整正向/校验/回滚 SQL、执行顺序、数据量/锁表风险、兼容和回滚限制。
- 无 DDL 时写清复用表和“不变”的证据，不能只写“无数据库改动”。
- 验证表字段：`TC-ID / REQ-ID / 模块 / 前置条件 / 操作路径 / 预期 / 实际 / 版本 / 状态 / 截图或证据`。
- 修复后保留失败行，新增修复 SHA、部署尝试和回归行。

## 8. 证据、状态与增量更新

- 同一任务只维护一个 HTML；每次有效更新递增台账版本和 `updated_at`。
- 使用稳定 ID：`PHASE / REQ / DEC / ARCH / DATA / IMPACT / DEV / DEPLOY / TC / LOG / ISSUE`。
- 所有方案产物声明 `data-artifact`、`data-status`、`data-evidence-count` 和 `data-as-of`。
- 事实记录来源链接/文件与行号、命令、Commit、部署 ID、截图、时间和 as-of；推断明确标识。
- 新结论替代旧结论时标记 `superseded` 并引用替代记录。
- 评论、追评、正文修订、解决和重新打开都追加审计事件；不得删除评论历史。
- 总览状态从 Phase 明细派生，不能维护第二份互相矛盾的事实。
- 日志和截图脱敏；不嵌入令牌、Cookie、个人信息或完整生产数据。

## 9. 校验与完成

- 新建骨架后运行 `--gate structure --live`。
- 请求 Phase 需求确认前运行 `--gate requirements --phase <id> --live`。
- 请求 Phase 方案确认前运行 `--gate design --phase <id> --live`。
- 创建下游分支前运行 `--gate branch --phase <id> --live`。
- 整体完成前运行 `--gate done --live`。
- 每次都先修复所有错误；用户确认不能覆盖校验失败。
- 浏览器检查桌面、移动、Tab、锚点、展开全部、打印、宽图/表内部滚动和控制台。
- 只有所有 Phase 完成、跨阶段集成验证通过且无必需工作遗留，整体状态才能为 `DONE`。
