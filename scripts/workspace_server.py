"""Loopback-only workbench with independent document pages and manual archive."""
from __future__ import annotations
import datetime as dt
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import secrets
import threading
from urllib.parse import parse_qs, unquote, urlsplit

from workspace_store import Store, KINDS, LABELS, stamp

ASSETS = Path(__file__).resolve().parents[1] / 'assets'
from workspace_documents import KEY_LABELS, TITLES, document_contents, render_phase


def board_stage(detail):
    task = detail['task']
    phase = detail['phases'].get(task.get('activePhase'),{})
    state = phase.get('state',task.get('state','DISCOVERY'))
    if task.get('state') == 'DONE':
        return 'release'
    if state in ('DISCOVERY','REQUIREMENTS_REVIEW'):
        return 'product'
    if state in ('REQUIREMENTS_APPROVED','DESIGN_REVIEW'):
        # Technical and UI design share one lifecycle gate, but have distinct board columns.
        if detail.get('stage') in ('technical','ui'):
            return detail['stage']
        artifacts = phase.get('artifacts',{})
        ui = artifacts.get('uiDesign',{})
        if phase.get('applicability',{}).get('uiChange') and ui.get('status') == 'pending' and any(v.get('status')=='complete' for k,v in artifacts.items() if k!='uiDesign' and isinstance(v,dict)):
            return 'ui'
        return 'technical'
    if state in ('DESIGN_APPROVED','IMPLEMENTING','FIXING'):
        return 'development'
    if state in ('LOCAL_VERIFY','E2E'):
        return 'testing'
    return 'release'


def summary(detail):
    task = detail['task']
    phases = list(detail['phases'].values())
    active = detail['phases'].get(task.get('activePhase'),{})
    # Progress is based on declared checklist items, never invented time estimates.
    checklist = task.get('workItems',[])
    if not checklist:
        checklist = [item for phase in phases for item in phase.get('workItems',[])]
    total = len(checklist)
    completed = sum(1 for item in checklist if isinstance(item,dict) and item.get('status') in ('DONE','done','PASS','complete'))
    from workspace_status import execution_status
    execution = execution_status(detail)
    state = active.get('state',task.get('state'))
    dirty=detail.get('dirtyExports',[])
    status = execution['status']
    return {k:detail[k] for k in ('key','project','thread_id','host_id','archive_state','stage')} | {
        'taskId':task['taskId'],'title':task['title'],'state':state,'stage':board_stage(detail),'status':status,
        'activePhase':task.get('activePhase'),'phaseCount':len(phases),'completed':completed,'total':total,
        'progress':round(completed*100/total) if total else (100 if status=='done' else None),
        'nextAction':('有外部文件改动待同步：'+', '.join(dirty)) if dirty else active.get('nextAction') or task.get('nextAction',''),
        'updatedAt':detail['updated_at'],'targetDate':task.get('targetDate',''),'archive':detail['archive'],
        'artifactCount':len(detail['deliverables']),
    } | execution


def safe_file(root, relative):
    root = root.resolve()
    path = root / relative
    # Resolve and inspect each component; do not expose arbitrary project files.
    if path.is_symlink() or root not in path.resolve().parents or not path.is_file():
        raise ValueError('File is unavailable or outside this task')
    part = path
    while part != root:
        if part.is_symlink():
            raise ValueError('Symlink files are not served')
        part = part.parent
    return path


def document_page(title, contents, back='/'):
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><link rel="stylesheet" href="/workspace.css"><link rel="stylesheet" href="/document.css"><script defer src="/checklist.js"></script><body><main class="document-page"><a href="{html.escape(back,quote=True)}">← 返回任务</a><h1>{html.escape(title)}</h1><p id="checklist-status" role="status"></p>{contents}</main></body></html>'''


def html_deliverable_page(record):
    """Give sandboxed HTML the viewport below a compact task navigation bar."""
    title = html.escape(record['title'] + (' · ' + record['version'] if record['version'] else ''))
    back = html.escape('/?task=' + record['task_key'], quote=True)
    source = html.escape('/raw/' + record['id'], quote=True)
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><link rel="stylesheet" href="/workspace.css"></head>
<body class="deliverable-viewer">
<header class="deliverable-toolbar"><a href="{back}">← 返回任务</a><h1 title="{title}">{title}</h1></header>
<main class="deliverable-content"><iframe class="deliverable-frame" sandbox="allow-scripts" src="{source}" title="{title}"></iframe></main>
</body></html>'''


def structured_html(value):
    if isinstance(value,dict):
        return '<dl>'+''.join('<dt>'+html.escape(KEY_LABELS.get(k,str(k)))+'</dt><dd>'+structured_html(v)+'</dd>' for k,v in value.items())+'</dl>'
    if isinstance(value,list):
        return '<ul>'+''.join('<li>'+structured_html(v)+'</li>' for v in value)+'</ul>' if value else '<span class="muted">暂无记录</span>'
    return '<span>'+html.escape(str(value if value is not None else '—'))+'</span>'


def markdown_html(text):
    # Minimal offline Markdown display, with all source HTML escaped.
    blocks = []
    code = []
    in_code = False
    for line in text.splitlines():
        if line.startswith('```'):
            if in_code:
                blocks.append('<pre><code>'+html.escape('\n'.join(code))+'</code></pre>')
                code = []
            in_code = not in_code
        elif in_code:
            code.append(line)
        elif line.startswith('#'):
            depth = min(len(line)-len(line.lstrip('#')),6)
            blocks.append(f'<h{depth}>'+html.escape(line[depth:].strip())+f'</h{depth}>')
        elif line.strip():
            blocks.append('<p>'+html.escape(line)+'</p>')
    if code:
        blocks.append('<pre>'+html.escape('\n'.join(code))+'</pre>')
    return ''.join(blocks)


class WorkspaceHTTP(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self,address,store,codex_factory=None):
        super().__init__(address,Handler)
        self.store = store
        self.token = secrets.token_urlsafe(32)
        self.codex_factory = codex_factory
        self.archive_lock = threading.Lock()
        self.cleanup_error = None
        # Interrupted copying never claims success; uncertain outcomes must be reconciled.
        with store.connect() as db:
            db.execute("UPDATE tasks SET archive_state='uncertain' WHERE archive_state='copying'")
            db.execute("UPDATE archives SET state='uncertain',error='Service restarted during archive; retry to reconcile' WHERE state IN ('copying','codex-pending')")


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):
        pass

    def respond(self,data,content_type='application/json; charset=utf-8',status=200,sandbox=False):
        if isinstance(data,dict):
            data = json.dumps(data,ensure_ascii=False)
        data = data.encode('utf-8') if isinstance(data,str) else data
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; frame-ancestors 'self'" if sandbox else "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-src 'self'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'")
        self.end_headers()
        self.wfile.write(data)

    def trusted_host(self):
        return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')

    def do_GET(self):
        if not self.trusted_host():
            self.respond({'error':'Invalid Host'},status=403)
            return
        try:
            self.get()
        except (ValueError,FileNotFoundError,KeyError) as error:
            self.respond({'error':str(error)},status=404)

    def get(self):
        request = urlsplit(self.path)
        parts = [unquote(p) for p in request.path.split('/') if p]
        store = self.server.store
        if request.path in ('/','/workspace.js','/workspace.css','/document.css','/checklist.js'):
            name = 'workspace.html' if request.path=='/' else request.path[1:]
            self.respond((ASSETS/name).read_bytes(),mimetypes.guess_type(name)[0]+'; charset=utf-8')
        elif request.path == '/api/workspace':
            self.respond({'tasks':[summary(t) for t in store.list_tasks()],'csrf':self.server.token,'database':str(store.path),'cleanupError':self.server.cleanup_error})
        elif len(parts)==3 and parts[:2]==['api','tasks']:
            detail = store.detail(parts[2])
            self.respond({**detail,'summary':summary(detail)})
        elif len(parts)==4 and parts[0]=='tasks' and parts[2]=='documents':
            key,kind = parts[1],parts[3]
            if kind not in KINDS:
                raise ValueError('Unknown document kind')
            detail = store.detail(key)
            if detail['archive_state']=='archived' and detail['archive']['copy_state']=='deleted':
                raise ValueError('Local archive copy expired; the Codex conversation is retained')
            registered = [d for d in detail['deliverables'] if d['kind']==kind]
            links = ''.join(f'<p><a href="/deliverables/{d["id"]}">{html.escape(d["title"])} · {html.escape(d["version"])}</a></p>' for d in registered)
            phases = []
            for phase in detail['phases'].values():
                checklist = None
                if kind=='release':
                    revision = detail['revisions']['phases/'+phase['id']+'.json']
                    checklist = '<p class="muted small">勾选记录你的确认，不触发部署，也不自动通过完成门禁。</p>'+''.join(
                        f'<label class="release-check"><input type="checkbox" data-task="{key}" data-phase="{html.escape(phase["id"],quote=True)}" data-item="{html.escape(item["id"],quote=True)}" data-revision="{revision}" {"checked" if item.get("checked") else ""} {"disabled" if detail["archive_state"] not in ("active","failed") else ""}><span>{html.escape(item["title"])}<small>{html.escape(item.get("checkedAt","待确认"))}</small></span></label>' for item in phase.get('releaseChecklist',[]))
                phases.append(render_phase(phase,kind,checklist))
            contents = document_contents(detail,kind,phase_html=''.join(phases))
            files = '<section><h2>版本文档与附件</h2>'+links+'</section>' if links else ''
            self.respond(document_page(detail['task']['title']+' · '+TITLES[kind],files+contents,'/?task='+key),'text/html; charset=utf-8')
        elif len(parts)==2 and parts[0] in ('deliverables','raw'):
            with store.connect() as db:
                record = db.execute('SELECT * FROM deliverables WHERE id=?',(parts[1],)).fetchone()
            if record is None:
                raise ValueError('Unknown deliverable')
            detail = store.detail(record['task_key'])
            root = Path(detail['task_dir'])
            if detail['archive_state']=='archived':
                if detail['archive']['copy_state']!='saved':
                    raise ValueError('The local archive copy has expired')
                root = store.archive_path(detail['archive']['archive_id'])
            path = safe_file(root,record['relative_path'])
            mime = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
            if parts[0]=='raw':
                self.respond(path.read_bytes(),mime,sandbox=True)
            else:
                if path.suffix.lower() in ('.html','.htm'):
                    self.respond(html_deliverable_page(record),'text/html; charset=utf-8')
                    return
                elif path.suffix.lower() in ('.png','.jpg','.jpeg','.webp','.gif'):
                    content = f'<img class="design-image" src="/raw/{record["id"]}" alt="{html.escape(record["title"],quote=True)}">'
                elif path.suffix.lower() in ('.md','.txt','.json','.csv'):
                    content = markdown_html(path.read_text(encoding='utf-8'))
                else:
                    content = f'<p><a href="/raw/{record["id"]}" download>下载交付物</a></p>'
                self.respond(document_page(record['title'],content,'/?task='+record['task_key']),'text/html; charset=utf-8')
        else:
            self.respond({'error':'Not found'},status=404)

    def do_POST(self):
        origin = self.headers.get('Origin')
        origins = (f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}')
        if not self.trusted_host() or origin not in origins or not secrets.compare_digest(self.headers.get('X-Lifecycle-Token',''),self.server.token) or self.headers.get_content_type()!='application/json':
            self.respond({'error':'Request must originate from the local workbench'},status=403)
            return
        try:
            length = int(self.headers.get('Content-Length','0'))
            if not 0<length<=65536:
                raise ValueError('Invalid request size')
            body = json.loads(self.rfile.read(length))
            parts = self.path.strip('/').split('/')
            if len(parts)!=4 or parts[:2]!=['api','tasks'] or parts[3] not in ('archive','checklist'):
                self.respond({'error':'Unknown action'},status=404)
                return
            key = parts[2]
            if parts[3]=='checklist':
                phase_id = str(body['phaseId'])
                detail = self.server.store.detail(key)
                if phase_id not in detail['phases'] or type(body.get('checked')) is not bool:
                    raise ValueError('Unknown Phase or invalid check state')
                name = 'phases/'+phase_id+'.json'
                phase,revision = self.server.store.get_document(key,name)
                item = next((i for i in phase.get('releaseChecklist',[]) if i.get('id')==body.get('itemId')),None)
                if not item:
                    raise ValueError('Unknown release checklist item')
                item.update(checked=body['checked'],checkedAt=stamp(),checkedBy='user')
                revision = self.server.store.put_document(key,name,phase,body['expectedRevision'])
                self.server.store.audit(key,'release-checklist-confirmed',item['title'],phaseId=phase_id,itemId=item['id'],checked=body['checked'],source='user-click')
                self.respond({'ok':True,'revision':revision,'checkedAt':item['checkedAt']})
                return
            if body.get('userRequested') is not True:
                raise ValueError('Manual archive action required')
            from codex_bridge import CodexBridge
            if not self.server.archive_lock.acquire(blocking=False):
                self.respond({'error':'An archive operation is in progress; retry when it finishes'},status=409)
                return
            try:
                with (self.server.codex_factory or CodexBridge)() as codex:
                    result = self.server.store.archive(key,codex)
                self.respond({'ok':True,'archive':result})
            finally:
                self.server.archive_lock.release()
        except (ValueError,KeyError,OSError,ConnectionError) as error:
            self.respond({'error':str(error)},status=409)


def serve(store,port):
    try:
        server = WorkspaceHTTP(('127.0.0.1',port),store)
    except OSError as error:
        import errno
        from urllib.request import urlopen
        if error.errno!=errno.EADDRINUSE:
            raise
        try:
            with urlopen(f'http://127.0.0.1:{port}/api/workspace',timeout=3) as response:
                existing=json.load(response)
            if existing.get('database')!=str(store.path):
                raise ValueError('Port belongs to a different workspace')
        except Exception:
            raise ValueError('Port is already in use; choose another --port') from error
        print(json.dumps({'ok':True,'alreadyRunning':True,'url':f'http://127.0.0.1:{port}','database':str(store.path)},ensure_ascii=False),flush=True)
        return
    stop = threading.Event()
    def cleanup_loop():
        while not stop.is_set():
            try:
                store.cleanup()
                server.cleanup_error = None
            except Exception as error:
                server.cleanup_error = str(error)
            stop.wait(60)
    cleaner = threading.Thread(target=cleanup_loop,daemon=True)
    cleaner.start()
    print(json.dumps({'ok':True,'url':f'http://127.0.0.1:{server.server_port}','database':str(store.path),'cleanup':'startup and every 60 seconds'},ensure_ascii=False),flush=True)
    try:
        server.serve_forever(poll_interval=.5)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
