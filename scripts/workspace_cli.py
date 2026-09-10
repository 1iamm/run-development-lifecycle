"""Workspace subcommands kept separate from the existing lifecycle validators."""
import json
from pathlib import Path
from workspace_store import Store, binding, default_database, KINDS, stamp


def output(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0


def bound_task(directory):
    value = binding(Path(directory).expanduser().resolve())
    if not value:
        raise ValueError('This task is not in SQLite yet; use workspace import first')
    return value[0], value[1]


def command(args):
    action = args.workspace_action
    if action in ('list','import','serve','cleanup','backup'):
        store = Store(args.database)
    else:
        store,key = bound_task(args.task_dir)
    if action == 'import':
        key = store.import_task(args.task_dir,args.project,args.project_root)
        return output({'ok':True,'taskKey':key,'database':str(store.path)})
    if action == 'list':
        from workspace_server import summary
        return output({'database':str(store.path),'tasks':[summary(t) for t in store.list_tasks()]})
    if action == 'read':
        data,revision = store.get_document(key,args.document)
        return output({'document':args.document,'revision':revision,'data':data})
    if action == 'activity':
        name = 'phases/'+args.phase+'.json'
        phase,revision = store.get_document(key,name)
        phase['execution'] = {
            'status':args.status,'summary':args.summary,
            'requiredAction':args.required_action or '', 'updatedAt':stamp(),
        }
        revision = store.put_document(key,name,phase,args.expected_revision)
        store.audit(key,'execution-update',args.summary,phase=args.phase,execution=phase['execution'])
        from lifecycle import render_task
        render_task(Path(args.task_dir).resolve())
        return output({'ok':True,'revision':revision,'execution':phase['execution']})
    if action == 'update':
        value = json.loads(Path(args.file).read_text(encoding='utf-8'))
        revision = store.put_document(key,args.document,value,args.expected_revision,allow_dirty_export=True)
        store.audit(key,'structured-update','Updated '+args.document,document=args.document,revision=revision)
        from lifecycle import render_task
        render_task(Path(args.task_dir).resolve())
        return output({'ok':True,'revision':revision})
    if action == 'bind':
        if args.thread_id:
            from codex_bridge import CodexBridge
            with CodexBridge() as codex:
                codex.read(args.thread_id)
        store.configure(key,transfer_thread=args.transfer_thread,project=args.project,project_root=args.project_root,thread_id=args.thread_id,stage=args.stage)
        return output({'ok':True,'taskKey':key})
    if action == 'document':
        from workspace_documents import export_document
        return output(export_document(store,key,args.phase,args.kind,args.version))
    if action == 'deliverable':
        identifier = store.add_deliverable(key,args.phase,args.kind,args.title,args.path,args.version)
        return output({'ok':True,'deliverableId':identifier})
    if action == 'cleanup':
        return output({'ok':True,'cleaned':store.cleanup()})
    if action == 'backup':
        import sqlite3
        target = Path(args.output).expanduser().resolve()
        if target.exists() or target == store.path:
            raise ValueError('Backup destination must be a new file')
        target.parent.mkdir(parents=True,exist_ok=True)
        with store.connect() as source, sqlite3.connect(target) as destination:
            source.backup(destination)
        target.chmod(0o600)
        return output({'ok':True,'databaseBackup':str(target),'note':'Deliverable source files are backed up separately; archive copies retain their 30-day policy'})
    if action == 'archive':
        if not args.user_requested:
            raise ValueError('Archiving requires a manual user request; DONE alone is not authorization')
        from codex_bridge import CodexBridge
        with CodexBridge() as codex:
            result = store.archive(key,codex)
        return output({'ok':True,'archive':result})
    if action == 'serve':
        from workspace_server import serve
        serve(store,args.port)
        return 0
    raise ValueError('Unknown workspace command')


def add_commands(commands):
    workspace = commands.add_parser('workspace',help='SQLite multi-project board and archive manager')
    subs = workspace.add_subparsers(dest='workspace_action',required=True)
    for action in ('list','serve','cleanup','backup'):
        parser = subs.add_parser(action)
        parser.add_argument('--database',default=str(default_database()))
        if action == 'serve':
            parser.add_argument('--port',type=int,default=8765)
        if action == 'backup':
            parser.add_argument('--output',required=True)
        parser.set_defaults(function=command)
    imp = subs.add_parser('import',help='Import one identified V2 task without changing its lifecycle state')
    imp.add_argument('task_dir')
    imp.add_argument('--database',default=str(default_database()))
    imp.add_argument('--project')
    imp.add_argument('--project-root',default='')
    imp.set_defaults(function=command)
    for action in ('read','update','activity','bind','deliverable','document','archive'):
        parser = subs.add_parser(action)
        parser.add_argument('task_dir')
        if action in ('read','update'):
            parser.add_argument('--document',default='task.json')
        if action == 'update':
            parser.add_argument('--file',required=True,help='JSON input file outside the generated export paths')
            parser.add_argument('--expected-revision',type=int,required=True)
        if action == 'activity':
            parser.add_argument('--phase',required=True)
            parser.add_argument('--status',choices=('active','blocked'),required=True)
            parser.add_argument('--summary',required=True,help='Current agent work or reason waiting for the user')
            parser.add_argument('--required-action',help='Concrete user action; required only when blocked')
            parser.add_argument('--expected-revision',type=int,required=True)
        if action == 'bind':
            parser.add_argument('--project')
            parser.add_argument('--project-root')
            parser.add_argument('--thread-id')
            parser.add_argument('--stage',choices=KINDS)
            parser.add_argument('--transfer-thread',action='store_true',help='Explicitly rebind this conversation from its previous active lifecycle task')
        if action == 'deliverable':
            parser.add_argument('--phase',default='P1')
            parser.add_argument('--kind',choices=KINDS,required=True)
            parser.add_argument('--title',required=True)
            parser.add_argument('--path',required=True)
            parser.add_argument('--version',required=True)
        if action == 'document':
            parser.add_argument('--phase',default='P1')
            parser.add_argument('--kind',choices=KINDS,required=True)
            parser.add_argument('--version',required=True)
        if action == 'archive':
            parser.add_argument('--user-requested',action='store_true')
        parser.set_defaults(function=command)
