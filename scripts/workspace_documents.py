"""Shared HTML document format for live SQLite views and versioned exports."""
from __future__ import annotations
import html
import re
from pathlib import Path
from urllib.parse import urlsplit
from workspace_store import KINDS, stamp

ASSETS = Path(__file__).resolve().parents[1] / 'assets'
TITLES = dict(zip(KINDS, ('产品 PRD','技术设计','UI 与交互设计','开发记录','测试用例与结果','上线资源')))
KEY_LABELS = {'status':'状态','summary':'说明','evidence':'依据与证据','details':'详细设计','currentBehavior':'当前行为','goals':'目标','nonGoals':'不包含的范围','assumptions':'假设','blockingDecisions':'待确认决策','id':'编号','statement':'需求描述','acceptance':'验收标准','expected':'预期结果','actual':'实际结果','name':'名称','title':'标题','owner':'负责人','reason':'原因','source':'来源','path':'文件路径','url':'链接','observedAt':'核查时间','ref':'引用','sha':'版本 SHA','type':'类型','question':'问题','recommended':'建议','answer':'结论','answerSource':'结论来源','answeredAt':'确认时间','version':'版本','environment':'环境','result':'结果','at':'记录时间','scope':'适用范围','phaseId':'阶段','candidateSha':'候选版本','headSha':'当前版本','baseSha':'开发基线','parentPhaseId':'父阶段','parentBranch':'父分支','parentCandidateSha':'父阶段候选版本','syncStatus':'同步状态','applicationArchitecture':'应用架构','codeArchitecture':'代码架构','functionalBreakdown':'功能拆解','dataArchitecture':'数据架构','domainModel':'领域模型','persistenceModel':'数据模型','dataInventory':'数据清单','stateMachine':'状态机','mainFlow':'主流程','recoveryFlow':'异常恢复','impact':'影响分析','traceability':'需求追踪'}

KEY_LABELS.update({'priority':'优先级','role':'角色','entry':'入口','trigger':'触发条件','steps':'操作步骤','preconditions':'前置条件','requirementId':'需求编号','requirementIds':'关联需求','testIds':'关联用例','checked':'检查结果','checkedAt':'确认时间','checkedBy':'确认人','createdAt':'创建时间','updatedAt':'更新时间','phaseId':'阶段','statusAtArchive':'归档时状态','branch':'分支','headSha':'代码版本','baseSha':'基线版本','candidateSha':'候选版本','rollback':'回滚步骤','risks':'风险','resources':'资源清单','dependencies':'依赖','requirement':'关联需求','target':'目标','command':'执行命令','expectedResult':'预期结果','actualResult':'实际结果'})
STATUS_LABELS={'pending':'待补充','complete':'已完成','unchanged':'沿用现状','not-applicable':'不适用','TODO':'待办','DONE':'已完成','PASS':'通过','FAIL':'失败','FAILED':'失败','NOT_RUN':'未执行','BLOCKED':'受阻','PLANNED':'计划中','open':'未解决','closed':'已关闭'}
KEY_LABELS.update({'repository':'仓库','sourceBranch':'源分支','targetBranch':'目标分支','prUrl':'PR 链接','prStatus':'PR 状态','mergedAt':'合并时间','mergeSha':'合并版本','coverage':'覆盖范围'})
KEY_LABELS.update({'key':'Key','value':'Value','description':'描述','appkey':'AppKey','step':'顺序','action':'操作','cron':'Cron'})


def esc(value):
    return html.escape(str(value),quote=True)


def resource_link(value):
    """Link complete HTTP(S) resource URLs, leaving other content as text."""
    if not isinstance(value,str) or re.search(r'[\s<>"\x00-\x1f\x7f]',value):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in ('http','https') or not parsed.hostname:
            return None
    except ValueError:
        return None
    return '<a href="'+esc(value)+'" target="_top" rel="noreferrer">'+esc(value)+'</a>'


def render_value(value):
    if value is None or value == '' or value == [] or value == {}:
        return '<span class="muted">待补充 / 暂无记录</span>'
    if isinstance(value,bool):
        return '是' if value else '否'
    if isinstance(value,dict):
        return '<dl>'+''.join('<dt>'+esc(KEY_LABELS.get(k,k))+'</dt><dd>'+render_value(v)+'</dd>' for k,v in value.items())+'</dl>'
    if isinstance(value,list):
        if all(isinstance(item,dict) for item in value):
            columns=list(dict.fromkeys(k for item in value for k in item))
            if not columns:
                return '<span class="muted">待补充 / 暂无记录</span>'
            return '<div class="doc-table"><table><thead><tr>'+''.join('<th scope="col">'+esc(KEY_LABELS.get(k,k))+'</th>' for k in columns)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+render_value(item.get(k))+'</td>' for k in columns)+'</tr>' for item in value)+'</tbody></table></div>'
        return '<ul>'+''.join('<li>'+render_value(item)+'</li>' for item in value)+'</ul>'
    return resource_link(value) or '<span class="doc-text">'+esc(STATUS_LABELS.get(str(value),value))+'</span>'


def sections(phase,kind):
    a=phase.get('artifacts',{})
    scope=phase.get('scope',{})
    document=phase.get('documents',{}).get(kind,{})
    if kind=='product':
        result=[('背景与现状',scope.get('currentBehavior')),('目标与范围',{'goals':scope.get('goals'),'nonGoals':scope.get('nonGoals')}),('需求与验收标准',phase.get('requirements')),('角色、流程与功能拆解',a.get('functionalBreakdown')),('假设与待确认问题',{'assumptions':scope.get('assumptions'),'blockingDecisions':scope.get('blockingDecisions')}),('需求追踪',phase.get('traceability') or a.get('traceability'))]
    elif kind=='technical':
        result=[
            ('版本记录',document.get('versionHistory')),
            ('项目背景',{'需求关联':document.get('projectBackground'),'现状':scope.get('currentBehavior'),'目标':scope.get('goals'),'范围外':scope.get('nonGoals'),'名词解释':document.get('terminology')}),
            ('干系方',document.get('stakeholders')),
            ('概要设计',{'设计思路':document.get('designOverview') or a.get('functionalBreakdown'),'应用架构':a.get('applicationArchitecture'),'代码架构':a.get('codeArchitecture'),'数据架构':a.get('dataArchitecture'),'领域模型':a.get('domainModel'),'表与关系':a.get('persistenceModel'),'数据清单':a.get('dataInventory'),'功能时序与主流程':a.get('mainFlow'),'状态机':a.get('stateMachine')}),
            ('详细设计',{'接口变更':document.get('interfaces'),'配置变更':document.get('configurationChanges'),'数据迁移与洗数':document.get('dataMigration'),'异常与恢复':a.get('recoveryFlow'),'影响与兼容性':a.get('impact')}),
            ('监控设计',document.get('monitoring')),
            ('上线方案',document.get('rollout') or a.get('release')),
            ('质量保障',{'风险评估表':document.get('qualityAssurance'),'验证计划':a.get('validation'),'需求追踪':phase.get('traceability') or a.get('traceability')}),
            ('排期',document.get('schedule') or phase.get('workItems')),
            ('沟通记录',document.get('communication')),
        ]
    elif kind=='ui':
        result=[('适用范围',{'UI 变更':phase.get('applicability',{}).get('uiChange')}),('页面、布局与交互说明',a.get('uiDesign')),('用户路径与异常状态',a.get('functionalBreakdown')),('验收与交互验证',a.get('validation'))]
    elif kind=='development':
        result=[('开发范围与模块',a.get('impact')),('任务拆分与进度',phase.get('workItems')),('分支与代码版本',phase.get('branch')),('本地验证记录',phase.get('tests')),('问题与后续工作',{'问题':phase.get('issues'),'下一步':phase.get('nextAction')})]
    elif kind=='testing':
        result=[('测试范围、环境与策略',a.get('validation')),('用例与执行结果',phase.get('tests')),('缺陷与回归记录',phase.get('issues')),('需求覆盖',phase.get('traceability') or a.get('traceability'))]
    elif kind=='release':
        resources=[('代码 / PR',document.get('code')),('功能开关',document.get('featureFlags',document.get('emis'))),('配置中心' if 'configuration' in document else 'Lion',document.get('configuration',document.get('lion'))),('网关路由' if 'gateway' in document else 'Shepherd',document.get('gateway',document.get('shepherd')))]
        resources += [(title,document.get(key)) for key,title in (('sql','SQL / DDL'),('scheduledJobs','定时任务'),('crane','Crane / 定时任务'),('mq','消息资源'),('permissions','权限 / 证书'),('other','其他资源'))]
        def applicable(value):
            return bool(value) and not (isinstance(value,dict) and value.get('status') in ('not-applicable','unchanged'))
        result=[]
        for title,value in resources:
            if isinstance(value,list):
                value=[item for item in value if applicable(item)]
            if applicable(value):
                result.append((title,value))
        if not result:
            result=[('上线资源','尚未整理上线资源；请补充需要发布的 PR、配置或其他资源。')]
        return result+[('上线顺序',document.get('rollout'))]
    else:
        raise ValueError('Unknown document kind')
    return result+[('证据与确认记录',{'现状证据':scope.get('evidence'),'确认记录':phase.get('approvals')})]


def render_phase(phase,kind):
    contents=[]
    narrative=phase.get('documents',{}).get(kind,{})
    if kind in ('product','technical'):
        contents.append('<section class="doc-section"><h3>总体结论与范围</h3>'+render_value(narrative.get('summary'))+'</section>')
    for number,(title,data) in enumerate(sections(phase,kind),1):
        if kind=='release' and title=='上线顺序' and isinstance(data,list) and data and not all(isinstance(item,dict) for item in data):
            body='<ol>'+''.join('<li>'+render_value(item)+'</li>' for item in data)+'</ol>'
        else:
            body=render_value(data)
        contents.append(f'<section class="doc-section"><h3>{number:02d} · {esc(title)}</h3>{body}</section>')
    if kind in ('product','technical'):
        contents.append('<section class="doc-section"><h3>决策、验收与风险收束</h3>'+render_value(narrative.get('conclusion'))+'</section>')
    state='' if kind=='release' else f'<p class="muted">当前阶段状态：{esc(phase.get("state","待补充"))}</p>'
    return f'<article class="doc-phase"><h2>{esc(phase["id"])} · {esc(phase["name"])}</h2>'+state+''.join(contents)+'</article>'


def document_contents(detail,kind,phase_ids=None,version=None,phase_html=None):
    if kind not in TITLES:
        raise ValueError('Unknown document kind')
    ids=phase_ids or list(detail['phases'])
    if kind=='release':
        label=('版本快照 '+version) if version else '当前台账'
        top='<p class="muted small">'+esc(detail['project'])+' · '+esc(detail['task']['taskId'])+' · '+esc(label)+'</p>'
        if detail.get('dirtyExports'):
            top+='<p class="doc-note">有外部文件改动待同步；此页展示 SQLite 已保存内容。</p>'
        body=phase_html if phase_html is not None else ''.join(render_phase(detail['phases'][p],kind) for p in ids)
        return top+body
    phases=[detail['phases'][p] for p in ids]
    revisions=' / '.join(p+': r'+str(detail['revisions']['phases/'+p+'.json']) for p in ids)
    metadata={'项目':detail['project'],'任务编号':detail['task']['taskId'],'负责人':detail['task'].get('owner','待确认'),'文档版本':version or '当前台账','数据版本':'task r'+str(detail['revisions']['task.json'])+' · '+revisions,'更新时间':detail['updated_at'],'生命周期状态':detail['task'].get('state'),'归档状态':detail['archive_state']}
    top='<div class="doc-meta">'+''.join('<div><span class="muted">'+esc(k)+'</span><strong>'+esc(v)+'</strong></div>' for k,v in metadata.items())+'</div>'
    top+='<p class="doc-note">'+('这是版本快照，内容截至导出时；后续更新请查看工作台当前台账。' if version else '内容来自当前台账；空项标为待补充，完成与确认以实际记录为准。')+'</p>'
    if detail.get('dirtyExports'):
        top+='<p class="doc-note">有外部文件改动待同步；此页展示 SQLite 已保存内容。</p>'
    body=phase_html if phase_html is not None else ''.join(render_phase(p,kind) for p in phases)
    history=[{'at':e.get('at'),'type':e.get('type'),'summary':e.get('summary')} for e in detail['events'][-20:]][::-1]
    return top+body+'<section class="doc-section"><h2>最近变更记录</h2>'+render_value(history)+'</section>'


def export_document(store,key,phase_id,kind,version):
    if kind not in TITLES or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}',version):
        raise ValueError('Use a valid document kind and simple version such as v0.1')
    detail=store.detail(key)
    if detail['archive_state'] not in ('active','failed'):
        raise ValueError('Archived or archiving documents are read-only')
    if phase_id not in detail['phases'] or not re.fullmatch(r'P[1-9][0-9]*',phase_id):
        raise ValueError('Unknown Phase')
    if detail.get('dirtyExports'):
        raise ValueError('Reconcile files edited outside SQLite before exporting a document')
    title=detail['task']['title']+' · '+TITLES[kind]
    content=document_contents(detail,kind,[phase_id],version)
    css=(ASSETS/'workspace.css').read_text()+'\n'+(ASSETS/'document.css').read_text()
    source='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+esc(title)+'</title><style>'+css+'</style></head><body><main class="document-page"><h1>'+esc(title)+'</h1>'+content+'<footer>HTML 交付规范 v1 · 导出于 '+esc(stamp())+'</footer></main></body></html>'
    root=Path(detail['task_dir'])
    parent=root/'deliverables'/phase_id/kind
    for folder in (root/'deliverables',root/'deliverables'/phase_id,parent):
        if folder.is_symlink():
            raise ValueError('Document output must not use symlinks')
        folder.mkdir(exist_ok=True)
    path=parent/(version+'.html')
    # Exclusive create preserves previously reviewed versions.
    with path.open('x',encoding='utf-8') as output:
        output.write(source)
    try:
        identifier=store.add_deliverable(key,phase_id,kind,TITLES[kind],path,version)
    except Exception:
        path.unlink()
        raise
    return {'ok':True,'path':str(path),'deliverableId':identifier,'version':version}
