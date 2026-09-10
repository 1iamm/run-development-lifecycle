# 生命周期评论线程与 AI 追评协议

## 1. 目标与边界

台账评论用于解释、质疑和修订已有内容，不直接授权代码、部署、SQL 或其他外部操作。评论 UI 只与本机 loopback 服务同步，不向外部网络或 AI 自动发送内容。

V2 的持久化权威记录是 `comments.json`，生成 HTML 嵌入其快照；浏览器更新先写 `.ledger-comments/comments.pending.json`，下一次 `sync-comments` 合并。V1 继续以内嵌 `ledger-comments-data` 为权威记录。

V1 因浏览器不能可靠地直接改写 `file://` HTML 源文件而采用三层存储；V2 使用相同的浏览器 pending 层，但把 `comments.json` 作为权威源：

- `comments.json`：V2 已处理并合并的权威评论记录；生成 HTML 的 `ledger-comments-data` 是其快照；V1 则以内嵌数据为权威；
- 浏览器 `localStorage`：用户尚未提交给 AI 的本地评论和追评。
- 任务目录 `.ledger-comments/comments.pending.json`：本机评论桥接保存的待处理快照，Codex 可直接读取。

页面加载时按 Comment ID 和 Message ID 合并内嵌记录与 localStorage。评论桥接可用时，页面把合并后的状态自动同步到任务目录；用户无需复制粘贴。“复制待处理评论”和“导出 JSON”仍作为桥接不可用时的显式降级入口。V2 中 AI 更新结构化内容和 `comments.json` 后运行 checkpoint 重新生成 HTML，用户刷新本地服务页面查看结果。V1 仍按兼容流程更新源 HTML。

## 2. 本机自动评论桥接

V2 启动：

```bash
python3 <skill-dir>/scripts/lifecycle.py serve /path/to/task
```

V1 兼容启动：

```bash
python3 <skill-dir>/scripts/comment_bridge.py start /path/to/task/index.html
```

读取：

```bash
python3 <skill-dir>/scripts/comment_bridge.py read /path/to/task/index.html
```

停止：

```bash
python3 <skill-dir>/scripts/comment_bridge.py stop /path/to/task/index.html
```

桥接约束：

- 只绑定 `127.0.0.1` 随机端口，不监听局域网或公网地址；
- 每次启动生成随机令牌，页面请求必须携带自定义令牌头；`Origin` 只接受同源 localhost 或本地 `file://` 的 `null`；
- 令牌与 PID 元数据只写入权限为 `0600` 的 `.ledger-comments/bridge.json`，命令输出必须脱敏；
- 评论 JSON 限制大小、Task ID 和基本结构，并使用原子替换写入；不执行评论文本，不自动联网；
- 服务响应在内存中注入 `ledger-comment-bridge-config`，不重写源 HTML；磁盘中的配置始终保持 `null`；
- 使用命令返回的 `http://127.0.0.1:<port>/` 在 Codex 侧边栏浏览器打开；不要用 `file://` 作为侧边栏降级；
- `read` 通过 Message ID 和 `updatedAt` 比较线程状态，只返回尚未进入权威记录的更新；权威线程较新时忽略浏览器旧状态，浏览器较新的解决/重开仍会返回，checkpoint 合并后无需用户手工清空。

## 3. 可评论对象

支持两类锚点：

### 文本选区

用户框选文本后显示“评论所选”。保存：

```text
sectionId / quote / prefix / suffix / ledgerVersion
```

`quote` 是选中文字，`prefix/suffix` 用于正文变化后的消歧。页面应尽量重新高亮匹配选区；找不到唯一匹配时显示 `STALE_TARGET`，不得把评论自动挂到其他相似文本。

### 资源对象

评论模式下可点击区块、表格、数据行、图、ER 实体、SQL/代码块、链接或证据资源。资源使用稳定 ID：

```text
sectionId / resourceId / resourceType / label / ledgerVersion
```

资源 ID 优先使用已有业务 ID、表名、图类型或元素 ID；仅在没有稳定标识时使用区块内序号。

## 4. 数据模型

内嵌 JSON：

```json
{
  "version": 1,
  "taskId": "DEV-YYYYMMDD-NNN",
  "ledgerVersion": "v0.1",
  "threads": [
    {
      "id": "CMT-...",
      "target": {
        "type": "text",
        "sectionId": "phase-P1-release",
        "resourceId": "phase-P1-release",
        "quote": "...",
        "prefix": "...",
        "suffix": "..."
      },
      "severity": "question",
      "status": "answered",
      "createdAt": "ISO-8601",
      "updatedAt": "ISO-8601",
      "messages": [
        {"id": "MSG-...", "author": "user", "createdAt": "ISO-8601", "body": "..."},
        {"id": "MSG-...", "author": "ai", "createdAt": "ISO-8601", "body": "..."}
      ],
      "change": {
        "status": "none",
        "ledgerVersion": "v0.1",
        "summary": ""
      }
    }
  ]
}
```

枚举：

- `severity`: `question / suggestion / blocker`；
- `status`: `open / answered / change-applied / needs-clarification / stale-target / resolved`；
- `author`: `user / ai`；
- `change.status`: `none / applied / rejected / blocked`。

评论和消息只追加。解决使用 `resolved`，不得删除历史；重新追问把线程改回 `open` 并追加消息。

## 5. UI 契约

V1 HTML 必须包含原有完整控件集合。V2 生成页至少包含评论抽屉、未解决计数、资源评论、文本选区评论、追评、解决/重开、复制、导出、composer、`ledger-comments-data` 和 `ledger-comment-bridge-config`；具体 DOM ID 由 `ledger-v2-shell.html` 和对应测试约束。

V1 完整控件集合：

- `comment-mode-button`：开启/关闭资源评论模式；
- `comments-button`、`comments-count`：打开讨论抽屉和显示未解决数量；
- `comment-selection-action`：文本选区评论入口；
- `comments-drawer`、`comments-filter`、`comments-list`：线程浏览、过滤和追评；
- `comment-composer`、`comment-target-preview`、`comment-severity`、`comment-textarea`、`comment-save`、`comment-cancel`；
- `comments-copy`：复制待 AI 处理的结构化评论；
- `comments-export`：导出 JSON 备份；
- `comments-close`：关闭抽屉；
- `ledger-comments-data`：`application/json` 内嵌权威评论。
- `ledger-comment-bridge-config`：默认值为 `null`；桥接运行时只包含 loopback endpoint 和临时令牌。

评论模式必须有清晰视觉状态。评论标记不得遮挡表格、图、打印内容；打印时隐藏评论 UI，但正文中已应用的修改照常打印。

## 6. AI 处理流程

用户说“我做了评论”“看看评论”或“处理台账评论”时，V2 先运行一次 `python3 <skill-dir>/scripts/lifecycle.py sync-comments <task-dir>`；它只合并 pending 并返回 actionable threads，不制造门禁尝试。V1 先运行 `comment_bridge.py read`。桥接不可用时才要求用户使用“复制待处理评论”。复制内容的兼容格式仍为：

```text
处理台账评论：<结构化 payload>
```

AI 对每条线程：

1. 打开对应结构化任务记录；V1 才打开源 HTML。核对 Task ID、版本、sectionId/resourceId 和 quote/context。
2. 目标不存在或不唯一：追加 AI 追评，状态设为 `stale-target` 或 `needs-clarification`，不修改正文。
3. 仅需解释：追加 AI 回复，状态设为 `answered`；不擅自改正文。
4. 内容确实不清楚、错误或不完整：V2 修改对应 Phase JSON、递增任务版本并追加事件；V1 修改正文。追加 AI 回复说明“改了什么、为什么、证据、影响”，状态设为 `change-applied`。
5. 用户明确要求不改或建议不采纳：追加理由，`change.status=rejected`，保留原文。
6. V2 将完整线程和 AI 新消息写入 `comments.json`，V1 写入 `ledger-comments-data`；按 ID 去重，永不覆盖或删除旧消息。
7. 修改后运行适用 checkpoint/gate 并重新生成 V2 HTML；在回复中报告校验结果。

AI 不自动把线程标为 `resolved`。通常由用户阅读回复/修改后在 HTML 中解决；只有用户明确说“解决这些评论”时才可批量解决。

## 7. 门禁关系

- `blocker + 非 resolved` 的评论会阻止其目标所属 Phase 的需求/方案/分支/完成门禁。
- `question` 和 `suggestion` 不自动阻止门禁，但请求确认前应显式报告未解决数量。
- 已确认内容因评论发生语义修改时，按状态机回到对应需求或方案评审，不能只改文字而维持原确认。
- 桥接 pending 中未解决的 blocker 与内嵌 blocker 等价，会阻止对应门禁。桥接不可用时，页面必须明显显示“待同步给 AI”数量，用户确认门禁前 AI 才需要询问是否还有未复制评论。

## 8. 安全与隐私

- 评论默认只存本机；只有点击复制/导出并由用户发送时才离开页面。
- payload 不包含 Cookie、token、密码、完整业务对象或未脱敏日志。
- 长引用应截断并保留 section/resource 锚点；不要复制整张表或整份文档。
- 导出文件名包含 Task ID 和时间，不自动上传。
