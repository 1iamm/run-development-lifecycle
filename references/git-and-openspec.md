# Git、Worktree 与规格管理

## 基线与工作目录

先读取目标项目的 `AGENTS.md`、贡献说明、分支保护和已有规格流程。核对仓库根目录、remote、当前 branch、status、worktree list 和现有分支。保留用户的脏改动；不要擅自 stash、reset、clean、切换其工作目录或覆盖未知路径。

P1 从项目已确定的基线创建。优先采用仓库规则或用户指定分支；否则读取远端默认分支，例如 `git symbolic-ref refs/remotes/origin/HEAD`，缺失时用 `git ls-remote --symref origin HEAD` 核实。不要硬编码 main、master 或 develop。记录本次 fetch 后的确切 SHA。

- 只读研究可使用 detached worktree；不要在该 worktree 实现功能。
- 设计确认后，从记录的基线 SHA 创建任务开发分支和 worktree。仓库无命名约定时可用 `feat/<task-id>-<phase-id>-<slug>`。
- 后续 Phase 从明确的父 Phase 候选 SHA 创建；父 Phase 变化时标记 `STALE_PARENT`，同步已知父候选并重新验证。
- 不把包含无关变更的临时集成分支当作功能开发来源。不覆盖未知已有分支，不静默 rebase 或 force push。
- 多仓库任务分别记录 baseline、branch、SHA、版本与验证结果。

## 规格管理

使用项目已有的规格约定。项目采用 OpenSpec 时，按已安装 CLI 的实际文档执行 proposal/design/tasks、validate 和 archive；每个 Phase 对应独立 change，记录父候选谱系。不要伪造工具执行结果。

项目没有 OpenSpec 时，直接采用本 skill 的 SQLite 台账与 HTML 交付文档；没有 OpenSpec 不是阻塞，不需要为使用工作台额外安装它。使用其他规格系统时记录其引用及适用检查。

## 提交、评审与部署

1. 只暂存当前任务明确拥有的改动，检查 diff、未跟踪文件和生成物。
2. 完成适用测试和构建，将失败、修复及回归分别留痕。
3. 检查没有把数据库、任务记录、证据原件、凭据、环境文件或私人服务地址带进 Git。
4. 根据当前用户授权提交、推送或创建 PR；记录目标分支、候选 SHA 和结果。已有授权保持有效，不重复确认同一未变化操作。
5. 遵循目标仓库分支保护和评审流程。推送受保护分支、合并或部署不能从“创建台账”推导授权。
6. 如果推送/合并会自动触发 CI/CD，记录这项联动，避免额外触发重复部署。
7. E2E 修复回到当前任务分支，生成并核验新候选，不修改其他任务分支。
8. 只有在任务资料已保存在独立任务根目录、worktree 干净且已获允许时才清理任务 worktree。

发布验证见 [deployment-validation.md](deployment-validation.md)。本 skill 不预设特定公司的 Git 托管、部署或日志平台。
