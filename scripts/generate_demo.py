#!/usr/bin/env python3
"""Generate the canonical multi-phase lifecycle ledger demo."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


AS_OF = "2026-08-21"
TASK_ID = "DEV-20260821-001"

PHASES = (
    {
        "id": "P1",
        "order": "1",
        "name": "商户进件",
        "parent": "NONE",
        "parent_name": "远端基线",
        "branch": "feat/dev-20260821-001-p1-onboarding",
        "parent_branch": "origin/master",
        "base": "1111111",
        "parent_candidate": "NONE",
        "head": "a1b2c3d4",
        "candidate": "a1b2c3d4",
        "entry": "MerchantApplyController#create",
        "module": "merchant-onboarding",
        "aggregate": "MerchantApplication",
        "entity": "MerchantApplicationItem",
        "table": "wx_merchant_application",
        "secondary": "wx_merchant_application_log",
        "parent_table": "merchant_profile",
        "api": "POST /api/wechat/merchant-applications",
        "event": "merchant.application.changed",
        "summary": "建立商户微信支付进件能力，保存申请快照、材料状态和微信侧申请单号，为后续支付配置提供唯一商户身份。",
        "dependency": "不依赖后续阶段；向 P2 提供 merchantApplicationId、wechatMerchantId 和 APPROVED 状态。",
    },
    {
        "id": "P2",
        "order": "2",
        "name": "微信支付",
        "parent": "P1",
        "parent_name": "商户进件",
        "branch": "feat/dev-20260821-001-p2-wechat-pay",
        "parent_branch": "feat/dev-20260821-001-p1-onboarding",
        "base": "a1b2c3d4",
        "parent_candidate": "a1b2c3d4",
        "head": "b2c3d4e5",
        "candidate": "b2c3d4e5",
        "entry": "WechatPayController#createOrder",
        "module": "wechat-payment",
        "aggregate": "WechatPaymentOrder",
        "entity": "WechatPaymentAttempt",
        "table": "wx_payment_order",
        "secondary": "wx_payment_attempt",
        "parent_table": "wx_merchant_application",
        "api": "POST /api/wechat/payments",
        "event": "wechat.payment.result",
        "summary": "在已通过进件的商户下创建微信支付订单，处理预下单、支付回调、查询和退款前置状态，为连续包月首扣复用稳定支付链路。",
        "dependency": "依赖 P1 的 APPROVED 商户、wechatMerchantId 和支付权限；P1 回滚时停止新订单创建。",
    },
    {
        "id": "P3",
        "order": "3",
        "name": "连续包月",
        "parent": "P2",
        "parent_name": "微信支付",
        "branch": "feat/dev-20260821-001-p3-recurring",
        "parent_branch": "feat/dev-20260821-001-p2-wechat-pay",
        "base": "b2c3d4e5",
        "parent_candidate": "b2c3d4e5",
        "head": "c3d4e5f6",
        "candidate": "c3d4e5f6",
        "entry": "RecurringContractController#sign",
        "module": "wechat-recurring",
        "aggregate": "RecurringContract",
        "entity": "RecurringCharge",
        "table": "wx_recurring_contract",
        "secondary": "wx_recurring_charge",
        "parent_table": "wx_payment_order",
        "api": "POST /api/wechat/recurring-contracts",
        "event": "wechat.recurring.charge",
        "summary": "基于 P2 支付能力完成签约、首扣、周期扣款、解约和失败重试，并形成可审计的合同与扣款记录。",
        "dependency": "依赖 P2 的支付商户配置、支付订单能力和回调验签；P2 不可用时冻结新签约并保留存量合同查询。",
    },
)

IMPACTS = (
    ("ui", "用户与 UI"),
    ("frontend", "前端代码"),
    ("backend", "后端服务"),
    ("api", "API / RPC 契约"),
    ("data", "数据与存储"),
    ("async", "消息与异步任务"),
    ("config", "配置、开关与密钥引用"),
    ("auth", "权限、租户与数据隔离"),
    ("upstream", "上游调用方"),
    ("downstream", "下游依赖"),
    ("observability", "监控、告警与审计"),
    ("capacity", "容量、性能与限流"),
    ("release", "发布、兼容与回滚"),
    ("security", "安全、隐私与合规"),
)


def artifact_attrs(kind: str, evidence: int = 2) -> str:
    return f'data-artifact="{kind}" data-status="complete" data-evidence-count="{evidence}" data-as-of="{AS_OF}"'


def section_toc(toc_id: str, aria_label: str, groups: list[tuple[str, list[tuple[str, str, bool]]]]) -> str:
    rendered_groups = []
    for group_name, links in groups:
        rendered_links = "".join(
            f'<a class="toc-link{" release-link" if highlighted else ""}" href="#{target}">{label}</a>'
            for target, label, highlighted in links
        )
        rendered_groups.append(f'<div class="toc-group"><b>{group_name}</b>{rendered_links}</div>')
    return f'<nav id="{toc_id}" class="section-toc" data-section-toc aria-label="{aria_label}"><span class="toc-title">目录</span>{"".join(rendered_groups)}</nav>'


def phase_toc(phase_id: str) -> str:
    prefix = f"phase-{phase_id}-"
    return section_toc(
        f"toc-phase-{phase_id}",
        f"{phase_id} 区块目录",
        [
            ("需求", [
                (prefix + "context", "现状", False),
                (prefix + "requirements", "需求与验收", False),
                (prefix + "functional-breakdown", "功能拆解", False),
            ]),
            ("方案", [
                (prefix + "architecture", "应用架构", False),
                (prefix + "code-architecture", "代码架构", False),
                (prefix + "ui", "UI", False),
                (prefix + "data-architecture", "数据架构", False),
                (prefix + "domain-model", "领域模型", False),
                (prefix + "persistence-model", "ER 图", False),
                (prefix + "data-inventory", "数据清单", False),
                (prefix + "state-machine", "状态机", False),
                (prefix + "sequence-main", "主流程", False),
                (prefix + "sequence-recovery", "异常恢复", False),
                (prefix + "impact", "影响范围", False),
            ]),
            ("交付", [
                (prefix + "branch", "分支谱系", False),
                (prefix + "release", "上线资源", True),
                (prefix + "validation", "测试证据", False),
                (prefix + "traceability", "需求追踪", False),
            ]),
        ],
    )


def diagram(nodes: list[str], caption: str, kind: str | None = None) -> str:
    flow = '<span class="arrow">→</span>'.join(f'<span class="node">{node}</span>' for node in nodes)
    kind_attr = f' data-diagram-kind="{kind}"' if kind else ""
    return f'<div class="diagram" data-diagram{kind_attr} role="img" aria-label="{caption}"><div class="flow">{flow}</div><p>{caption}</p></div>'


def data_architecture(phase: dict[str, str]) -> str:
    return f'''
    <div class="diagram data-architecture" data-diagram data-diagram-kind="data-architecture" role="img" aria-label="{phase['id']} 数据架构读写与恢复链路">
      <div class="data-lane"><b>命令写链路</b><div class="flow"><span class="node">API / Command</span><span class="arrow">→</span><span class="node">事务 T1<br>{phase['table']} + {phase['secondary']}</span><span class="arrow">→</span><span class="node">afterCommit<br>{phase['event']}</span><span class="arrow">→</span><span class="node">Worker / 微信平台</span><span class="arrow">→</span><span class="node">事务 T2<br>状态 + operation_audit_log</span></div></div>
      <div class="data-lane"><b>查询读链路</b><div class="flow"><span class="node">Query API</span><span class="arrow">→</span><span class="node">{phase['table']} 主数据源</span><span class="arrow">+</span><span class="node">{phase['secondary']} 明细</span><span class="arrow">→</span><span class="node">状态 / 失败原因 / 进度</span></div></div>
      <div class="data-lane"><b>技术恢复链路</b><div class="flow"><span class="node">Retry / 补扫 Job</span><span class="arrow">→</span><span class="node">{phase['secondary']}.next_retry_at</span><span class="arrow">→</span><span class="node">重新投递 / 微信对账</span><span class="arrow">→</span><span class="node">补偿 + 审计</span></div></div>
      <p>{phase['table']} 是本 Phase 权威主数据源；写入方为 Command/Worker Repository，查询方为 Query API 与对账 Job。事务边界、异步边界和中断恢复入口均显式标注。</p>
    </div>'''


def entity_box(name: str, title: str, fields: list[str]) -> str:
    items = "".join(f"<li>{field}</li>" for field in fields)
    return f'<article class="er-entity" data-entity="{name}"><h4>{title}</h4><code>{name}</code><ul>{items}</ul></article>'


def er_diagram(phase: dict[str, str]) -> str:
    parent = entity_box(phase["parent_table"], "父域/既有主数据", [
        "PK id BIGINT", "UK tenant_id + external_no", "status VARCHAR", "updated_at DATETIME",
    ])
    main = entity_box(phase["table"], f'{phase["aggregate"]} 主表', [
        "PK id BIGINT", "UK tenant_id + request_id", f"REF parent_id → {phase['parent_table']}.id",
        "status VARCHAR", "version INT", "created_at / updated_at",
    ])
    secondary = entity_box(phase["secondary"], f'{phase["entity"]} 明细表', [
        "PK id BIGINT", f"FK aggregate_id → {phase['table']}.id", "UK aggregate_id + attempt_no",
        "IDX status + next_retry_at", "error_code / error_message", "created_at / updated_at",
    ])
    audit = entity_box("operation_audit_log", "统一审计表", [
        "PK id BIGINT", f"REF aggregate_id → {phase['table']}.id", "UK aggregate_id + version + event_type",
        "operator_id / trace_id", "before_value / after_value", "created_at DATETIME",
    ])
    return f'''
    <div class="diagram erd" data-diagram data-diagram-kind="erd" role="img" aria-label="{phase['id']} 表级 ER 图">
      <div class="er-entities">{parent}{main}{secondary}{audit}</div>
      <div class="er-links">
        <div class="er-link logical" data-relationship="{phase['parent_table']}|1:N|{phase['table']}|logical"><code>{phase['parent_table']}</code><b>1</b><span>逻辑引用 REF · 父域不建物理外键</span><b>N</b><code>{phase['table']}</code></div>
        <div class="er-link physical" data-relationship="{phase['table']}|1:N|{phase['secondary']}|physical"><code>{phase['table']}</code><b>1</b><span>物理外键 FK · ON DELETE RESTRICT</span><b>N</b><code>{phase['secondary']}</code></div>
        <div class="er-link logical" data-relationship="{phase['table']}|1:N|operation_audit_log|logical"><code>{phase['table']}</code><b>1</b><span>逻辑引用 REF · 只追加审计</span><b>N</b><code>operation_audit_log</code></div>
      </div>
      <p><b>基数：</b>父域实体 1:N 本阶段主表；主表 1:N 明细；主表 1:N 审计。跨域和审计采用逻辑引用，同库主从明细采用物理外键。图中展示主键、唯一键、关键索引、写入关系与证据映射。</p>
    </div>'''


def impact_rows(phase: dict[str, str]) -> str:
    rows = []
    for code, label in IMPACTS:
        decision = "受影响" if code in {"backend", "api", "data", "async", "observability", "release", "security"} else "不受影响"
        rows.append(
            f'<tr data-impact-category="{code}"><td>{label}</td><td>{phase["module"]}</td><td>{decision}</td>'
            f'<td>按 {phase["id"]} 边界实施；不受影响项保持既有契约并以基线回归证明。</td>'
            f'<td>向前兼容，开关关闭时回到阶段前行为。</td><td>{phase["id"]}-TC-001 与契约回归</td>'
            f'<td>成功率、延迟、错误码告警；异常关闭开关并回滚候选 SHA。</td>'
            f'<td>证据：origin/master@1111111、{phase["entry"]}</td></tr>'
        )
    return "".join(rows)


def functional_breakdown(phase: dict[str, str]) -> str:
    pid = phase["id"]
    return f'''
  <section class="card" id="phase-{pid}-functional-breakdown" {artifact_attrs('functional-breakdown')}>
    <h3>功能拆解：角色、入口与生命周期</h3>
    {diagram(["运营发起", "系统校验", "自动执行", "用户可见", "异常恢复"], f"{pid} 功能生命周期：人工入口触发后，由系统自动推进并向操作角色展示确定结果")}
    <div class="table-wrap"><table><thead><tr><th>REQ</th><th>角色</th><th>生命周期节点</th><th>入口 / 触发</th><th>操作与系统行为</th><th>用户可见结果</th><th>人工 / 自动</th><th>异常路径</th></tr></thead><tbody>
      <tr><td>{pid}-REQ-001</td><td>运营管理员</td><td>创建</td><td><code>{phase['entry']}</code> 页面或 API 入口；点击提交触发</td><td>填写必要资料并提交，系统进行租户、权限、幂等键与字段完整性校验。</td><td>立即看到受理结果、申请编号和下一步提示；重复提交返回同一业务对象。</td><td>人工发起，自动校验</td><td>校验失败停留原节点，明确字段错误，不产生半成品写入。</td></tr>
      <tr><td>{pid}-REQ-001</td><td>领域服务</td><td>受理</td><td><code>{phase['api']}</code> 命令进入后触发</td><td>在事务内写入 <code>{phase['table']}</code> 主数据与 <code>{phase['secondary']}</code> 初始明细，并记录版本。</td><td>查询接口返回处理中状态、创建时间和当前阶段。</td><td>系统自动</td><td>事务失败整体回滚；同一 request_id 由唯一约束兜底。</td></tr>
      <tr><td>{pid}-REQ-001</td><td>异步执行器</td><td>执行</td><td>事务提交后的 <code>{phase['event']}</code> 事件触发</td><td>调用微信侧或下游能力，保存外部单号、执行次数、错误码与下一次重试时间。</td><td>进度页可见处理中、成功或可行动失败原因。</td><td>系统自动</td><td>短暂失败自动重试；超过阈值进入待人工处理并保留补扫入口。</td></tr>
      <tr><td>{pid}-REQ-002</td><td>商户 / 最终用户</td><td>确认与完成</td><td>查询页、回调或下一 Phase 的稳定契约触发</td><td>读取权威主数据源并校验终态，只有满足不变量后才向后续阶段暴露可用标识。</td><td>看到成功状态、完成时间和后续可执行动作，不暴露内部技术状态。</td><td>用户查看，系统自动派生</td><td>回调乱序按版本忽略；查询事实与本地不一致时进入对账而非直接覆盖。</td></tr>
      <tr><td>{pid}-REQ-001</td><td>值班人员</td><td>异常恢复</td><td>告警、补扫 Job 或人工“重试”入口触发</td><td>根据审计记录执行重试、补偿、对账或关闭入口；所有人工操作记录 operator_id 与 trace_id。</td><td>运营可见恢复结果和最新失败原因，商户只见稳定业务状态。</td><td>自动补扫，必要时人工确认</td><td>恢复仍失败则保持可重试状态并升级告警，禁止跨越非法状态直接完成。</td></tr>
    </tbody></table></div>
    <p class="evidence"><b>证据：</b>REQ 与功能节点逐项映射到真实入口 <code>{phase['entry']}</code>、契约 <code>{phase['api']}</code>、主数据 <code>{phase['table']}</code> 和事件 <code>{phase['event']}</code>；as-of {AS_OF}。</p>
  </section>'''


def phase_panel(phase: dict[str, str]) -> str:
    pid = phase["id"]
    return f'''
<section class="tab-panel" id="panel-phase-{pid}" role="tabpanel" data-panel="phase-{pid}"
  data-phase-id="{pid}" data-phase-order="{phase['order']}" data-phase-name="{phase['name']}"
  data-phase-status="DONE" data-parent-phase="{phase['parent']}">
  <div class="panel-head"><div><span class="eyebrow">{pid} · {phase['name']}</span><h2>{phase['name']}</h2><p>{phase['summary']}</p></div><span class="pill done">DONE</span></div>
  {phase_toc(pid)}

  <section class="card" id="phase-{pid}-context" {artifact_attrs('context')}>
    <h3>现状与范围</h3>
    <p><b>现状：</b>当前系统没有由本阶段统一承载的完整能力，相关动作分散且缺少可追踪状态。<b>真实入口：</b><code>{phase['entry']}</code>，代码位于 <code>{phase['module']}</code>，基线为 <code>origin/master@1111111</code>。</p>
    <p><b>痛点：</b>上下游无法获得稳定状态、失败原因和恢复进度。<b>目标：</b>{phase['summary']} <b>非目标：</b>本阶段不提前实现后续 Phase 的业务规则，也不修改无关支付渠道。</p>
    <p class="evidence"><b>证据：</b>代码入口与调用链调研、Schema 文件和接口文档，as-of {AS_OF}，高置信；跨阶段依赖：{phase['dependency']}</p>
  </section>

  <section class="card" id="phase-{pid}-requirements" {artifact_attrs('requirements')}>
    <h3>需求与验收</h3>
    <div class="table-wrap"><table><thead><tr><th>REQ-ID</th><th>描述</th><th>验收标准</th><th>优先级</th><th>状态</th><th>证据</th></tr></thead><tbody>
      <tr><td>{pid}-REQ-001</td><td>{phase['summary']}</td><td>正常、重复、失败和恢复路径都有确定结果，可由接口和日志核验。</td><td>P0</td><td>已确认</td><td>需求确认记录 v1.0</td></tr>
      <tr><td>{pid}-REQ-002</td><td>提供跨阶段稳定契约</td><td>{phase['dependency']}</td><td>P0</td><td>已确认</td><td>集成依赖矩阵 INT-001</td></tr>
    </tbody></table></div>
  </section>

  {functional_breakdown(phase)}

  <section class="card" id="phase-{pid}-architecture" {artifact_attrs('application-architecture')}>
    <h3>应用架构</h3>
    {diagram(['运营/用户端', 'API/BFF', phase['module'], '领域服务', '数据与微信平台'], f'{pid} 应用组件职责、调用边界与同步/异步依赖')}
    <p>职责由 API 层完成鉴权和协议转换，应用模块负责编排，领域服务维护业务不变量，Repository 隔离数据访问，Adapter 隔离微信外部依赖。同步边界覆盖命令校验，异步边界使用事件 <code>{phase['event']}</code>。证据：模块依赖文件、入口调用链和基线 SHA。</p>
  </section>

  <section class="card" id="phase-{pid}-code-architecture" {artifact_attrs('code-architecture')}>
    <h3>代码架构与真实调用链</h3>
    {diagram([phase['entry'], f'{phase["module"]}.application', f'{phase["module"]}.domain', f'{phase["module"]}.infrastructure'], f'{pid} 代码调用链与依赖方向：接口层只能向应用层，应用层编排领域层，基础设施实现反向接口')}
    <div class="table-wrap"><table><thead><tr><th>仓库</th><th>模块</th><th>入口</th><th>调用链</th><th>依赖方向</th><th>预计文件</th><th>证据</th></tr></thead><tbody>
      <tr><td>payment-service</td><td>{phase['module']}</td><td>{phase['entry']}</td><td>Controller → CommandHandler → Aggregate → Repository/WechatAdapter</td><td>adapter → application → domain；domain 不反向依赖基础设施</td><td><code>src/{phase['module']}/application</code>、<code>domain</code>、<code>infrastructure</code></td><td>rg 调用链，origin/master@1111111</td></tr>
      <tr><td>merchant-pc-fe</td><td>{phase['module']}-ui</td><td>routes/{phase['module']}</td><td>Page → service → {phase['api']}</td><td>页面依赖 typed service，不直接拼接微信协议</td><td><code>src/pages/{phase['module']}</code></td><td>路由与请求封装，origin/master@2222222</td></tr>
    </tbody></table></div>
  </section>

  <section class="card" id="phase-{pid}-ui" {artifact_attrs('ui-gate', 1)}>
    <h3>UI 设计门禁</h3>
    <p><b>适用性：</b>适用，新增后台阶段状态页，但沿用既有表格、表单、抽屉和状态 Token。<b>理由：</b>用户需要查看提交、处理中、成功和失败。响应式以桌面为主，窄屏表格内部滚动；无障碍包含键盘焦点、错误摘要和可读状态文本；Reduced Motion 下关闭位移动效。证据：现有后台组件清单与页面截图，as-of {AS_OF}。</p>
  </section>

  <section class="card" id="phase-{pid}-data-architecture" {artifact_attrs('data-architecture', 3)}>
    <h3>数据架构与完整读写链路</h3>
    {data_architecture(phase)}
    <p><b>证据：</b>Command Handler、事务注解、Repository、消息发布点、Query Mapper、Retry/补扫/对账 Job，基线 <code>origin/master@1111111</code>。主数据源、写入方、查询方、事务 T1/T2 和异步边界均与下方 ER 图及数据资产清单使用相同对象名。</p>
  </section>

  <section class="card" id="phase-{pid}-domain-model" {artifact_attrs('domain-model')}>
    <h3>领域模型</h3>
    {diagram([phase['aggregate'] + ' 聚合根', phase['entity'] + ' 实体', 'WechatGateway 领域端口', 'AuditEvent 领域事件'], f'{pid} 领域对象、聚合边界、实体关系和所有权')}
    <p><code>{phase['aggregate']}</code> 是聚合根并拥有状态转换；<code>{phase['entity']}</code> 记录执行明细。规则与不变量：租户必须一致、外部请求号唯一、终态不可逆、同一业务动作只能成功一次。所有权归 {phase['module']}，微信协议由端口隔离。证据：领域服务与既有测试，基线 origin/master@1111111。</p>
  </section>

  <section class="card" id="phase-{pid}-persistence-model" {artifact_attrs('persistence-model')}>
    <h3>表级 ER 图</h3>
    {er_diagram(phase)}
    <p>ER 图以真实表名和字段为准：主表使用主键 id、业务唯一键 UK(tenant_id, request_id) 与状态索引；明细表通过 aggregate_id 形成 1:N 物理关系；父 Phase 表和统一审计表通过逻辑引用关联。写入方为 {phase['module']} Repository，物理外键仅限同库主从表，跨域关系不建 FK。证据：Schema proposal、DDL、Mapper 和查询索引调研。</p>
  </section>

  <section class="card" id="phase-{pid}-data-inventory" {artifact_attrs('data-inventory', 3)}>
    <h3>数据资产与涉及表清单</h3>
    <div class="table-wrap"><table><thead><tr><th>类型</th><th>数据源</th><th>对象名</th><th>新增或既有</th><th>业务职责</th><th>操作类型</th><th>主数据与所有者</th><th>写入方</th><th>读取方</th><th>PK/UK/索引</th><th>规模热点</th><th>迁移/保留/清理</th><th>回滚限制</th><th>证据</th></tr></thead><tbody>
      <tr data-object="{phase['parent_table']}" data-object-kind="table"><td>MySQL</td><td>父 Phase / 既有域</td><td>{phase['parent_table']}</td><td>既有不变</td><td>父域权威主数据，仅通过引用 ID 和稳定状态读取</td><td>Select</td><td>父 Phase / 父领域所有</td><td>父域 Repository</td><td>{phase['module']} Command 校验</td><td>PK(id)、UK(tenant,external_no)、IDX(status)</td><td>只按主键/唯一键读取，无全表扫描</td><td>沿用父域保留与清理策略</td><td>本 Phase 不修改或回滚父表</td><td>父 Phase Schema 与候选 SHA</td></tr>
      <tr data-object="{phase['table']}" data-object-kind="table"><td>MySQL</td><td>payment.{phase['module']}</td><td>{phase['table']}</td><td>新增</td><td>聚合主数据与权威状态</td><td>Insert/Update/Select</td><td>{phase['aggregate']}，所有者 {phase['module']}</td><td>Command Repository</td><td>Query API、对账 Job</td><td>PK(id)、UK(tenant,request)、IDX(status,updated)</td><td>预计每日 5 万，状态索引防全表扫描</td><td>无存量回填；在线 365 天后归档清理</td><td>写入后不可直接 Drop，先关开关并导出</td><td>schema.sql@1111111</td></tr>
      <tr data-object="{phase['secondary']}" data-object-kind="table"><td>MySQL</td><td>payment.{phase['module']}</td><td>{phase['secondary']}</td><td>新增</td><td>执行尝试、快照、失败与重试</td><td>Insert/Update/Select</td><td>{phase['entity']}，主数据归本 Phase</td><td>Worker Repository</td><td>结果查询、补扫 Job</td><td>PK(id)、UK(aggregate,attempt)、IDX(retry_at)</td><td>主表约 1:N，按 retry_at 控制热点</td><td>随主表归档，审计独立保留</td><td>存在未完成任务时禁止删除</td><td>mapper 与 Job 调研证据</td></tr>
      <tr data-object="operation_audit_log" data-object-kind="table"><td>MySQL</td><td>audit.common</td><td>operation_audit_log</td><td>既有扩展/复用</td><td>只追加保存状态变化、操作者和 Trace</td><td>Insert/Select</td><td>审计域所有，本阶段只追加</td><td>事务 T2 Audit Repository</td><td>审计查询与问题定位</td><td>PK(id)、UK(aggregate,version,event)、IDX(trace_id)</td><td>按月分区，避免聚合查询热点</td><td>服从审计保留策略，不随业务表清理</td><td>业务代码回滚不删除审计记录</td><td>audit mapper 与治理规则</td></tr>
      <tr data-object="{phase['event']}" data-object-kind="topic"><td>MQ</td><td>payment-event</td><td>{phase['event']}</td><td>新增 Topic/事件类型</td><td>异步执行与跨阶段通知</td><td>Publish/Consume</td><td>数据库状态是主数据，消息仅触发</td><td>{phase['module']} afterCommit</td><td>本阶段 Worker、下一 Phase</td><td>幂等键 aggregateId+version</td><td>峰值 100/s，消费限流 50/s</td><td>保留 3 天；失败进入重试和补扫</td><td>停消费者不删除主数据</td><td>消息契约 EVT-{pid}-001</td></tr>
    </tbody></table></div>
  </section>

  <section class="card" id="phase-{pid}-state-machine" {artifact_attrs('state-machine')}>
    <h3>业务状态机</h3>
    {diagram(['INIT', 'PROCESSING', 'SUCCEEDED / RETRY_WAIT', 'FAILED / CANCELLED'], f'{pid} 状态机：命令触发合法转换，成功或失败为终态')}
    <p>状态由命令或微信回调触发；INIT 可进入 PROCESSING，临时失败进入 RETRY_WAIT，成功进入 SUCCEEDED，明确业务失败进入 FAILED。终态不可逆；非法重复回调通过版本号和幂等键拒绝。取消只允许在外部受理前。证据：状态枚举、转换表和单元测试。</p>
  </section>

  <section class="card" id="phase-{pid}-sequence-main" {artifact_attrs('sequence-main')}>
    <h3>主业务全生命周期流程</h3>
    {diagram(['用户创建', 'API 校验', 'T1 写入聚合与明细', 'afterCommit 异步执行', '微信结果', '查询并完成'], f'{pid} 主流程：创建、校验、事务写入、异步执行、查询和完成')}
    <p>创建请求携带租户和幂等键；API 完成权限与参数校验，事务 T1 写入主表和明细，提交后发送异步事件。Worker 执行微信调用并在独立事务写结果，查询接口只从本阶段主数据返回状态。证据：接口契约、事务注解、消息发布点和查询 Mapper。</p>
  </section>

  <section class="card" id="phase-{pid}-sequence-recovery" {artifact_attrs('sequence-recovery')}>
    <h3>失败、重试与恢复流程</h3>
    {diagram(['重复请求返回原记录', '调用失败持久化', '退避重试', '补扫过期任务', '对账微信结果', '补偿或终态失败'], f'{pid} 异常恢复：失败、重试、补偿、补扫、对账和中断恢复')}
    <p>重复请求通过唯一键返回原记录；可重试失败先持久化 errorCode、attempt 和 nextRetryAt，再按退避计划重试。消息丢失由补扫 Job 恢复，进程中断通过租约过期重新抢占，对账任务核对微信最终状态。不可自动恢复时执行人工补偿并进入终态失败，保留审计证据。</p>
  </section>

  <section class="card" id="phase-{pid}-impact" {artifact_attrs('impact', 4)}>
    <h3>14 类影响范围矩阵</h3>
    <div class="table-wrap"><table><thead><tr><th>类别</th><th>对象</th><th>判定</th><th>变化或理由</th><th>兼容</th><th>验证</th><th>监控与回滚</th><th>证据</th></tr></thead><tbody>{impact_rows(phase)}</tbody></table></div>
  </section>

  <section class="card" id="phase-{pid}-branch" {artifact_attrs('branch', 2)}
    data-branch-name="{phase['branch']}" data-base-sha="{phase['base']}"
    data-parent-candidate-sha="{phase['parent_candidate']}" data-head-sha="{phase['head']}"
    data-candidate-sha="{phase['candidate']}" data-sync-status="CURRENT">
    <h3>Phase 分支与基线谱系</h3>
    <div class="table-wrap"><table><thead><tr><th>phaseId</th><th>parentPhaseId</th><th>branch</th><th>parentBranch</th><th>parentCandidateSHA</th><th>baseSHA</th><th>headSHA</th><th>syncStatus</th><th>证据</th></tr></thead><tbody>
      <tr><td>{pid}</td><td>{phase['parent']}</td><td>{phase['branch']}</td><td>{phase['parent_branch']}</td><td>{phase['parent_candidate']}</td><td>{phase['base']}</td><td>{phase['head']}</td><td>CURRENT</td><td>git merge-base、worktree list、remote SHA</td></tr>
    </tbody></table></div>
    <p>{pid} 从 {phase['parent_name']} 的确切 SHA 创建；父阶段产生新候选时先标记 STALE_PARENT，再 merge 父提交并重新验证，禁止静默 rebase 和 force push。</p>
  </section>

  <section class="card" id="phase-{pid}-release" {artifact_attrs('release', 4)}>
    <h3>上线资源与顺序</h3>
    <div class="table-wrap"><table><thead><tr><th>资源</th><th>内容</th><th>负责人</th><th>部署顺序</th><th>验证</th><th>回滚</th><th>证据</th></tr></thead><tbody>
      <tr><td>DDL</td><td>新增 {phase['table']}、{phase['secondary']}；正向、校验、回滚 SQL 单独评审</td><td>DBA/用户</td><td>1</td><td>SHOW CREATE TABLE 与索引检查</td><td>无业务写入时回滚；有数据时仅关入口</td><td>SQL-{pid}-001</td></tr>
      <tr><td>配置/开关</td><td><code>{phase['module']}.enabled</code> 默认关闭；微信密钥只引用配置中心</td><td>服务负责人</td><td>2</td><td>配置读取和租户灰度</td><td>关闭开关</td><td>CFG-{pid}-001</td></tr>
      <tr><td>消息/定时任务</td><td>{phase['event']}、重试 Job、补扫 Job、对账 Job</td><td>后端负责人</td><td>3</td><td>消息积压、定时任务锁和告警</td><td>停消费者与 Job，不删除数据</td><td>EVT-{pid}-001</td></tr>
      <tr><td>应用部署</td><td>{phase['branch']}@{phase['candidate']}</td><td>发布人</td><td>4</td><td>镜像 SHA、实例健康、冒烟</td><td>上一制品并保持新表兼容</td><td>DEPLOY-{pid}-001</td></tr>
    </tbody></table></div>
    <p>部署顺序为 DDL → 配置与开关 → 消息和定时任务 → 应用 → 灰度开关。验证覆盖资源、版本和业务状态；回滚优先关开关，再回滚代码，数据表保留以支持兼容与审计。负责人和证据必须在执行前确认。</p>
  </section>

  <section class="card" id="phase-{pid}-validation" {artifact_attrs('validation', 3)}>
    <h3>测试与实际证据</h3>
    <div class="table-wrap"><table><thead><tr><th>TC-ID</th><th>REQ-ID</th><th>模块</th><th>前置</th><th>操作路径</th><th>预期</th><th>实际</th><th>版本</th><th>状态</th><th>证据</th></tr></thead><tbody>
      <tr><td>{pid}-TC-001</td><td>{pid}-REQ-001</td><td>{phase['module']}</td><td>依赖 Phase 已满足、开关开启</td><td>页面/API 创建 → 异步执行 → 查询</td><td>进入成功终态且审计完整</td><td>示例结果：通过</td><td>{phase['candidate']}</td><td>PASS</td><td>截图-{pid}-001、LOG-{pid}-001</td></tr>
      <tr><td>{pid}-TC-002</td><td>{pid}-REQ-002</td><td>恢复链路</td><td>模拟微信超时与消息丢失</td><td>失败 → 重试 → 补扫 → 对账</td><td>不重复执行并可中断恢复</td><td>示例结果：通过</td><td>{phase['candidate']}</td><td>PASS</td><td>集成测试与脱敏日志</td></tr>
    </tbody></table></div>
  </section>

  <section class="card" id="phase-{pid}-traceability" {artifact_attrs('traceability', 3)}>
    <h3>需求追踪矩阵</h3>
    <div class="table-wrap"><table><thead><tr><th>REQ</th><th>架构</th><th>代码</th><th>数据</th><th>测试</th><th>发布</th><th>证据</th></tr></thead><tbody>
      <tr><td>{pid}-REQ-001</td><td>ARCH-{pid}-APP / ARCH-{pid}-CODE</td><td>{phase['module']} application/domain/infrastructure</td><td>{phase['table']}、{phase['secondary']}、{phase['event']}</td><td>{pid}-TC-001/002</td><td>SQL/CFG/DEPLOY-{pid}-001</td><td>基线、候选 SHA、截图和日志</td></tr>
      <tr><td>{pid}-REQ-002</td><td>INT-{pid}-DEPENDENCY</td><td>typed contract 与兼容保护</td><td>跨阶段 ID、状态和事件</td><td>INT-TC-{pid}</td><td>按 Phase 依赖顺序发布</td><td>集成矩阵与回归记录</td></tr>
    </tbody></table></div>
  </section>
</section>'''


def embedded_comments_json() -> str:
    data = {
        "version": 1,
        "taskId": TASK_ID,
        "ledgerVersion": "v2.0",
        "threads": [
            {
                "id": "CMT-DEMO-001",
                "target": {
                    "type": "text",
                    "sectionId": "phase-P2-release",
                    "resourceId": "phase-P2-release",
                    "quote": "回滚优先关开关，再回滚代码",
                    "prefix": "验证覆盖资源、版本和业务状态；",
                    "suffix": "，数据表保留以支持兼容与审计。",
                    "label": "P2 上线资源与顺序",
                },
                "severity": "question",
                "status": "answered",
                "createdAt": "2026-08-21T10:00:00+08:00",
                "updatedAt": "2026-08-21T10:08:00+08:00",
                "messages": [
                    {
                        "id": "MSG-DEMO-001-U",
                        "author": "user",
                        "createdAt": "2026-08-21T10:00:00+08:00",
                        "body": "为什么这里要先关闭开关，而不是直接回滚代码？",
                    },
                    {
                        "id": "MSG-DEMO-001-A",
                        "author": "ai",
                        "createdAt": "2026-08-21T10:08:00+08:00",
                        "body": "先关闭入口可以立即停止新增写入，避免代码回滚窗口内继续产生新数据；随后再回滚应用，并保留兼容表结构用于读取和审计。当前正文表述正确，因此本次只追评说明，没有修改正文。",
                    },
                ],
                "change": {"status": "none", "ledgerVersion": "v2.0", "summary": "仅解释，未修改正文"},
            }
        ],
    }
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def comments_runtime_script() -> str:
    return r'''
const commentRoot = document.documentElement;
const commentTaskId = commentRoot.dataset.taskId;
const commentLedgerVersion = commentRoot.dataset.ledgerVersion;
const embeddedCommentNode = document.getElementById('ledger-comments-data');
const storageKey = 'lifecycle-ledger-comments:' + commentTaskId + ':' + location.pathname;
const commentBridge = globalThis.__LEDGER_COMMENT_BRIDGE__ || null;
const embeddedComments = JSON.parse(embeddedCommentNode.textContent || '{"version":1,"threads":[]}');
const embeddedThreadIds = new Set((embeddedComments.threads || []).map(thread => thread.id));
const embeddedMessageIds = new Set((embeddedComments.threads || []).flatMap(thread => (thread.messages || []).map(message => message.id)));
let storageAvailable = true;
let bridgeStatus = commentBridge ? '自动同步待连接' : '手动同步模式';
let localComments = {version:1, taskId:commentTaskId, ledgerVersion:commentLedgerVersion, threads:[]};
try {
  const stored = localStorage.getItem(storageKey);
  if (stored) localComments = JSON.parse(stored);
} catch (error) {
  storageAvailable = false;
}

function timeValue(value) { const parsed = Date.parse(value || ''); return Number.isFinite(parsed) ? parsed : 0; }
function newer(left, right) {
  return timeValue(left.updatedAt || left.createdAt) >= timeValue(right.updatedAt || right.createdAt) ? left : right;
}
function mergeThreads(embedded, local) {
  const map = new Map();
  [...(embedded || []), ...(local || [])].forEach(thread => {
    if (!map.has(thread.id)) {
      map.set(thread.id, JSON.parse(JSON.stringify(thread)));
      return;
    }
    const current = map.get(thread.id);
    const latest = newer(current, thread);
    const messages = new Map((current.messages || []).map(message => [message.id, message]));
    (thread.messages || []).forEach(message => messages.set(message.id, message));
    map.set(thread.id, {...current, ...latest, messages:[...messages.values()].sort((a,b)=>timeValue(a.createdAt)-timeValue(b.createdAt))});
  });
  return [...map.values()].sort((a,b)=>String(b.updatedAt || b.createdAt).localeCompare(String(a.updatedAt || a.createdAt)));
}
let commentState = {
  version: 1,
  taskId: commentTaskId,
  ledgerVersion: commentLedgerVersion,
  threads: mergeThreads(embeddedComments.threads, localComments.threads),
};
let pendingCommentTarget = null;
let commentMode = false;

const commentsDrawer = document.getElementById('comments-drawer');
const commentsList = document.getElementById('comments-list');
const commentsFilter = document.getElementById('comments-filter');
const commentsCount = document.getElementById('comments-count');
const localStatus = document.getElementById('comments-local-status');
const selectionAction = document.getElementById('comment-selection-action');
const composer = document.getElementById('comment-composer');
const targetPreview = document.getElementById('comment-target-preview');
const commentSeverity = document.getElementById('comment-severity');
const commentTextarea = document.getElementById('comment-textarea');

function uid(prefix) {
  return prefix + '-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2,8);
}
function isoNow() { return new Date().toISOString(); }
function saveComments() {
  if (storageAvailable) {
    try { localStorage.setItem(storageKey, JSON.stringify(commentState)); }
    catch (error) { storageAvailable = false; }
  }
  void syncCommentsToBridge();
}
async function syncCommentsToBridge() {
  if (!commentBridge?.endpoint || !commentBridge?.token) return false;
  try {
    const response = await fetch(commentBridge.endpoint, {
      method:'PUT', mode:'cors', credentials:'omit', cache:'no-store',
      headers:{'Content-Type':'application/json','X-Ledger-Comment-Token':commentBridge.token},
      body:JSON.stringify(commentState),
    });
    if (!response.ok) throw new Error('bridge status ' + response.status);
    bridgeStatus = '已自动同步给本机 AI 桥接';
    renderComments();
    return true;
  } catch (error) {
    bridgeStatus = '自动同步失败，评论仍保存在本机浏览器';
    renderComments();
    return false;
  }
}
function unsyncedMessageCount() {
  return commentState.threads.flatMap(thread => thread.messages || []).filter(message => message.author === 'user' && !embeddedMessageIds.has(message.id)).length;
}
function unresolved(thread) { return thread.status !== 'resolved'; }

function nearestSection(element) {
  return element.closest('[data-artifact][id], .card[id], section[id]');
}
function resourceIdFor(element, index) {
  const section = nearestSection(element);
  const sectionId = section?.id || 'document';
  if (element.id) return element.id;
  if (element.dataset.object) return sectionId + '::data::' + element.dataset.object;
  if (element.dataset.entity) return sectionId + '::entity::' + element.dataset.entity;
  if (element.dataset.diagramKind) return sectionId + '::diagram::' + element.dataset.diagramKind;
  if (element.matches('pre')) return sectionId + '::code::' + (element.id || index);
  if (element.matches('.table-wrap')) return sectionId + '::table::' + index;
  return sectionId + '::resource::' + index;
}
function prepareCommentables() {
  const selector = '.card[id], [data-artifact][id], .diagram, .table-wrap, tr[data-object], .er-entity, pre, .evidence';
  [...document.querySelectorAll(selector)].forEach((element, index) => {
    if (element.closest('#comments-drawer, #comment-composer')) return;
    element.dataset.commentable = 'true';
    element.dataset.resourceId = resourceIdFor(element, index);
    if (!element.dataset.resourceType) {
      element.dataset.resourceType = element.dataset.object ? 'data-row' : element.dataset.entity ? 'er-entity' : element.matches('.diagram') ? 'diagram' : element.matches('.table-wrap') ? 'table' : element.matches('pre') ? 'code' : 'section';
    }
  });
}
function findResource(resourceId) {
  return [...document.querySelectorAll('[data-commentable]')].find(element => element.dataset.resourceId === resourceId);
}
function labelFor(element) {
  return element.getAttribute('aria-label') || element.querySelector('h2,h3,h4')?.textContent?.trim() || element.dataset.object || element.dataset.entity || element.dataset.resourceId;
}
function targetForResource(element) {
  const section = nearestSection(element);
  return {type:'resource', sectionId:section?.id || element.id || 'document', resourceId:element.dataset.resourceId, resourceType:element.dataset.resourceType, label:labelFor(element), ledgerVersion:commentLedgerVersion};
}
function targetForSelection(selection) {
  const quote = selection.toString().trim().slice(0,600);
  const node = selection.commonAncestorContainer || selection.anchorNode;
  const element = node?.nodeType === Node.ELEMENT_NODE ? node : node?.parentElement;
  const section = element?.closest('[data-artifact][id], .card[id], section[id]');
  if (!section || !quote) return null;
  const sectionText = section.innerText || section.textContent || '';
  const offset = sectionText.indexOf(quote);
  const prefix = offset >= 0 ? sectionText.slice(Math.max(0, offset - 80), offset) : '';
  const suffix = offset >= 0 ? sectionText.slice(offset + quote.length, offset + quote.length + 80) : '';
  return {type:'text', sectionId:section.id, resourceId:section.dataset.resourceId || section.id, resourceType:'text', quote, prefix, suffix, label:labelFor(section), ledgerVersion:commentLedgerVersion};
}
function openComposer(target) {
  pendingCommentTarget = target;
  targetPreview.textContent = target.type === 'text' ? '选中文字：' + target.quote : '资源：' + target.label + ' (' + target.resourceId + ')';
  commentTextarea.value = '';
  commentSeverity.value = 'question';
  composer.hidden = false;
  setTimeout(()=>commentTextarea.focus(), 0);
}
function closeComposer() {
  composer.hidden = true;
  pendingCommentTarget = null;
  selectionAction.hidden = true;
}
function addThread() {
  const body = commentTextarea.value.trim();
  if (!body || !pendingCommentTarget) return;
  const now = isoNow();
  commentState.threads.unshift({
    id:uid('CMT'), target:pendingCommentTarget, severity:commentSeverity.value, status:'open', createdAt:now, updatedAt:now,
    messages:[{id:uid('MSG'), author:'user', createdAt:now, body}],
    change:{status:'none', ledgerVersion:commentLedgerVersion, summary:''},
  });
  saveComments(); closeComposer(); renderComments(); openDrawer();
  window.getSelection()?.removeAllRanges();
}
function addReply(threadId, input) {
  const body = input.value.trim();
  if (!body) return;
  const thread = commentState.threads.find(item => item.id === threadId);
  if (!thread) return;
  const now = isoNow();
  thread.messages = thread.messages || [];
  thread.messages.push({id:uid('MSG'), author:'user', createdAt:now, body});
  thread.status = 'open'; thread.updatedAt = now;
  input.value = ''; saveComments(); renderComments();
}
function toggleResolved(threadId) {
  const thread = commentState.threads.find(item => item.id === threadId);
  if (!thread) return;
  thread.status = thread.status === 'resolved' ? 'open' : 'resolved';
  thread.updatedAt = isoNow(); saveComments(); renderComments();
}
function locateThread(thread) {
  const target = document.getElementById(thread.target.sectionId) || findResource(thread.target.resourceId);
  if (!target) return;
  const panel = target.closest('[data-panel]');
  if (panel) show(panel.dataset.panel);
  requestAnimationFrame(()=>target.scrollIntoView({behavior:'smooth', block:'start'}));
}
function threadAnchorState(thread) {
  if (thread.target.type === 'resource') return findResource(thread.target.resourceId) ? 'ok' : 'stale';
  const section = document.getElementById(thread.target.sectionId);
  return section && (section.innerText || '').includes(thread.target.quote || '') ? 'ok' : 'stale';
}
function renderResourceBadges() {
  document.querySelectorAll('.comment-resource-badge').forEach(badge => badge.remove());
  document.querySelectorAll('[data-has-comments]').forEach(element => delete element.dataset.hasComments);
  const counts = new Map();
  commentState.threads.filter(unresolved).forEach(thread => {
    const key = thread.target.resourceId || thread.target.sectionId;
    counts.set(key, (counts.get(key) || 0) + 1);
  });
  counts.forEach((count, key) => {
    const element = findResource(key) || document.getElementById(key);
    if (!element) return;
    element.dataset.hasComments = 'true';
    const badgeHost = element.matches('tr') ? element.querySelector('td,th') : element;
    if (!badgeHost) return;
    if (getComputedStyle(badgeHost).position === 'static') badgeHost.style.position = 'relative';
    const badge = document.createElement('span');
    badge.className = 'comment-resource-badge'; badge.textContent = String(count); badge.title = '未解决评论 ' + count;
    badgeHost.appendChild(badge);
  });
}
function textNodeRange(section, quote) {
  const walker = document.createTreeWalker(section, NodeFilter.SHOW_TEXT, {acceptNode(node) {
    return node.parentElement?.closest('.comment-resource-badge, script, style') ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT;
  }});
  const nodes = []; let text = ''; let node;
  while ((node = walker.nextNode())) { nodes.push({node,start:text.length,end:text.length + node.data.length}); text += node.data; }
  const start = text.indexOf(quote);
  if (start < 0) return null;
  const end = start + quote.length;
  const first = nodes.find(item => item.start <= start && item.end >= start);
  const last = nodes.find(item => item.start < end && item.end >= end);
  if (!first || !last) return null;
  const range = document.createRange();
  range.setStart(first.node, start - first.start); range.setEnd(last.node, end - last.start);
  return range;
}
function renderHighlights() {
  if (!globalThis.CSS?.highlights || typeof Highlight === 'undefined') return;
  const ranges = commentState.threads.filter(unresolved).filter(thread => thread.target.type === 'text').map(thread => {
    const section = document.getElementById(thread.target.sectionId);
    return section ? textNodeRange(section, thread.target.quote || '') : null;
  }).filter(Boolean);
  CSS.highlights.set('ledger-comments', new Highlight(...ranges));
}
function renderComments() {
  const filter = commentsFilter.value;
  const threads = commentState.threads.filter(thread => filter === 'all' || (filter === 'resolved' ? thread.status === 'resolved' : thread.status !== 'resolved'));
  commentsList.replaceChildren();
  if (!threads.length) {
    const empty = document.createElement('p'); empty.className = 'muted'; empty.textContent = '当前筛选下没有评论。'; commentsList.appendChild(empty);
  }
  threads.forEach(thread => {
    const card = document.createElement('article'); card.className = 'comment-thread ' + thread.severity;
    const meta = document.createElement('div'); meta.className = 'comment-meta';
    meta.textContent = thread.id + ' · ' + thread.severity + ' · ' + thread.status + (threadAnchorState(thread) === 'stale' ? ' · 锚点需确认' : '');
    const quote = document.createElement('div'); quote.className = 'comment-quote';
    quote.textContent = thread.target.type === 'text' ? '“' + thread.target.quote + '”' : thread.target.label + ' · ' + thread.target.resourceId;
    const locate = document.createElement('button'); locate.className = 'btn small'; locate.textContent = '定位'; locate.addEventListener('click',()=>locateThread(thread));
    card.append(meta, quote, locate);
    (thread.messages || []).forEach(message => {
      const item = document.createElement('div'); item.className = 'comment-message ' + message.author;
      const author = document.createElement('small'); author.textContent = (message.author === 'ai' ? 'AI' : '你') + ' · ' + message.createdAt;
      const body = document.createElement('div'); body.textContent = message.body;
      item.append(author, body); card.appendChild(item);
    });
    const reply = document.createElement('div'); reply.className = 'comment-reply';
    const input = document.createElement('input'); input.placeholder = '继续追问或补充说明';
    const send = document.createElement('button'); send.className = 'btn'; send.textContent = '追评'; send.addEventListener('click',()=>addReply(thread.id,input));
    input.addEventListener('keydown',event=>{if(event.key==='Enter')addReply(thread.id,input);});
    const resolve = document.createElement('button'); resolve.className = 'btn'; resolve.textContent = thread.status === 'resolved' ? '重新打开' : '标记解决'; resolve.addEventListener('click',()=>toggleResolved(thread.id));
    reply.append(input, send, resolve); card.appendChild(reply); commentsList.appendChild(card);
  });
  const unresolvedCount = commentState.threads.filter(unresolved).length;
  commentsCount.textContent = String(unresolvedCount);
  const unsynced = unsyncedMessageCount();
  localStatus.textContent = bridgeStatus + ' · 待写回 HTML：' + unsynced + (storageAvailable ? '' : ' · 浏览器本地持久化不可用');
  renderResourceBadges(); renderHighlights();
}
function openDrawer() { commentsDrawer.classList.add('open'); commentsDrawer.setAttribute('aria-hidden','false'); renderComments(); }
function closeDrawer() { commentsDrawer.classList.remove('open'); commentsDrawer.setAttribute('aria-hidden','true'); }
async function writeClipboard(text) {
  try { await navigator.clipboard.writeText(text); return true; }
  catch (error) {
    const area = document.createElement('textarea'); area.value = text; area.style.position = 'fixed'; area.style.opacity = '0'; document.body.appendChild(area); area.select();
    const ok = document.execCommand('copy'); area.remove(); return ok;
  }
}
async function copyOpenCommentsForAI() {
  const threads = commentState.threads.filter(thread => thread.status === 'open');
  if (!threads.length) { localStatus.textContent = '没有需要 AI 处理的 open 评论'; return; }
  const payload = {protocol:'lifecycle-ledger-comments/v1', action:'reply-and-edit-when-justified', taskId:commentTaskId, ledgerVersion:commentLedgerVersion, source:'explicit-user-copy', threads};
  const text = '处理台账评论。请核对锚点，逐条追评；仅在内容不清楚、错误或不完整时修改正文，并更新台账版本、审计和内嵌评论。\n' + JSON.stringify(payload, null, 2);
  const ok = await writeClipboard(text); localStatus.textContent = ok ? '已复制 ' + threads.length + ' 个待处理线程' : '复制失败，请使用导出 JSON';
}
function exportComments() {
  const blob = new Blob([JSON.stringify(commentState, null, 2)], {type:'application/json'});
  const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = commentTaskId + '-comments-' + Date.now() + '.json'; link.click();
  setTimeout(()=>URL.revokeObjectURL(link.href),1000);
}

prepareCommentables();
document.getElementById('comment-mode-button').addEventListener('click', event => {
  commentMode = !commentMode; document.body.classList.toggle('comment-mode', commentMode); event.currentTarget.setAttribute('aria-pressed', String(commentMode)); event.currentTarget.textContent = commentMode ? '退出评论模式' : '评论资源';
  selectionAction.hidden = true; window.getSelection()?.removeAllRanges();
});
document.addEventListener('click', event => {
  if (!commentMode || event.target.closest('#comments-drawer, #comment-composer, .topbar, .tabs, .section-toc')) return;
  const resource = event.target.closest('[data-commentable]');
  if (!resource) return;
  event.preventDefault(); event.stopPropagation(); openComposer(targetForResource(resource));
}, true);
document.addEventListener('mouseup', event => {
  if (commentMode || event.target.closest('#comments-drawer, #comment-composer')) return;
  setTimeout(()=>{
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || selection.toString().trim().length < 2) { selectionAction.hidden = true; return; }
    const target = targetForSelection(selection);
    if (!target) return;
    pendingCommentTarget = target;
    const rect = selection.getRangeAt(0).getBoundingClientRect();
    selectionAction.style.left = Math.max(8, Math.min(innerWidth - 110, rect.left)) + 'px'; selectionAction.style.top = Math.max(8, rect.bottom + 8) + 'px'; selectionAction.hidden = false;
  },0);
});
selectionAction.addEventListener('click',()=>{ if (pendingCommentTarget) openComposer(pendingCommentTarget); });
document.getElementById('comments-button').addEventListener('click',openDrawer);
document.getElementById('comments-close').addEventListener('click',closeDrawer);
commentsFilter.addEventListener('change',renderComments);
document.getElementById('comment-save').addEventListener('click',addThread);
document.getElementById('comment-cancel').addEventListener('click',closeComposer);
document.getElementById('comments-copy').addEventListener('click',copyOpenCommentsForAI);
document.getElementById('comments-export').addEventListener('click',exportComments);
renderComments();
void syncCommentsToBridge();
'''


def page() -> str:
    phase_tabs = "".join(
        f'<button class="tab" role="tab" aria-controls="panel-phase-{p["id"]}" data-tab="phase-{p["id"]}">{p["id"]} · {p["name"]}</button>'
        for p in PHASES
    )
    phase_panels = "".join(phase_panel(phase) for phase in PHASES)
    overview_toc = section_toc("toc-overview", "总览区块目录", [("总览", [
        ("overview-status", "状态指标", False),
        ("overview-phase-map", "Phase 依赖", False),
        ("overview-branch-lineage", "分支谱系", False),
        ("overview-blockers", "阻塞待确认", False),
        ("overview-commands", "推荐动作", False),
        ("overview-links", "关键链接", False),
    ])])
    integration_toc = section_toc("toc-integration", "跨阶段集成区块目录", [("集成", [
        ("integration-dependencies", "接口与数据依赖", False),
        ("integration-branches", "父 SHA 同步", False),
        ("integration-resources", "共享资源", True),
        ("integration-release", "发布与回滚", False),
        ("integration-validation", "集成验证", False),
    ])])
    summary_toc = section_toc("toc-summary", "总结与审计区块目录", [("总结", [
        ("summary-outcome", "交付结果", False),
        ("summary-risks", "风险遗留", False),
        ("summary-audit", "审计时间线", False),
        ("summary-continue", "继续使用", False),
    ])])
    comments_json = embedded_comments_json()
    comments_js = comments_runtime_script()
    return f'''<!doctype html>
<html lang="zh-CN" data-demo="true" data-comments-enabled="true" data-task-id="{TASK_ID}" data-ledger-version="v2.0">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{TASK_ID} · 微信连续包月三阶段交付示例</title>
<style>
:root{{--bg:#f4f6f9;--card:#fff;--text:#1f2937;--muted:#667085;--line:#dfe4eb;--blue:#246bfd;--green:#168653;--amber:#a96700;--shadow:0 10px 30px rgba(33,43,54,.08)}}
html{{scroll-behavior:smooth}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
.shell{{max-width:1500px;margin:auto;padding:24px}} .topbar{{display:flex;justify-content:space-between;gap:20px;align-items:flex-start;background:#15233a;color:#fff;padding:24px;border-radius:18px;box-shadow:var(--shadow)}}
h1,h2,h3,p{{margin-top:0}} h1{{font-size:28px;margin-bottom:6px}} h2{{font-size:24px}} h3{{font-size:18px;margin-bottom:12px}} code{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}}
.eyebrow{{text-transform:uppercase;letter-spacing:.08em;font-size:12px;color:#8cb4ff}} .meta{{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}} .chip,.pill{{display:inline-flex;border-radius:999px;padding:5px 10px;background:#eef3fb;color:#284a7a;font-weight:650}} .topbar .chip{{background:#233b60;color:#dce9ff}}
.pill.done{{background:#e8f6ef;color:#12663e}} .actions{{display:flex;gap:8px;flex-wrap:wrap}} button{{font:inherit}} .btn{{border:1px solid #70809a;background:#fff;color:#26364e;padding:8px 12px;border-radius:9px;cursor:pointer}}
.tabs{{display:flex;gap:8px;overflow:auto;margin:18px 0;padding:8px;background:#e8ecf2;border-radius:13px;position:sticky;top:0;z-index:10}} .tab{{white-space:nowrap;border:0;background:transparent;padding:10px 14px;border-radius:9px;color:#536176;cursor:pointer;font-weight:700}} .tab.active{{background:#fff;color:var(--blue);box-shadow:0 2px 10px rgba(30,42,60,.10)}}
.tab-panel{{display:none}} .tab-panel.active{{display:block}} .panel-head{{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin:22px 0 12px}} .card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;margin:12px 0;box-shadow:0 3px 14px rgba(31,41,55,.04)}}
.section-toc{{display:flex;align-items:center;gap:10px;overflow:auto;position:sticky;top:66px;z-index:9;padding:10px 12px;margin:0 0 16px;background:rgba(255,255,255,.96);border:1px solid #d8e0ea;border-radius:12px;box-shadow:0 5px 18px rgba(31,41,55,.07);backdrop-filter:blur(10px)}} .toc-title{{flex:0 0 auto;font-weight:800;color:#26364e}} .toc-group{{display:flex;align-items:center;gap:6px;flex:0 0 auto;padding-left:10px;border-left:1px solid #d9e0e9}} .toc-group>b{{font-size:11px;color:#7b8799;letter-spacing:.06em}} .toc-link{{white-space:nowrap;text-decoration:none;color:#38506f;background:#f1f4f8;border:1px solid transparent;border-radius:999px;padding:5px 9px;font-size:12px;font-weight:650}} .toc-link:hover,.toc-link:focus-visible{{color:var(--blue);border-color:#8aaff5;background:#eef4ff;outline:none}} .toc-link.release-link{{color:#7a4b00;background:#fff0c7;border-color:#e9c665}} [id]{{scroll-margin-top:145px}}
.grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}} .metric strong{{font-size:22px;display:block}} .muted{{color:var(--muted)}} .evidence{{border-left:4px solid var(--blue);padding:10px 12px;background:#f4f8ff}}
.diagram{{overflow:auto;border:1px dashed #aab5c3;border-radius:12px;padding:16px;background:#fbfcfe;margin:12px 0}} .flow{{display:flex;align-items:center;min-width:max-content;gap:8px}} .node{{padding:10px 13px;border:1px solid #8eaddd;background:#edf4ff;border-radius:9px;font-weight:700}} .arrow{{color:#728097;font-size:20px}} .diagram p{{margin:10px 0 0;color:var(--muted)}}
.data-lane{{min-width:1050px;padding:12px 0;border-bottom:1px solid #e2e7ee}} .data-lane:last-of-type{{border-bottom:0}} .data-lane>b{{display:block;color:#315a92;margin-bottom:8px}}
.erd{{min-width:0}} .er-entities{{display:grid;grid-template-columns:repeat(4,minmax(270px,1fr));gap:14px;align-items:start;min-width:1240px}} .er-entity{{border:1px solid #93a4ba;border-radius:10px;background:#fff;overflow:hidden;min-height:245px}} .er-entity h4{{margin:0;padding:9px 12px;background:#e7eef9;color:#234b7a}} .er-entity>code{{display:block;padding:8px 12px;border-bottom:1px solid #e3e8ef;color:#174f92;font-weight:700}} .er-entity ul{{list-style:none;margin:0;padding:6px 12px 10px}} .er-entity li{{padding:3px 0;border-bottom:1px dashed #e4e8ed;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}} .er-entity li:last-child{{border:0}} .er-links{{display:grid;gap:8px;margin-top:16px;min-width:1240px}} .er-link{{display:grid;grid-template-columns:240px 34px minmax(300px,1fr) 34px 240px;align-items:center;text-align:center;gap:8px;padding:8px 12px;border:1px solid #bed0e9;border-radius:9px;background:#edf5ff}} .er-link.logical{{border-style:dashed;border-color:#d3ad71;background:#fff8e9}} .er-link span{{position:relative;font-size:12px;font-weight:650}} .er-link span:before,.er-link span:after{{content:"";position:absolute;top:50%;width:28%;border-top:3px solid #3774c8}} .er-link.logical span:before,.er-link.logical span:after{{border-top-style:dashed;border-color:#a16a19}} .er-link span:before{{left:0}} .er-link span:after{{right:0}} .er-link code{{font-weight:700;color:#234b7a}}
.table-wrap{{overflow:auto;border:1px solid var(--line);border-radius:10px}} table{{border-collapse:collapse;min-width:980px;width:100%;background:#fff}} th,td{{padding:10px 11px;text-align:left;vertical-align:top;border-bottom:1px solid #e7ebf0}} th{{position:sticky;top:0;background:#f5f7fa;color:#445168;font-size:12px}} tr:last-child td{{border-bottom:0}}
.phase-chain{{display:flex;align-items:stretch;gap:10px;overflow:auto}} .phase-box{{min-width:235px;background:#fff;border:1px solid var(--line);border-top:4px solid var(--blue);border-radius:12px;padding:14px}} .chain-arrow{{display:flex;align-items:center;color:#8591a3;font-size:24px}}
.callout{{padding:14px;border-radius:10px;background:#fff7df;border:1px solid #f0d58b}} .good{{background:#edf9f2;border-color:#b9e3cc}} .small{{font-size:12px}}
[hidden]{{display:none!important}} #comments-count{{display:inline-grid;place-items:center;min-width:20px;height:20px;margin-left:5px;padding:0 5px;border-radius:999px;background:#d94452;color:#fff;font-size:11px}} #comment-mode-button[aria-pressed="true"]{{background:#fff0c7;border-color:#e1b849;color:#704700}}
body.comment-mode [data-commentable]{{cursor:crosshair}} body.comment-mode [data-commentable]:hover{{outline:3px solid #e3a900;outline-offset:3px}} [data-has-comments="true"]{{box-shadow:inset 4px 0 0 #e3a900}} .comment-resource-badge{{position:absolute;right:8px;top:8px;display:inline-grid;place-items:center;min-width:22px;height:22px;padding:0 6px;border-radius:999px;background:#fff0c7;border:1px solid #dfb64a;color:#724800;font-size:11px;font-weight:800;z-index:3}} ::highlight(ledger-comments){{background:#fff1a8;text-decoration:underline dotted #a96c00 2px}}
#comment-selection-action{{position:fixed;z-index:40;border:1px solid #d3a52d;background:#fff5d6;color:#684300;padding:7px 10px;border-radius:8px;box-shadow:var(--shadow);cursor:pointer}}
.comments-drawer{{position:fixed;top:0;right:0;bottom:0;width:min(460px,100vw);z-index:50;background:#f8fafc;border-left:1px solid #cfd7e2;box-shadow:-12px 0 34px rgba(25,39,58,.18);transform:translateX(102%);transition:transform .2s ease;display:flex;flex-direction:column}} .comments-drawer.open{{transform:translateX(0)}} .comments-head{{padding:16px;border-bottom:1px solid #dce3eb;background:#fff}} .comments-head-row{{display:flex;align-items:center;justify-content:space-between;gap:10px}} .comments-toolbar{{display:flex;gap:8px;align-items:center;margin-top:10px;flex-wrap:wrap}} .comments-toolbar select{{padding:7px;border:1px solid #bdc7d4;border-radius:8px;background:#fff}} .comments-list{{padding:12px;overflow:auto;flex:1}} .comment-thread{{background:#fff;border:1px solid #dce3eb;border-radius:12px;padding:12px;margin-bottom:10px}} .comment-thread.blocker{{border-left:5px solid #d94452}} .comment-thread.suggestion{{border-left:5px solid #246bfd}} .comment-thread.question{{border-left:5px solid #d99a16}} .comment-meta{{display:flex;gap:6px;flex-wrap:wrap;font-size:11px;color:#69768a}} .comment-quote{{margin:8px 0;padding:8px;background:#fff8dd;border-radius:7px;color:#604b13}} .comment-message{{margin:8px 0;padding:9px;border-radius:8px;background:#f2f5f8}} .comment-message.ai{{background:#eaf2ff}} .comment-message small{{display:block;color:#718096;margin-bottom:3px}} .comment-reply{{display:flex;gap:6px;margin-top:9px}} .comment-reply input{{min-width:0;flex:1;padding:8px;border:1px solid #bdc7d4;border-radius:8px}} .comments-footer{{padding:12px;border-top:1px solid #dce3eb;background:#fff;display:flex;gap:8px;flex-wrap:wrap}}
.comment-composer{{position:fixed;inset:0;z-index:60;background:rgba(20,30,45,.45);display:grid;place-items:center;padding:18px}} .comment-dialog{{width:min(560px,100%);background:#fff;border-radius:14px;padding:18px;box-shadow:0 20px 60px rgba(10,20,35,.3)}} .comment-dialog textarea{{width:100%;min-height:110px;resize:vertical;padding:10px;border:1px solid #b9c4d2;border-radius:9px}} .comment-dialog select{{padding:8px;border:1px solid #b9c4d2;border-radius:8px}} .comment-target-preview{{padding:9px;background:#f5f7fa;border-radius:8px;margin-bottom:10px;max-height:120px;overflow:auto}} .comment-dialog-actions{{display:flex;justify-content:flex-end;gap:8px;margin-top:12px}}
@media(max-width:800px){{.shell{{padding:12px}}.topbar,.panel-head{{display:block}}.actions{{margin-top:14px}}.grid{{grid-template-columns:1fr}}.tabs{{top:0}}.section-toc{{top:62px}}.comments-drawer{{width:100vw}}}}
@media print{{body{{background:#fff}}.shell{{max-width:none;padding:0}}.topbar{{color:#000;background:#fff;border:1px solid #bbb;box-shadow:none}}.tabs,.section-toc,.actions,.comments-drawer,.comment-composer,#comment-selection-action,.comment-resource-badge{{display:none!important}}.tab-panel{{display:block!important;break-before:page}}.card{{box-shadow:none;break-inside:avoid}}}}
</style>
</head>
<body><main class="shell">
  <header class="topbar"><div><span class="eyebrow">Phase-aware lifecycle ledger · 示例数据</span><h1>微信连续包月三阶段交付</h1><p>{TASK_ID} · 进件 → 微信支付 → 连续包月</p><div class="meta"><span class="chip">整体 DONE</span><span class="chip">3 Phases</span><span class="chip">台账 v2.0</span><span class="chip">更新 {AS_OF}</span></div></div><div class="actions"><button class="btn" data-copy-text="{TASK_ID}">复制任务 ID</button><button class="btn" id="comment-mode-button" aria-pressed="false">评论资源</button><button class="btn" id="comments-button">讨论<span id="comments-count">1</span></button><button class="btn" id="toggle-all">展开全部</button><button class="btn" id="print-button">打印</button></div></header>
  <div class="callout" style="margin-top:14px"><b>示例说明：</b>这是用于检查最新版 Skill 信息架构的虚构案例；分支、SHA、接口、表名和结果不可用于真实发布。</div>
  <nav class="tabs" aria-label="任务阶段"><button class="tab active" role="tab" aria-controls="panel-overview" data-tab="overview">总览</button>{phase_tabs}<button class="tab" role="tab" aria-controls="panel-integration" data-tab="integration">跨阶段集成</button><button class="tab" role="tab" aria-controls="panel-summary" data-tab="summary">总结与审计</button></nav>

  <section class="tab-panel active" id="panel-overview" role="tabpanel" data-panel="overview">
    <div class="panel-head"><div><span class="eyebrow">总览</span><h2>三阶段依赖、分支谱系与当前动作</h2></div><span class="pill done">全部完成</span></div>
    {overview_toc}
    <section class="grid" id="overview-status"><div class="card metric"><strong>3 / 3</strong>Phase 完成</div><div class="card metric"><strong>3</strong>独立候选分支</div><div class="card metric"><strong>0</strong>父 SHA 漂移</div></section>
    <section class="card" id="overview-phase-map"><h3>Phase 依赖图</h3><div class="phase-chain"><div class="phase-box"><b>P1 商户进件</b><p>提供已审核商户身份</p><span class="pill done">DONE</span></div><div class="chain-arrow">→</div><div class="phase-box"><b>P2 微信支付</b><p>提供支付订单与回调</p><span class="pill done">DONE</span></div><div class="chain-arrow">→</div><div class="phase-box"><b>P3 连续包月</b><p>签约、首扣和周期扣款</p><span class="pill done">DONE</span></div></div></section>
    <section class="card" id="overview-branch-lineage"><h3>分支谱系</h3><div class="table-wrap"><table><thead><tr><th>Phase</th><th>分支</th><th>父 Phase</th><th>父候选 SHA</th><th>Base SHA</th><th>Head</th><th>状态</th></tr></thead><tbody><tr><td>P1</td><td>feat/...-p1-onboarding</td><td>NONE</td><td>NONE</td><td>1111111</td><td>a1b2c3d4</td><td>CURRENT</td></tr><tr><td>P2</td><td>feat/...-p2-wechat-pay</td><td>P1</td><td>a1b2c3d4</td><td>a1b2c3d4</td><td>b2c3d4e5</td><td>CURRENT</td></tr><tr><td>P3</td><td>feat/...-p3-recurring</td><td>P2</td><td>b2c3d4e5</td><td>b2c3d4e5</td><td>c3d4e5f6</td><td>CURRENT</td></tr></tbody></table></div></section>
    <section class="card good" id="overview-blockers"><h3>阻塞与待确认</h3><p>示例完成态无阻塞。真实任务若父 Phase 候选变化，下游会立即显示 STALE_PARENT，并阻止候选 push 和部署。</p></section>
    <section class="card" id="overview-commands"><h3>推荐动作</h3><p>检查三个 Phase Tab 的强制产物、分支继承和上线资源是否符合团队预期。</p></section>
    <section class="card" id="overview-links"><h3>关键链接</h3><p>代码、需求文档、OpenSpec、部署任务、截图与日志证据在真实台账中使用明确链接；本示例不连接业务系统。</p></section>
  </section>

  {phase_panels}

  <section class="tab-panel" id="panel-integration" role="tabpanel" data-panel="integration">
    <div class="panel-head"><div><span class="eyebrow">跨阶段集成</span><h2>契约、分支、共享资源与发布顺序</h2></div><span class="pill done">验证通过</span></div>
    {integration_toc}
    <section class="card" id="integration-dependencies" {artifact_attrs('integration-dependencies', 3)}><h3>Phase 接口与数据依赖</h3><p>P1 通过接口与事件向 P2 提供 wechatMerchantId、merchantApplicationId 和 APPROVED 状态；P2 向 P3 提供支付商户配置、支付订单接口和验签后的回调事件。数据所有权不跨 Phase 转移，后阶段只通过稳定接口和引用 ID 使用。兼容窗口允许父 Phase 新旧字段并存两个发布周期；证据为接口契约、事件 Schema、数据清单和候选 SHA。</p></section>
    <section class="card" id="integration-branches" {artifact_attrs('integration-branches', 3)}><h3>父 SHA 与同步记录</h3><p>分支谱系为 P1@a1b2c3d4 → P2@b2c3d4e5 → P3@c3d4e5f6。每个子分支的 base 等于创建时父候选 SHA，当前父 SHA 状态均为 CURRENT。若父阶段更新，先标记 STALE_PARENT，再 merge 父提交到子分支并重跑契约、数据兼容和回归测试；同步证据包含 merge-base、同步 commit 和测试结果。</p></section>
    <section class="card" id="integration-resources" {artifact_attrs('integration-resources', 3)}><h3>共享资源与所有者</h3><p>资源按 Phase 所有：P1 管理进件表和商户状态；P2 管理支付订单、支付回调与支付配置；P3 管理连续包月合同和扣款记录。共享资源包括微信商户密钥引用、事件命名空间和统一审计 Trace。每项记录所有者、首次引入 Phase、兼容约束和回滚策略；证据来自数据资产清单、配置中心清单和消息契约。</p></section>
    <section class="card" id="integration-release" {artifact_attrs('integration-release', 3)}><h3>总体部署顺序与回滚</h3><p>部署顺序为 P1 DDL/配置/应用/E2E → P2 DDL/配置/应用/E2E → P3 DDL/配置/应用/E2E。保护规则是在父 Phase 未就绪时关闭子 Phase 入口；每阶段部署后先验证版本、数据和契约，再继续下一阶段。失败时停止后续发布，优先关闭当前阶段开关，回滚代码但保留向后兼容表结构；证据由部署 ID、镜像 SHA、健康检查和回归结果组成。</p></section>
    <section class="card" id="integration-validation" {artifact_attrs('integration-validation', 3)}><h3>跨阶段验证</h3><p>用例 INT-TC-001 验证 P1 APPROVED 商户进入 P2 支付，预期创建订单成功，实际示例通过，版本 P1 a1b2c3d4 / P2 b2c3d4e5，状态 PASS，证据为接口响应和日志。用例 INT-TC-002 验证 P2 成功支付后进入 P3 签约与首扣，预期合同和扣款状态一致，实际示例通过，版本 P3 c3d4e5f6，证据为截图、事件和对账日志。</p></section>
  </section>

  <section class="tab-panel" id="panel-summary" role="tabpanel" data-panel="summary">
    <div class="panel-head"><div><span class="eyebrow">总结与审计</span><h2>阶段交付结果</h2></div><span class="pill done">DONE</span></div>
    {summary_toc}
    <section class="card" id="summary-outcome"><h3>结果</h3><p>P1、P2、P3 分别由独立分支和候选 SHA 承载；每个 Phase 的需求、架构、模型、数据、影响、上线资源和验证均有独立记录，跨阶段集成回归通过。</p></section>
    <section class="card" id="summary-risks"><h3>风险与遗留</h3><p>真实上线仍需复核微信平台权限、生产容量、数据保留和正式回滚审批。本示例不代表生产授权，也不包含真实业务数据。</p></section>
    <section class="card" id="summary-audit"><h3>审计时间线</h3><p>10:00 建立三 Phase 范围；11:00 确认需求；14:00 确认方案；次日完成 P1 候选；随后从父候选 SHA 创建 P2、P3；完成分阶段部署、E2E 和跨阶段回归。</p></section>
    <section class="card" id="summary-continue"><h3>继续使用</h3><p>可继续追问实现、补充验收、重开某个 Phase、增加 P4，或在父 Phase 变化后执行分支同步与重新验证。</p></section>
  </section>
</main>
<button id="comment-selection-action" hidden>评论所选</button>
<aside id="comments-drawer" class="comments-drawer" aria-hidden="true" aria-label="台账讨论">
  <div class="comments-head">
    <div class="comments-head-row"><div><b>台账讨论</b><div class="small muted">本地保存 · 桥接自动同步 · 复制/导出降级</div></div><button class="btn" id="comments-close">关闭</button></div>
    <div class="comments-toolbar"><label for="comments-filter">筛选</label><select id="comments-filter"><option value="unresolved">未解决</option><option value="all">全部</option><option value="resolved">已解决</option></select><span id="comments-local-status" class="small muted"></span></div>
  </div>
  <div id="comments-list" class="comments-list"></div>
  <div class="comments-footer"><button class="btn" id="comments-copy">复制待处理评论</button><button class="btn" id="comments-export">导出 JSON</button></div>
</aside>
<div id="comment-composer" class="comment-composer" hidden>
  <div class="comment-dialog" role="dialog" aria-modal="true" aria-labelledby="comment-dialog-title">
    <h3 id="comment-dialog-title">新增评论</h3>
    <div id="comment-target-preview" class="comment-target-preview"></div>
    <label for="comment-severity">类型</label>
    <select id="comment-severity"><option value="question">不理解 / 问题</option><option value="suggestion">修改建议</option><option value="blocker">阻塞确认</option></select>
    <label for="comment-textarea" style="display:block;margin-top:10px">评论</label>
    <textarea id="comment-textarea" placeholder="写下问题、建议或需要 AI 修改的内容"></textarea>
    <div class="comment-dialog-actions"><button class="btn" id="comment-cancel">取消</button><button class="btn" id="comment-save">保存评论</button></div>
  </div>
</div>
<script id="ledger-comment-bridge-config">globalThis.__LEDGER_COMMENT_BRIDGE__=null;</script>
<script id="ledger-comments-data" type="application/json">{comments_json}</script>
<script>
const tabs=[...document.querySelectorAll('[data-tab]')],panels=[...document.querySelectorAll('[data-panel]')];
function show(name){{tabs.forEach(t=>t.classList.toggle('active',t.dataset.tab===name));panels.forEach(p=>p.classList.toggle('active',p.dataset.panel===name));}}
tabs.forEach(t=>t.addEventListener('click',()=>show(t.dataset.tab)));
function activateHash(){{const id=decodeURIComponent(location.hash.slice(1));if(!id)return;const target=document.getElementById(id);if(!target)return;const panel=target.closest('[data-panel]');if(panel)show(panel.dataset.panel);requestAnimationFrame(()=>target.scrollIntoView({{block:'start'}}));}}
window.addEventListener('hashchange',activateHash);if(location.hash)activateHash();
document.getElementById('toggle-all').addEventListener('click',()=>{{const expanded=document.body.classList.toggle('expanded');panels.forEach(p=>p.classList.toggle('active',expanded||p.dataset.panel==='overview'));}});
document.getElementById('print-button').addEventListener('click',()=>window.print());
document.querySelectorAll('[data-copy-text]').forEach(b=>b.addEventListener('click',()=>navigator.clipboard?.writeText(b.dataset.copyText)));
{comments_js}
</script></body></html>'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(page(), encoding="utf-8")
    print(args.output.resolve())


if __name__ == "__main__":
    main()
