"""SQLite source of truth for lifecycle tasks; JSON files are review exports."""
from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import threading
import uuid

MARKER = '.lifecycle-store.json'
KINDS = ('product', 'technical', 'ui', 'development', 'testing', 'release')
LABELS = ('产品', '技术', 'UI', '开发', '测试', '上线')
READ_REVISIONS = {}


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def default_database():
    base = Path(os.environ.get('LIFECYCLE_HOME', str(Path.home() / '.codex' / 'lifecycle')))
    return base.expanduser().resolve() / 'workspace.sqlite3'


def write_file(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temp.open('w', encoding='utf-8') as out:
            os.chmod(temp, 0o600)
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def binding(path):
    path = Path(path).resolve()
    candidates = [path.parent, path.parent.parent] if path.suffix else [path]
    for root in candidates:
        marker = root / MARKER
        if marker.is_file():
            value = json.loads(marker.read_text(encoding='utf-8'))
            name = path.relative_to(root).as_posix() if path != root else ''
            if name and name not in ('task.json', 'comments.json', 'events.jsonl') and not re.fullmatch(r'phases/[^/]+\.json', name):
                continue
            return Store(value['database']), value['taskKey'], name
    return None


class Store:
    def __init__(self, database=None):
        self.path = Path(database or default_database()).expanduser().resolve()
        self.home = self.path.parent
        self.home.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self.connect() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version > 1:
                raise ValueError('Database schema is newer than this skill; upgrade before opening it')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS tasks (
                    key TEXT PRIMARY KEY, task_dir TEXT NOT NULL UNIQUE,
                    project TEXT NOT NULL, project_root TEXT NOT NULL DEFAULT '',
                    thread_id TEXT, host_id TEXT NOT NULL DEFAULT 'local',
                    stage TEXT, archive_state TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS documents (
                    task_key TEXT NOT NULL REFERENCES tasks(key), name TEXT NOT NULL,
                    data TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY(task_key,name)
                );
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, task_key TEXT NOT NULL REFERENCES tasks(key),
                    event_id TEXT NOT NULL, data TEXT NOT NULL, UNIQUE(task_key,event_id)
                );
                CREATE TABLE IF NOT EXISTS exports (
                    task_key TEXT NOT NULL REFERENCES tasks(key), name TEXT NOT NULL,
                    fingerprint TEXT NOT NULL, PRIMARY KEY(task_key,name)
                );
                CREATE TABLE IF NOT EXISTS deliverables (
                    id TEXT PRIMARY KEY, task_key TEXT NOT NULL REFERENCES tasks(key),
                    phase_id TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL,
                    relative_path TEXT NOT NULL, version TEXT NOT NULL, created_at TEXT NOT NULL,
                    UNIQUE(task_key,relative_path)
                );
                CREATE TABLE IF NOT EXISTS archives (
                    task_key TEXT PRIMARY KEY REFERENCES tasks(key), archive_id TEXT NOT NULL UNIQUE,
                    state TEXT NOT NULL, archived_at TEXT, expires_at TEXT, copy_state TEXT NOT NULL,
                    error TEXT, requested_at TEXT NOT NULL, cleaned_at TEXT
                );
                PRAGMA user_version=1;
            ''')
        os.chmod(self.path, 0o600)

    @contextlib.contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA synchronous=FULL')
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def row(self, key):
        with self.connect() as db:
            row = db.execute('SELECT * FROM tasks WHERE key=?', (key,)).fetchone()
        if row is None:
            raise ValueError('Unknown workspace task')
        return dict(row)

    def import_task(self, root, project=None, project_root='', thread_id=None):
        root = Path(root).resolve()
        if (root / MARKER).exists():
            current = binding(root)
            if current[0].path != self.path:
                raise ValueError('Task already belongs to a different database')
            return current[1]
        task = json.loads((root / 'task.json').read_text(encoding='utf-8'))
        if task.get('schemaVersion') != 2:
            raise ValueError('Only structured V2 tasks can be imported; V1 is left untouched')
        names = ['task.json', 'comments.json'] + [entry['file'] for entry in task['phases']]
        records = []
        fingerprints = {}
        for name in names:
            path = (root / name).resolve()
            if root not in path.parents or not path.is_file():
                raise ValueError('Missing or unsafe task source: ' + name)
            raw = path.read_bytes()
            fingerprints[name] = hashlib.sha256(raw).hexdigest()
            records.append((name,json.loads(raw)))
        if records[0][1] != task:
            raise ValueError('Task changed while importing; retry after the current update completes')
        events = [json.loads(line) for line in (root / 'events.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()] if (root / 'events.jsonl').exists() else []
        key = uuid.uuid4().hex
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if any(hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest for name,digest in fingerprints.items()):
                raise ValueError('Task source changed while importing; retry with a stable snapshot')
            prior = db.execute('SELECT key FROM tasks WHERE task_dir=?', (str(root),)).fetchone()
            if prior:
                key = prior['key']
            else:
                db.execute('INSERT INTO tasks(key,task_dir,project,project_root,thread_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                           (key, str(root), project or Path(project_root).name or '未分组项目', str(project_root), thread_id, stamp(), stamp()))
                db.executemany('INSERT INTO documents(task_key,name,data) VALUES(?,?,?)', [(key, name, json.dumps(value, ensure_ascii=False)) for name,value in records])
                db.executemany('INSERT INTO exports VALUES(?,?,?)', [(key,name,fingerprints[name]) for name,_ in records])
                if (root/'events.jsonl').is_file():
                    db.execute('INSERT INTO exports VALUES(?,?,?)',(key,'events.jsonl',hashlib.sha256((root/'events.jsonl').read_bytes()).hexdigest()))
                db.executemany('INSERT INTO events(task_key,event_id,data) VALUES(?,?,?)', [(key,e['id'],json.dumps(e, ensure_ascii=False)) for e in events])
        write_file(root / MARKER, json.dumps({'version':3, 'database':str(self.path), 'taskKey':key}, indent=2) + '\n')
        return key

    def get_document(self, key, name):
        with self.connect() as db:
            row = db.execute('SELECT data,revision FROM documents WHERE task_key=? AND name=?', (key,name)).fetchone()
        if row is None:
            raise FileNotFoundError(name)
        READ_REVISIONS[(threading.get_ident(),str(self.path),key,name)] = row['revision']
        return json.loads(row['data']), row['revision']

    def check_export(self,key,name):
        path = Path(self.row(key)['task_dir'])/name
        with self.connect() as db:
            previous = db.execute('SELECT fingerprint FROM exports WHERE task_key=? AND name=?',(key,name)).fetchone()
        if previous and path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()!=previous['fingerprint']:
            raise ValueError('JSON export was edited outside SQLite: '+name+'; preserve these edits and reconcile them with workspace read/update before continuing')

    def exported_file(self,key,name,data,allow_dirty=False):
        if not allow_dirty:
            self.check_export(key,name)
        path = Path(self.row(key)['task_dir'])/name
        write_file(path,data)
        with self.connect() as db:
            db.execute('INSERT INTO exports VALUES(?,?,?) ON CONFLICT(task_key,name) DO UPDATE SET fingerprint=excluded.fingerprint',(key,name,hashlib.sha256(data.encode()).hexdigest()))

    def put_document(self, key, name, value, expected=None, allow_dirty_export=False):
        if name not in ('task.json','comments.json') and not re.fullmatch(r'phases/[^/]+\.json', name):
            raise ValueError('Unsupported structured document')
        if not isinstance(value, dict):
            raise ValueError('Structured documents must be JSON objects')
        if name.startswith('phases/') and 'execution' in value:
            from workspace_status import validate_execution
            validate_execution(value['execution'])
        if not allow_dirty_export:
            self.check_export(key,name)
        if expected is None:
            expected = READ_REVISIONS.get((threading.get_ident(),str(self.path),key,name))
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            task = db.execute('SELECT * FROM tasks WHERE key=?', (key,)).fetchone()
            if task is None or task['archive_state'] not in ('active','failed'):
                raise ValueError('Task is archived or archiving; source updates are locked')
            current = db.execute('SELECT revision FROM documents WHERE task_key=? AND name=?', (key,name)).fetchone()
            if current and (expected is None or current['revision'] != expected):
                raise ValueError('Concurrent update detected; read current revision and reapply the change')
            revision = current['revision'] + 1 if current else 1
            db.execute('INSERT INTO documents(task_key,name,data,revision) VALUES(?,?,?,?) ON CONFLICT(task_key,name) DO UPDATE SET data=excluded.data,revision=excluded.revision',
                       (key,name,json.dumps(value,ensure_ascii=False),revision))
            db.execute('UPDATE tasks SET updated_at=? WHERE key=?', (stamp(),key))
        READ_REVISIONS[(threading.get_ident(),str(self.path),key,name)] = revision
        self.exported_file(key,name,json.dumps(value,ensure_ascii=False,indent=2)+'\n',allow_dirty=allow_dirty_export)
        return revision

    def events(self, key):
        with self.connect() as db:
            return [json.loads(r['data']) for r in db.execute('SELECT data FROM events WHERE task_key=? ORDER BY seq', (key,))]

    def event(self, key, event):
        with self.connect() as db:
            db.execute('INSERT INTO events(task_key,event_id,data) VALUES(?,?,?)', (key,event['id'],json.dumps(event,ensure_ascii=False)))

    def audit(self, key, kind, summary, **details):
        self.event(key, {'id':'EVT-'+uuid.uuid4().hex, 'at':stamp(), 'type':kind, 'summary':summary, **details})

    def export(self, key):
        root = Path(self.row(key)['task_dir'])
        with self.connect() as db:
            docs = db.execute('SELECT name,data FROM documents WHERE task_key=?', (key,)).fetchall()
        for record in docs:
            self.check_export(key,record['name'])
        self.check_export(key,'events.jsonl')
        for record in docs:
            self.exported_file(key,record['name'],json.dumps(json.loads(record['data']),ensure_ascii=False,indent=2)+'\n')
        self.exported_file(key,'events.jsonl',''.join(json.dumps(e,ensure_ascii=False)+'\n' for e in self.events(key)))

    def configure(self, key, transfer_thread=False, **fields):
        allowed = {'project','project_root','thread_id','host_id','stage'}
        fields = {k:v for k,v in fields.items() if k in allowed and v is not None}
        if fields.get('stage') and fields['stage'] not in KINDS:
            raise ValueError('Unknown board stage')
        if fields.get('thread_id') and not re.fullmatch(r'[0-9a-fA-F-]{32,36}', fields['thread_id']):
            raise ValueError('Use the actual Codex thread UUID')
        if not fields:
            return
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT archive_state FROM tasks WHERE key=?', (key,)).fetchone()
            if not row or row['archive_state'] not in ('active','failed'):
                raise ValueError('Archived task binding is locked')
            if fields.get('thread_id'):
                other = db.execute("SELECT key FROM tasks WHERE thread_id=? AND key<>? AND archive_state<>'archived'", (fields['thread_id'],key)).fetchone()
                if other:
                    if not transfer_thread:
                        raise ValueError('This Codex conversation is already bound to another active lifecycle task; use --transfer-thread only for an explicitly requested new task in this conversation')
                    db.execute('UPDATE tasks SET thread_id=NULL,updated_at=? WHERE key=?',(stamp(),other['key']))
                    event={'id':'EVT-'+uuid.uuid4().hex,'at':stamp(),'type':'conversation-binding-transferred','summary':'The conversation was explicitly rebound to a new lifecycle task','threadId':fields['thread_id'],'newTaskKey':key}
                    db.execute('INSERT INTO events(task_key,event_id,data) VALUES(?,?,?)',(other['key'],event['id'],json.dumps(event,ensure_ascii=False)))
            db.execute('UPDATE tasks SET '+','.join(k+'=?' for k in fields)+',updated_at=? WHERE key=?', (*fields.values(),stamp(),key))
        self.audit(key,'workspace-configured','Updated project, board stage or Codex binding', fields=fields)

    def add_deliverable(self, key, phase, kind, title, path, version):
        row = self.row(key)
        if row['archive_state'] not in ('active','failed'):
            raise ValueError('Archived deliverables are read-only')
        if kind not in KINDS:
            raise ValueError('Unknown deliverable kind')
        root = Path(row['task_dir']).resolve()
        source = Path(path).expanduser().resolve()
        original = Path(path).expanduser().absolute()
        if root not in source.parents or not source.is_file() or original.is_symlink():
            raise ValueError('Deliverable must be a file inside the task directory')
        if not source.relative_to(root).as_posix().startswith(('deliverables/','evidence/')):
            raise ValueError('Store deliverable files under deliverables/ or evidence/ inside the task')
        relative = source.relative_to(root).as_posix()
        artifact_id = uuid.uuid4().hex
        with self.connect() as db:
            prior = db.execute('SELECT id FROM deliverables WHERE task_key=? AND relative_path=?',(key,relative)).fetchone()
            artifact_id = prior['id'] if prior else artifact_id
            db.execute('INSERT INTO deliverables VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(task_key,relative_path) DO UPDATE SET title=excluded.title,version=excluded.version,kind=excluded.kind,phase_id=excluded.phase_id',
                       (artifact_id,key,phase,kind,title,relative,version,stamp()))
        self.audit(key,'deliverable-registered',title,artifactId=artifact_id,version=version,path=relative)
        return artifact_id

    def detail(self, key):
        row = self.row(key)
        with self.connect() as db:
            documents = {r['name']:json.loads(r['data']) for r in db.execute('SELECT * FROM documents WHERE task_key=?',(key,))}
            revisions = {r['name']:r['revision'] for r in db.execute('SELECT name,revision FROM documents WHERE task_key=?',(key,))}
            artifacts = [dict(r) for r in db.execute('SELECT * FROM deliverables WHERE task_key=? ORDER BY created_at',(key,))]
            archive = db.execute('SELECT * FROM archives WHERE task_key=?',(key,)).fetchone()
            exports = db.execute('SELECT name,fingerprint FROM exports WHERE task_key=?',(key,)).fetchall()
        dirty=[]
        for exported in exports:
            path=Path(row['task_dir'])/exported['name']
            if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()!=exported['fingerprint']:
                dirty.append(exported['name'])
        return {**row,'task':documents['task.json'],'phases':{n.split('/')[-1][:-5]:v for n,v in documents.items() if n.startswith('phases/')},
                'comments':documents.get('comments.json',{}),'revisions':revisions,'deliverables':artifacts,'archive':dict(archive) if archive else None,'events':self.events(key),'dirtyExports':dirty}

    def list_tasks(self):
        with self.connect() as db:
            keys = [r['key'] for r in db.execute('SELECT key FROM tasks ORDER BY updated_at DESC')]
        return [self.detail(key) for key in keys]

    def archive_path(self, archive_id):
        if not re.fullmatch(r'[a-f0-9]{32}', archive_id):
            raise ValueError('Invalid archive identifier')
        root = self.home / 'archives'
        root.mkdir(mode=0o700, exist_ok=True)
        if root.is_symlink():
            raise ValueError('Archive root must not be a symlink')
        path = root / archive_id
        if path.is_symlink() or path.resolve().parent != root.resolve():
            raise ValueError('Unsafe archive path')
        return path

    def archive(self, key, codex):
        detail = self.detail(key)
        if detail['archive_state'] == 'archived':
            return detail['archive']
        if not detail['thread_id']:
            raise ValueError('Bind this task to its Codex conversation before archiving')
        if detail['host_id'] != 'local':
            raise ValueError('Only local Codex conversations are supported by this local archive service')
        # A retry keeps the saved copy. An uncertain remote result is reconciled first.
        prior = detail['archive']
        archive_id = prior['archive_id'] if prior else uuid.uuid4().hex
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            state = db.execute('SELECT archive_state FROM tasks WHERE key=?',(key,)).fetchone()[0]
            if state not in ('active','failed','uncertain'):
                raise ValueError('Archive is already in progress')
            current_docs = {r['name']:r['revision'] for r in db.execute('SELECT name,revision FROM documents WHERE task_key=?',(key,))}
            if current_docs != detail['revisions']:
                raise ValueError('Task changed while preparing archive; retry with the latest state')
            db.execute("UPDATE tasks SET archive_state='copying' WHERE key=?",(key,))
            db.execute("INSERT INTO archives(task_key,archive_id,state,copy_state,requested_at) VALUES(?,?,'copying','pending',?) ON CONFLICT(task_key) DO UPDATE SET state='copying',error=NULL",(key,archive_id,stamp()))
        path = self.archive_path(archive_id)
        remote_attempted = False
        try:
            # Metadata read does not copy raw command output or authentication material.
            metadata = codex.read(detail['thread_id'])
            if metadata.get('status',{}).get('type') == 'active':
                raise ValueError('Codex conversation is running; wait for its current turn to stop before archiving')
            if path.exists():
                owner = json.loads((path/'owner.json').read_text())
                if owner != {'taskKey':key,'archiveId':archive_id}:
                    raise ValueError('Archive snapshot ownership mismatch')
                if (prior and prior['state']=='failed') or not (path/'manifest.json').is_file():
                    shutil.rmtree(path)
            if not path.exists():
                self.export(key)
                path.mkdir(mode=0o700)
                write_file(path/'owner.json',json.dumps({'taskKey':key,'archiveId':archive_id}))
                root = Path(detail['task_dir'])
                allowed = ['task.json','comments.json','events.jsonl','index.html','phases','evidence','deliverables']
                for name in allowed:
                    source = root / name
                    if not source.exists():
                        continue
                    if source.is_symlink() or (source.is_dir() and any(p.is_symlink() for p in source.rglob('*'))):
                        raise ValueError('Archive sources must not contain symlinks')
                    if source.is_dir():
                        shutil.copytree(source,path/name)
                    else:
                        shutil.copy2(source,path/name)
                write_file(path/'conversation.json',json.dumps({k:metadata.get(k) for k in ('id','name','createdAt','updatedAt')},ensure_ascii=False,indent=2))
                write_file(path/'deliverables.json',json.dumps(detail['deliverables'],ensure_ascii=False,indent=2))
                manifest = {p.relative_to(path).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in path.rglob('*') if p.is_file()}
                write_file(path/'manifest.json',json.dumps({'taskKey':key,'archiveId':archive_id,'files':manifest},indent=2))
            manifest = json.loads((path/'manifest.json').read_text())
            if manifest.get('taskKey') != key:
                raise ValueError('Archive snapshot identity mismatch')
            for name,digest in manifest['files'].items():
                source = (path/name).resolve()
                if path.resolve() not in source.parents or hashlib.sha256(source.read_bytes()).hexdigest()!=digest:
                    raise ValueError('Archive snapshot verification failed')
            with self.connect() as db:
                db.execute("UPDATE archives SET state='codex-pending',copy_state='saved' WHERE task_key=?",(key,))
            remote_attempted = True
            if not codex.is_archived(detail['thread_id']):
                codex.archive(detail['thread_id'])
            if not codex.is_archived(detail['thread_id']):
                raise ValueError('Codex archive could not be verified; retry to reconcile')
            archived_at = stamp()
            expires = (dt.datetime.fromisoformat(archived_at)+dt.timedelta(days=30)).isoformat()
            with self.connect() as db:
                db.execute("UPDATE tasks SET archive_state='archived',updated_at=? WHERE key=?",(archived_at,key))
                db.execute("UPDATE archives SET state='archived',archived_at=?,expires_at=?,error=NULL WHERE task_key=?",(archived_at,expires,key))
            self.audit(key,'task-archived','User archived the task and Codex conversation',archiveId=archive_id,expiresAt=expires,lifecycleState=detail['task'].get('state'),phaseStates={p:v.get('state') for p,v in detail['phases'].items()})
            return self.detail(key)['archive']
        except Exception as error:
            state = 'uncertain' if remote_attempted else 'failed'
            with self.connect() as db:
                db.execute('UPDATE tasks SET archive_state=? WHERE key=?',(state,key))
                db.execute('UPDATE archives SET state=?,error=? WHERE task_key=?',(state,str(error),key))
            self.audit(key,'archive-failed','Archive did not complete',error=str(error),state=state)
            raise

    def cleanup(self, now=None):
        now = now or dt.datetime.now(dt.timezone.utc)
        with self.connect() as db:
            due = [dict(r) for r in db.execute("SELECT * FROM archives WHERE state='archived' AND copy_state='saved' AND expires_at<=?",(now.isoformat(),))]
        cleaned = []
        for row in due:
            path = self.archive_path(row['archive_id'])
            if path.exists():
                manifest = json.loads((path/'manifest.json').read_text())
                if manifest.get('taskKey') != row['task_key'] or manifest.get('archiveId') != row['archive_id']:
                    raise ValueError('Cleanup refused an unowned archive directory')
                shutil.rmtree(path)
            with self.connect() as db:
                db.execute("UPDATE archives SET copy_state='deleted',cleaned_at=? WHERE task_key=?",(stamp(),row['task_key']))
            self.audit(row['task_key'],'archive-copy-expired','Deleted the 30-day local archive copy; source files and Codex conversation retained')
            cleaned.append(row['task_key'])
        return cleaned
