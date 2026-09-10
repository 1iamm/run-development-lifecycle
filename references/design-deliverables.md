# Legacy V1 方案交付物与语义门禁

仅用于没有 `task.json` 的既有 V1 任务。V2 使用 [design-deliverables-v2.md](design-deliverables-v2.md) 的风险适配结构化产物。

## 1. 目的

把“应当描述架构、模型、时序和影响”变成可验证的方案交付物。标题、空容器、关键词堆砌或一句 `N/A` 都不算完成。

每个方案交付物根节点必须声明：

```html
<section
  id="phase-P1-code-architecture"
  data-artifact="code-architecture"
  data-status="complete"
  data-evidence-count="2"
  data-as-of="2026-08-21">
```

- `data-status` 只有 `complete` 才能通过方案门禁。
- `data-evidence-count` 必须大于零，且可见内容中必须给出文件、文档、Schema、Commit 或调研命令等证据。
- `data-as-of` 记录证据时间或基线日期。
- “无新增”“沿用”“不变”是结论，不是省略产物的理由。仍需写出现有结构、证据和不变约束。

## 2. 每个 Phase 的强制产物

| Artifact | 稳定 ID 后缀 | 最低内容 |
|---|---|---|
| 现状与范围 | `context` | 当前行为、真实入口、痛点、目标、非目标、证据 |
| 需求与验收 | `requirements` | REQ、验收标准、优先级、状态、决策与待确认项 |
| 功能拆解 | `functional-breakdown` | 紧随需求，按角色和生命周期阶段列出入口/触发、操作、可见结果、人工责任、系统自动动作、异常处理及对应REQ |
| 应用架构 | `architecture` | 系统/组件图、职责、调用边界、同步/异步依赖、外部系统 |
| 代码架构 | `code-architecture` | 仓库、模块、包、入口类/函数、调用链、依赖方向、预计文件落点 |
| 数据架构 | `data-architecture` | 主数据源、完整读写链路、事务/异步边界、写入方、查询方、恢复入口 |
| 领域模型 | `domain-model` | 聚合/实体/值对象/领域服务、规则、不变量、所有权 |
| 表级 ER 图 | `persistence-model` | 每张表的关键字段、PK/UK/IDX/FK或REF、1:1/1:N/N:M、逻辑/物理关系 |
| 数据资产清单 | `data-inventory` | 所有 DB 表、缓存、索引、Topic 和外部主数据源的逐项清单 |
| 状态机 | `state-machine` | 状态、合法转换、触发条件、终态、非法转换保护 |
| 主业务流程 | `sequence-main` | 创建、校验、写入、执行、查询、完成及事务/异步边界 |
| 异常恢复流程 | `sequence-recovery` | 重复、失败、超时、重试、补偿、补扫、对账、中断恢复 |
| 影响矩阵 | `impact` | 固定影响类别逐项判定、兼容、验证、监控与回滚 |
| 分支与基线 | `branch` | 分支、父阶段、父 SHA、base SHA、候选 SHA 和同步记录 |
| 上线资源 | `release` | DDL、配置、开关、消息、任务、部署顺序、验证、负责人和回滚 |
| 测试与证据 | `validation` | 模块化用例、预期/实际、版本、状态、截图/日志 |
| 需求追踪 | `traceability` | REQ → 架构 → 代码 → 数据 → 测试 → 发布资源 |

功能拆解不能用应用架构、数据模型或类/表清单代替；它先回答“谁在什么时候做什么、看到什么、系统自动做什么”。代码架构不能用应用组件图代替。数据架构不能用业务时序图代替。ER 图不能用“表 A → 表 B”的表名方框代替。数据资产清单不能用 DDL 代替。主业务流程不能用正常路径的一段文字代替，异常恢复必须独立展示。

## 3. 数据资产清单

每一行至少包含：

```text
类型 / 数据源或库 / 对象名 / 新增或既有 / 业务职责 / 操作类型 /
主数据与所有者 / 写入方 / 读取方 / PK-UK-索引 / 数据量与热点 /
迁移-保留-清理 / 回滚限制 / 证据
```

最低要求：

- 所有运行时读取或写入的表都列出，而不仅是发生 DDL 的表；
- Redis、ES、MQ Topic、定时任务中间表、审计表和外部主数据源同样列出；
- 无持久化变更时仍列出复用的数据源，并将“新增或既有”标记为 `既有不变`；
- 没有任何持久化或外部数据依赖时，保留一行“无持久化数据”，说明内存状态生命周期和代码证据。

## 4. 数据架构图与 ER 图

### 数据架构图

每个 Phase 都必须画数据架构，至少表现：

- 命令写链路、查询读链路和技术恢复链路；
- 唯一主数据源和数据所有者；
- 写入方、查询方、外部调用和跨 Phase 读取；
- 事务 T1/T2、afterCommit 或 Outbox、消息/任务等异步边界；
- 失败持久化、重试、补扫、对账和审计入口。

根图形使用 `data-diagram-kind="data-architecture"`。图中数据对象必须使用真实表、Topic、缓存或索引名，不只写“数据库”。

### 表级 ER 图

每个 Phase 都必须提供真正的 ER 图，根图形使用 `data-diagram-kind="erd"`：

- 每张表使用 `data-entity="真实表名"`；至少展示关键字段及其类型/语义；
- 标识 `PK`、`UK`、关键 `IDX`，以及物理 `FK` 或逻辑 `REF`；
- 每条关系使用 `data-relationship="source|cardinality|target|physical-or-logical"`；
- 基数明确写为 `1:1`、`1:N` 或 `N:M`；
- 物理外键和逻辑引用使用不同线型/标签，不得混淆；
- 审计表、明细表、关联表和继承自父 Phase 的表都要画出；
- ER 图中的每个 `data-entity` 必须在数据资产清单里有相同 `data-object` 行，反之数据库表行也应在 ER 图中出现。

如果 Phase 确实不使用持久化表，ER 区块仍保留并提供 `data-no-persistence="true"`、原因、内存状态生命周期和代码证据；不能只写 `N/A`。

## 5. 影响矩阵

以下类别必须全部出现。每项标记 `受影响 / 不受影响 / N/A`，后两者也必须说明理由和证据：

1. 用户与 UI
2. 前端代码
3. 后端服务
4. API / RPC 契约
5. 数据与存储
6. 消息与异步任务
7. 配置、开关与密钥引用
8. 权限、租户与数据隔离
9. 上游调用方
10. 下游依赖
11. 监控、告警与审计
12. 容量、性能与限流
13. 发布、兼容与回滚
14. 安全、隐私与合规

每行至少记录对象、判定、变化或理由、兼容策略、验证、监控/回滚和证据。

## 6. 图与证据

- 应用架构、代码架构、数据架构、领域模型、ER 图、状态机、主流程和异常恢复都要有可见图形。使用内联 SVG 或带 `data-diagram` 的离线图形容器。
- 图必须配可访问标题/说明，宽图放在可横向滚动容器中。
- 图中名称应能对应到下方表格、代码路径或数据对象，不能只有抽象方框。
- 每项关键事实记录来源、基线 SHA 或 as-of 和置信度。推断明确标识。

## 7. 门禁命令

在不同阶段运行：

```bash
python3 <skill-dir>/scripts/validate_ledger.py index.html --gate structure --live
python3 <skill-dir>/scripts/validate_ledger.py index.html --gate requirements --phase P1 --live
python3 <skill-dir>/scripts/validate_ledger.py index.html --gate design --phase P1 --live
python3 <skill-dir>/scripts/validate_ledger.py index.html --gate branch --phase P2 --live
python3 <skill-dir>/scripts/validate_ledger.py index.html --gate done --live
```

只有相应命令返回 0，才能请求该门禁的用户确认。用户确认不能替代缺失的交付物；接受延期必须记录范围、风险、接受人、负责人和期限，并且不能把阻断性的架构或数据未知项标成已完成。
