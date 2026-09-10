# 多阶段任务、Tab 与分支谱系

## 1. 适用性

当一个需求有可独立设计、开发、验证或上线的阶段时，使用多 Phase 模式。例如：

```text
P1 进件 → P2 微信支付 → P3 连续包月
```

不要因为仓库多、服务多就自动拆 Phase。Phase 表示可审计的业务交付阶段，必须有清晰范围、验收标准、依赖关系和发布边界。

## 2. 台账结构

多阶段台账使用动态一级 Tab：

```text
总览 | Phase 1 | Phase 2 | ... | 跨阶段集成 | 总结与审计
```

每个 Phase 是一份完整的小生命周期，V2 由独立 `phases/<id>.json` 保存当前事实并生成 Tab；必须包含现状与范围、需求、适用方案产物、分支谱系、上线资源、验证和追踪。不要把所有 Phase 的方案混进一个全局对象。

总览展示：

- Phase 依赖图和总体完成度；
- 每个 Phase 的状态、分支、父 SHA、候选 SHA、发布环境和阻塞；
- 当前唯一推荐动作。

跨阶段集成展示：

- Phase 依赖、共享接口/数据/资源和兼容窗口；
- 分支谱系与父 SHA 漂移；
- 跨阶段集成测试、部署顺序、总回滚策略；
- 后阶段对前阶段契约和数据的依赖。

## 3. Phase 状态

每个 Phase 使用 [state-machine.md](state-machine.md) 的完整状态机；本文件不维护第二份简化状态列表。

整体任务状态从各 Phase 派生，不能手工宣称全部完成：

- 任一 Phase 阻塞：整体显示阻塞 Phase；
- 所有 Phase `DONE` 且跨阶段验证通过：整体才可 `DONE`；
- 后阶段可以提前调研和设计，但代码分支与上线受依赖门禁约束。

## 4. 分支谱系

默认规则：

1. P1 从本次 fresh fetch 并记录的 已核实的远端基线分支 SHA 创建。
2. P2 从 P1 已推送的确切候选 SHA 创建，不从一个会移动的分支名含糊创建。
3. P3 从 P2 已推送的确切候选 SHA 创建，依此类推。
4. 每个 Phase 使用独立分支和开发 worktree，例如：

```text
feat/DEV-20260821-001-p1-onboarding
feat/DEV-20260821-001-p2-wechat-pay
feat/DEV-20260821-001-p3-recurring
```

5. `phase-<id>-branch` 记录 `phaseId / parentPhaseId / branch / parentBranch / parentCandidateSHA / baseSHA / headSHA / createdAt / syncStatus`。
6. 创建下游 Phase 分支前，父 Phase 必须至少达到 `CANDIDATE_PUSHED`，并运行 `--gate branch --phase <id>`。

## 5. 父阶段继续变化

下游分支创建后，如果父阶段产生新候选 SHA：

- 把下游标记为 `STALE_PARENT`，记录原父 SHA 和新父 SHA；
- 默认把父阶段的新提交 merge 到下游 Phase 分支，保留谱系和共享历史；
- 禁止静默 rebase、改写已共享历史或 force push；
- 重新运行受影响的本地检查、契约测试和数据兼容检查；
- 更新 `parentCandidateSHA`、同步 commit 和证据；
- 若变化影响后阶段需求或方案，回到对应 Phase 的 `REQUIREMENTS_REVIEW` 或 `DESIGN_REVIEW`。

只有用户明确选择并且分支未共享时，才可采用 rebase。记录选择、理由和新旧 SHA。

## 6. 跨阶段接口与数据

后阶段不得仅写“依赖上一阶段”。必须明确：

- 依赖的 API、事件、表、字段、状态和配置；
- 父阶段提供的最小契约及对应 SHA；
- 向前/向后兼容窗口；
- 部署先后顺序和未就绪保护；
- 父阶段回滚时后阶段如何降级或停止；
- 跨阶段测试用例和证据。

共享表或状态机必须明确最终所有者。后阶段扩展前阶段模型时，在两个 Phase 的数据清单中互相引用，并在跨阶段集成 Tab 记录最终合并形态。

## 7. 发布顺序

默认按依赖顺序发布。后阶段进入 `DEPLOYING` 前，父阶段必须满足台账中声明的发布依赖，通常是父阶段测试环境 E2E 通过。

允许在同一发布窗口连续部署多个 Phase，但仍要：

- 为每个 Phase 保留独立候选 SHA、部署记录、验证和回滚点；
- 明确共享 DDL/配置由哪个 Phase 首次引入；
- 按 Phase 顺序执行冒烟与跨阶段回归；
- 任一阶段失败时停止后续阶段，并按兼容关系决定代码回滚、配置关闭或数据修复。
