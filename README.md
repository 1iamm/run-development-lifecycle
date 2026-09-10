# run-development-lifecycle

给 coding agent 使用的本地开发迭代 skill：用 SQLite 管理多项目，按 **产品 → 技术 → UI → 开发 → 测试 → 上线** 展示卡片与全部任务表格，并保留文档、验证证据和变更历史。

A local, agent-driven development lifecycle workspace. Python standard library + SQLite + offline HTML. No hosted service or external database is required.

## 直接交给你的 agent

把下面这段发给有 Git、Python 和文件访问能力的 agent：

```text
请从 https://github.com/1iamm/run-development-lifecycle 安装这个 skill。
先阅读仓库 README.md 和 SKILL.md，再按 docs/agent-quickstart.md 执行。
如果同名目录已经存在，先核对来源和本地改动，不要覆盖。
用临时数据验证安装；不要导入、绑定或归档我的其他任务。
安装后告诉我 skill 路径、数据库路径，以及如何打开本地工作台。
```

这份公开版采用通用 Git、发布和日志流程，项目自己的 `AGENTS.md`、默认分支、CI/CD 和明确授权优先。无需特定公司的内网、账号、部署平台或 OpenSpec；没有专用设计/浏览器工具时，仍可维护台账和 HTML 文档。

## 能做什么

- 同一台电脑、同一数据库下汇总多个项目和多个 agent 会话。
- 六列看板、全部任务表格、同页展开任务详情。
- PRD、技术、UI、开发、测试、上线六类独立 HTML 页面及版本文件。
- 文档采用“总—分—总”，流程/关系优先图示，需求/接口/字段/用例优先表格。
- 以真实子任务计算进度；没有拆分项就显示待拆分，不估算百分比。
- Phase 依赖、审批、测试失败、修复与回归留痕。
- 本机 Codex 任务可关联原会话、点击跳转，在任意阶段手动归档任务与会话。
- 归档保存原阶段与未完成记录；本地归档副本 30 天后清理，原任务文件和 Codex 已归档会话继续保留。

普通聊天不会自动出现在看板里。Agent 必须按本 skill 创建/接入任务并更新记录；工作台不在后台调用模型或自动指挥其他会话。

## 环境要求与能力边界

| 能力 | 要求 |
| --- | --- |
| 看板、SQLite、HTML、生命周期 CLI | Python 3.10+，含标准库 `sqlite3`；现代浏览器 |
| Git 安装、更新和业务版本记录 | Git |
| 自动发现 skill | 当前 agent 主机支持技能目录；否则显式读取 `SKILL.md` |
| Codex 会话跳转与联动归档 | 本机已安装并可用的 Codex CLI/App Server、真实会话 ID；跳转需主机支持 `codex://` |
| Mermaid / PlantUML 图 | 由 agent 使用其已有渲染工具生成 SVG/图片或自包含 HTML；核心安装不依赖这些工具 |
| 自动 E2E、业务部署、远端日志 | 当前项目已有且授权的相应工具；本包不自带服务商凭据 |

核心运行不需要 `pip install` 或 `npm install`。主要验收环境为 macOS；核心代码使用 Python 标准库。其他操作系统上的 Codex 桌面链接、原生会话联动和进程管理应按当地环境验证，不能假定完全相同。

其他 agent 可使用本地台账和文档，但当前归档适配器只支持本机 Codex 会话。没有 Codex 绑定时，归档按钮不可用；不支持替其他 agent 的原生会话归档或删除。

## 安装

### Codex 个人技能目录

在终端执行，或让 agent 执行：

```bash
skill_dir="${CODEX_HOME:-$HOME/.codex}/skills/run-development-lifecycle"
git clone https://github.com/1iamm/run-development-lifecycle.git "$skill_dir"
python3 "$skill_dir/scripts/lifecycle.py" --help
```

目录已存在时 `git clone` 会失败；先检查它是否是同一仓库及是否有本地修改，不要删除后重装。代码和 `SKILL.md` 必须作为整个目录一起保留。

在新会话显式选择/调用 `$run-development-lifecycle`。旧会话应重新读取安装目录下的 `SKILL.md`；若主机仍未发现新 skill，按主机方式刷新技能列表或重启会话。

### 其他 agent / 自定义目录

克隆到该 agent 支持的技能目录；不要假定所有主机都支持相同的 `$skill` 语法。也可以克隆到任意持久目录，直接要求 agent 读取其中的 `SKILL.md`，用绝对路径调用脚本。执行命令时将下文 `skill_dir` 设置为真实安装目录。

## 使用

### 新需求

```text
使用 $run-development-lifecycle 新建任务。
项目：示例商城；项目目录：/实际/仓库/路径
需求：……
接入共享 SQLite 工作台，维护阶段、子任务、交付文档和测试证据。
如果当前环境是 Codex，请关联当前真实会话。
```

### 继续已有任务

```text
重新读取最新版 $run-development-lifecycle，继续任务【DEV 编号及任务目录】。
先 resume 对齐台账、当前阶段和阻塞项，再继续。
```

同名项目或相似标题不代表同一个任务。明确说“新需求”会创建新任务；为已有任务增加 Phase 需要明确指定父任务。

### 打开工作台 / 重启后恢复

```bash
python3 "$skill_dir/scripts/lifecycle.py" workspace serve --port 8765
```

打开 [本地工作台](http://127.0.0.1:8765/)。命令在前台运行，保持进程运行；`Ctrl+C` 停止服务。所有项目共用一份服务，页面约每 5 秒读取一次新状态。

不需要重新部署或导入数据。重启电脑后再次执行该命令，继续读取原数据库。安装不配置开机自启动；需要时按操作系统另行配置。

## 数据在哪里

| 内容 | 默认位置 |
| --- | --- |
| SQLite 台账 | `~/.codex/lifecycle/workspace.sqlite3` |
| 原始任务、证据、文档 | `~/Documents/Codex/dev-tasks/YYYY-MM-DD/<task>/` |
| 30 天归档副本 | 数据库所在目录的 `archives/<archive-id>/` |
| Skill 代码 | 安装时指定的 `skill_dir` |

数据与 skill 代码分开，更新 skill 不会重建数据库。`CODEX_HOME` 在上述安装示例中控制技能安装目录；数据库默认位置仍是表中的路径。需要改数据目录时，所有会话统一设置：

```bash
export LIFECYCLE_HOME="$HOME/.local/share/lifecycle"
python3 "$skill_dir/scripts/lifecycle.py" workspace serve --port 8765
```

**不要只在启动页面的会话中更改数据目录。** 新建任务和启动服务必须使用同一数据库。也可通过 init/import/serve 等命令的 `--database` 显式指定；任务的 `.lifecycle-store.json` 会记录其绑定数据库。

SQLite 是 V3 当前事实来源。`task.json`、`phases/*.json`、`comments.json`、`events.jsonl` 和 `index.html` 是复核导出，不应直接编辑来更新 V3 数据。正确的读写与版本冲突处理见 [agent quickstart](docs/agent-quickstart.md)。

## HTML 文档

文档总体和每个模块都遵循：**结论/目标 → 图表展开 → 决策、验收与风险收束**。少用长段文字；不要为了有图而画图，也不要把尚未渲染的图源码当作交付结果。

- PRD：目标/范围、用户路径或状态图、需求与验收表、异常边界、决策与风险。
- 技术方案：设计结论、架构/时序/ER/状态图、接口与数据表格、方案取舍、验证与回滚。
- 图源可以使用 Mermaid、PlantUML 或 SVG。渲染后的图和源文件一并保留；HTML 页面应离线可读。
- 交互原型单独登记为 UI 交付物；版本快照不可覆盖。

[完整 HTML 规范与字段](references/html-deliverables.md) · [图表与总分总写作约定](references/visual-narrative.md)

导出并登记一个版本文档：

```bash
python3 "$skill_dir/scripts/lifecycle.py" workspace document /实际/任务目录 \
  --phase P1 --kind technical --version v0.1
```

该命令渲染已保存的结构化记录，不会替 agent 创作完整方案或自动绘制 Mermaid/PlantUML。需要丰富图示时，按规范生成自包含 HTML 并用 `workspace deliverable` 登记。

## 归档与保留

归档必须来自用户按钮或明确请求，不要求任务 DONE。原阶段、待办、失败与批准记录不会被改成完成。当前 Codex turn 正在运行时先等待停止；归档先保存并校验本地副本，再调用 Codex App Server 并核验结果。失败会保留在看板，状态不明确时可重试核对。

30 天只清理归档副本，不删除原项目/任务资料、数据库索引/审计或 Codex 已归档会话。清理在服务启动及运行期间每 60 秒检查；电脑关机或服务停止期间不执行，下次启动补清理。

归档副本含任务资料、交付物和少量会话元数据，**不是 Codex 全量对话导出**。Codex 自身归档可能同时影响该任务的派生会话或托管 worktree，应在实际环境核对其行为。

## 更新与备份

确认安装目录没有未提交修改后：

```bash
git -C "$skill_dir" status --short
git -C "$skill_dir" pull --ff-only
```

更新后重新读取 skill；若服务正在运行，停止并重新启动它以加载代码。

一致性备份数据库（目标必须是新文件）：

```bash
python3 "$skill_dir/scripts/lifecycle.py" workspace backup \
  --output "$HOME/lifecycle-backup-YYYYMMDD.sqlite3"
```

原任务文档和证据目录需单独备份。不要直接复制正在写入的 SQLite 主文件而漏掉 WAL；使用上面的备份命令。备份不应绕过归档副本的 30 天保留约定。

## 验证与故障排查

```bash
cd "$skill_dir"
python3 -m unittest discover -s tests -v
```

测试使用临时目录、回环 HTTP 和模拟 Codex，不需要真实会话归档。受限 agent 沙箱可能需要允许本地监听端口后才能跑 HTTP 测试。

- 页面打不开：确认启动命令仍在运行，并使用其返回的 URL。
- 任务不出现：确认任务已经创建/导入、所有会话指向同一数据库。
- 外部导出文件冲突：保留外部编辑，读取 SQLite 最新 revision，合并后通过 `workspace update` 提交；不要删文件强行刷新。
- Codex CLI 找不到：设置 `LIFECYCLE_CODEX_BIN` 为本机真实可执行路径；勿指向他人环境。
- 归档按钮禁用：核对真实 Codex 会话绑定；其他 agent 原生会话暂不支持。

## 仓库入口

- [SKILL.md](SKILL.md)：给 agent 的主指令。
- [docs/agent-quickstart.md](docs/agent-quickstart.md)：安装检查、初始化、resume、读写、导出与接入示例。
- [references/sqlite-workspace.md](references/sqlite-workspace.md)：存储、并发、归档与维护。
- [references/v2-architecture.md](references/v2-architecture.md)：保留的 Phase 数据契约。
- `scripts/`：CLI、SQLite、HTTP、HTML 和 Codex 适配器。
- `tests/`：隔离的自动验证。

V2 JSON 任务可以显式导入；V1 HTML 台账保留独立验证路径，不自动迁移。不要把你的数据库、真实任务目录、内部文档或认证信息提交到这个仓库。
