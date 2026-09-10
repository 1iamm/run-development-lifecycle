from __future__ import annotations
import argparse
import contextlib
import datetime as dt
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import lifecycle
from workspace_store import Store, binding, KINDS
from workspace_server import WorkspaceHTTP, summary

THREAD='aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'


class FakeCodex:
    def __init__(self):
        self.archived=False
        self.calls=[]
        self.fail=False
        self.running=False
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def read(self,identifier):
        self.calls.append('read')
        return {'id':identifier,'status':{'type':'active' if self.running else 'notLoaded'}}
    def is_archived(self,identifier):
        self.calls.append('is_archived')
        return self.archived
    def archive(self,identifier):
        self.calls.append('archive')
        if self.fail: raise TimeoutError('Uncertain response')
        self.archived=True


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.store=Store(self.root/'data'/'workspace.sqlite3')
        args=argparse.Namespace(title='SQLite task',root=str(self.root/'tasks'),task_id='DEV-20260910-999',slug='sqlite',phase_name='P1',profile='STANDARD',storage='sqlite',database=str(self.store.path),project='Project A',project_root=str(self.root/'project'),thread_id=None)
        with contextlib.redirect_stdout(io.StringIO()): lifecycle.command_init(args)
        self.task_dir=self.root/'tasks'/'DEV-20260910-999-sqlite'
        self.key=binding(self.task_dir)[1]
        self.store.configure(self.key,thread_id=THREAD)

    def complete(self):
        task=lifecycle.load_task(self.task_dir)
        task['state']='DONE'
        lifecycle.write_json(self.task_dir/'task.json',task)
        phase=lifecycle.load_phases(self.task_dir,task)['P1']
        phase['state']='DONE'
        lifecycle.write_json(self.task_dir/'phases/P1.json',phase)

    def archive(self,codex=None):
        self.complete()
        return self.store.archive(self.key,codex or FakeCodex())

    def test_reopen_database_preserves_state_and_ignores_edited_export(self):
        task,revision=self.store.get_document(self.key,'task.json')
        task['title']='Persisted title'
        self.store.put_document(self.key,'task.json',task,revision)
        (self.task_dir/'task.json').write_text('{"title":"stale export"}')
        reopened=Store(self.store.path)
        self.assertEqual(reopened.get_document(self.key,'task.json')[0]['title'],'Persisted title')
        self.assertEqual(lifecycle.load_task(self.task_dir)['title'],'Persisted title')
        with self.assertRaisesRegex(ValueError,'edited outside SQLite'):
            reopened.export(self.key)
        self.assertEqual(json.loads((self.task_dir/'task.json').read_text())['title'],'stale export')
        task,revision=reopened.get_document(self.key,'task.json')
        reopened.put_document(self.key,'task.json',task,revision,allow_dirty_export=True)
        self.assertEqual(json.loads((self.task_dir/'task.json').read_text())['title'],'Persisted title')

    def test_stale_revision_cannot_overwrite_another_change(self):
        task,revision=self.store.get_document(self.key,'task.json')
        self.store.put_document(self.key,'task.json',{**task,'title':'first'},revision)
        with self.assertRaisesRegex(ValueError,'Concurrent'):
            self.store.put_document(self.key,'task.json',{**task,'title':'stale'},revision)
        self.assertEqual(self.store.get_document(self.key,'task.json')[0]['title'],'first')

    def test_concurrent_independent_documents_do_not_lose_events(self):
        failures=[]
        def worker(i):
            try:
                store=Store(self.store.path)
                store.audit(self.key,'test','parallel '+str(i))
            except Exception as error: failures.append(error)
        workers=[threading.Thread(target=worker,args=(i,)) for i in range(12)]
        for worker in workers: worker.start()
        for worker in workers: worker.join()
        self.assertEqual(failures,[])
        self.assertEqual(len([e for e in self.store.events(self.key) if e['type']=='test']),12)

    def test_same_task_import_is_idempotent_and_other_database_rejected(self):
        self.assertEqual(self.store.import_task(self.task_dir),self.key)
        with self.assertRaisesRegex(ValueError,'different database'):
            Store(self.root/'other.sqlite3').import_task(self.task_dir)
        self.assertEqual(len(self.store.list_tasks()),1)

    def test_missing_sqlite_record_never_falls_back_to_stale_export(self):
        with self.store.connect() as db:
            db.execute('DELETE FROM documents WHERE task_key=? AND name=?',(self.key,'phases/P1.json'))
        with self.assertRaises(FileNotFoundError): lifecycle.read_json(self.task_dir/'phases/P1.json')

    def test_lifecycle_checkpoint_records_failure_in_database(self):
        with contextlib.redirect_stdout(io.StringIO()):
            result=lifecycle.command_checkpoint(argparse.Namespace(task_dir=str(self.task_dir),gate='design',phase='P1'))
        self.assertNotEqual(result,0)
        self.assertTrue(any(e.get('result')=='FAIL' for e in self.store.events(self.key)))

    def test_done_does_not_archive_without_manual_operation(self):
        self.complete()
        self.assertEqual(summary(self.store.detail(self.key))['status'],'done')
        self.assertEqual(self.store.row(self.key)['archive_state'],'active')
        self.assertEqual(summary(self.store.detail(self.key))['stage'],'release')

    def test_resolved_historical_issues_do_not_make_board_blocked(self):
        phase,revision=self.store.get_document(self.key,'phases/P1.json')
        phase['issues']=[{'id':'old','severity':'blocker','status':'resolved-by-user-acceptance'},{'id':'baseline','status':'baseline-confirmed'}]
        self.store.put_document(self.key,'phases/P1.json',phase,revision)
        self.assertEqual(summary(self.store.detail(self.key))['status'],'active')
        phase,revision=self.store.get_document(self.key,'phases/P1.json')
        phase['issues'].append({'id':'new','severity':'blocker','status':'open'})
        self.store.put_document(self.key,'phases/P1.json',phase,revision)
        self.assertEqual(summary(self.store.detail(self.key))['status'],'blocked')

    def test_unfinished_task_archives_without_changing_phase_progress_or_failures(self):
        phase,revision=self.store.get_document(self.key,'phases/P1.json')
        phase.update(state='IMPLEMENTING',workItems=[{'id':'DEV-01','title':'Incomplete','status':'TODO'}],tests=[{'id':'TC-01','status':'FAIL'}])
        self.store.put_document(self.key,'phases/P1.json',phase,revision)
        task_before=self.store.get_document(self.key,'task.json')[0]
        self.assertTrue(lifecycle.validate_task(self.task_dir,'done')[0])
        codex=FakeCodex()
        record=self.store.archive(self.key,codex)
        self.assertTrue(codex.archived)
        self.assertEqual(self.store.get_document(self.key,'task.json')[0],task_before)
        self.assertEqual(self.store.get_document(self.key,'phases/P1.json')[0],phase)
        copied=json.loads((self.store.archive_path(record['archive_id'])/'phases/P1.json').read_text())
        self.assertEqual(copied['state'],'IMPLEMENTING')
        self.assertEqual(copied['tests'][0]['status'],'FAIL')
        self.assertEqual(summary(self.store.detail(self.key))['progress'],0)

    def test_archive_requires_actual_bound_conversation(self):
        self.store.configure(self.key,thread_id='')
        codex=FakeCodex()
        with self.assertRaisesRegex(ValueError,'Bind this task'):
            self.store.archive(self.key,codex)
        self.assertEqual(codex.calls,[])

    def test_archive_saves_deliverables_before_codex_and_is_idempotent(self):
        source=self.task_dir/'deliverables'/'prd.md'
        source.parent.mkdir()
        source.write_text('Approved PRD')
        self.store.add_deliverable(self.key,'P1','product','PRD',source,'v1')
        codex=FakeCodex()
        original=codex.archive
        def archive(identifier):
            record=self.store.detail(self.key)['archive']
            path=self.store.archive_path(record['archive_id'])
            self.assertEqual((path/'deliverables/prd.md').read_text(),'Approved PRD')
            self.assertTrue((path/'manifest.json').is_file())
            original(identifier)
        codex.archive=archive
        record=self.archive(codex)
        self.assertEqual(record['state'],'archived')
        self.assertEqual(dt.datetime.fromisoformat(record['expires_at'])-dt.datetime.fromisoformat(record['archived_at']),dt.timedelta(days=30))
        self.store.archive(self.key,codex)
        self.assertEqual(codex.calls.count('archive'),1)

    def test_timeout_keeps_copy_and_retry_reconciles_without_duplicate_archive(self):
        codex=FakeCodex();codex.fail=True
        with self.assertRaises(TimeoutError): self.archive(codex)
        detail=self.store.detail(self.key)
        self.assertEqual(detail['archive_state'],'uncertain')
        self.assertTrue(self.store.archive_path(detail['archive']['archive_id']).exists())
        codex.archived=True;codex.fail=False
        self.store.archive(self.key,codex)
        self.assertEqual(codex.calls.count('archive'),1)
        self.assertEqual(self.store.row(self.key)['archive_state'],'archived')

    def test_running_conversation_is_not_archived(self):
        codex=FakeCodex();codex.running=True
        with self.assertRaisesRegex(ValueError,'running'): self.archive(codex)
        self.assertNotIn('archive',codex.calls)
        self.assertEqual(self.store.row(self.key)['archive_state'],'failed')

    def test_expiry_deletes_only_owned_copy_and_keeps_original_database_and_codex(self):
        source=self.task_dir/'evidence'/'release.txt';source.write_text('Original release evidence')
        codex=FakeCodex();record=self.archive(codex)
        expires=dt.datetime.fromisoformat(record['expires_at'])
        copy=self.store.archive_path(record['archive_id'])
        self.assertEqual(self.store.cleanup(expires-dt.timedelta(seconds=1)),[])
        self.assertTrue(copy.exists())
        self.assertEqual(self.store.cleanup(expires),[self.key])
        self.assertFalse(copy.exists())
        self.assertEqual(source.read_text(),'Original release evidence')
        self.assertEqual(self.store.get_document(self.key,'task.json')[0]['state'],'DONE')
        self.assertEqual(self.store.row(self.key)['thread_id'],THREAD)
        self.assertTrue(codex.archived)
        self.assertEqual(codex.calls.count('archive'),1)
        self.assertEqual(self.store.cleanup(expires+dt.timedelta(days=2)),[])

    def test_cleanup_refuses_symlink_and_unknown_ownership(self):
        record=self.archive()
        copy=self.store.archive_path(record['archive_id'])
        (copy/'manifest.json').write_text(json.dumps({'taskKey':'wrong','archiveId':record['archive_id']}))
        with self.assertRaisesRegex(ValueError,'unowned'):
            self.store.cleanup(dt.datetime.fromisoformat(record['expires_at']))
        self.assertTrue(copy.exists())

    def test_symlink_snapshot_failure_can_retry_after_fix(self):
        source=self.task_dir/'evidence'/'linked.txt';source.symlink_to(self.root/'outside')
        (self.root/'outside').write_text('outside')
        codex=FakeCodex()
        with self.assertRaisesRegex(ValueError,'symlink'): self.archive(codex)
        self.assertNotIn('archive',codex.calls)
        source.unlink()
        self.store.archive(self.key,codex)
        self.assertTrue(codex.archived)

    def test_archived_task_cannot_be_rebound_or_overwritten(self):
        self.archive()
        task,revision=self.store.get_document(self.key,'task.json')
        with self.assertRaisesRegex(ValueError,'locked'):
            self.store.put_document(self.key,'task.json',task,revision)
        with self.assertRaisesRegex(ValueError,'locked'):
            self.store.configure(self.key,thread_id=THREAD)

    def test_versioned_html_uses_database_and_preserves_earlier_versions(self):
        from workspace_documents import export_document
        phase,revision=self.store.get_document(self.key,'phases/P1.json')
        phase['requirements']=[{'id':'REQ-1','statement':'<script>alert(1)</script>','acceptance':'Exactly one record'}]
        self.store.put_document(self.key,'phases/P1.json',phase,revision)
        result=export_document(self.store,self.key,'P1','product','v0.1')
        path=Path(result['path']);original=path.read_text()
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;',original)
        self.assertNotIn('<script>',original)
        self.assertIn('<table>',original)
        self.assertNotIn('<link rel="stylesheet"',original)
        phase,revision=self.store.get_document(self.key,'phases/P1.json')
        phase['requirements'][0]['statement']='Updated requirement'
        self.store.put_document(self.key,'phases/P1.json',phase,revision)
        with self.assertRaises(FileExistsError):
            export_document(self.store,self.key,'P1','product','v0.1')
        newer=export_document(self.store,self.key,'P1','product','v0.2')
        self.assertEqual(path.read_text(),original)
        self.assertIn('Updated requirement',Path(newer['path']).read_text())
        self.assertEqual(len(self.store.detail(self.key)['deliverables']),2)

    def test_all_html_document_kinds_export_without_changing_approval_or_status(self):
        from workspace_documents import export_document
        before=self.store.get_document(self.key,'phases/P1.json')[0]
        for kind in KINDS:
            result=export_document(self.store,self.key,'P1',kind,'v1')
            self.assertTrue(Path(result['path']).is_file())
        self.assertEqual(self.store.get_document(self.key,'phases/P1.json')[0],before)
        with self.assertRaises(ValueError):
            export_document(self.store,self.key,'P1','product','../../outside')
        with self.assertRaises(ValueError):
            export_document(self.store,self.key,'P99','product','v1')
        (self.task_dir/'task.json').write_text('{"title":"external edits"}')
        with self.assertRaisesRegex(ValueError,'Reconcile'):
            export_document(self.store,self.key,'P1','product','v2')


class WorkspaceHTTPTests(unittest.TestCase):
    complete=WorkspaceTests.complete
    archive=WorkspaceTests.archive
    def setUp(self):
        WorkspaceTests.setUp(self)
        self.codex=FakeCodex()
        self.server=WorkspaceHTTP(('127.0.0.1',0),self.store,lambda:self.codex)
        self.worker=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.worker.start()
        self.base='http://127.0.0.1:'+str(self.server.server_port)
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown();self.server.server_close();self.worker.join(timeout=3)

    def get(self,path):
        with urlopen(self.base+path) as result: return result.read()

    def post(self,path,body,authorized=True):
        headers={'Content-Type':'application/json','Origin':self.base,'X-Lifecycle-Token':self.server.token if authorized else 'wrong'}
        request=Request(self.base+path,data=json.dumps(body).encode(),headers=headers,method='POST')
        with urlopen(request) as response: return json.load(response)

    def test_web_tasks_are_live_and_documents_have_separate_routes(self):
        value=json.loads(self.get('/api/workspace'))
        self.assertEqual(value['tasks'][0]['title'],'SQLite task')
        for kind in KINDS:
            content=self.get('/tasks/'+self.key+'/documents/'+kind)
            self.assertIn(b'<!doctype html>',content)
        with self.assertRaises(HTTPError): self.get('/tasks/'+self.key+'/documents/unknown')

    def test_web_manual_archive_works_before_done_and_requires_origin_token(self):
        with self.assertRaises(HTTPError) as context:
            self.post('/api/tasks/'+self.key+'/archive',{'userRequested':True},False)
        self.assertEqual(context.exception.code,403)
        with self.assertRaises(HTTPError):
            self.post('/api/tasks/'+self.key+'/archive',{'userRequested':False})
        self.assertFalse(self.codex.archived)
        result=self.post('/api/tasks/'+self.key+'/archive',{'userRequested':True})
        self.assertTrue(result['ok'])
        self.assertTrue(self.codex.archived)
        self.assertEqual(self.store.get_document(self.key,'task.json')[0]['state'],'DISCOVERY')

    def test_checklist_persists_without_approving_or_finishing_task(self):
        phase,revision=self.store.get_document(self.key,'phases/P1.json')
        before=phase['state']
        self.post('/api/tasks/'+self.key+'/checklist',{'phaseId':'P1','itemId':'REL-01','checked':True,'expectedRevision':revision})
        phase,new_revision=self.store.get_document(self.key,'phases/P1.json')
        self.assertTrue(phase['releaseChecklist'][0]['checked'])
        self.assertEqual(phase['state'],before)
        self.assertIsNone(phase['approvals']['design'])
        self.assertGreater(new_revision,revision)
        with self.assertRaises(HTTPError):
            self.post('/api/tasks/'+self.key+'/checklist',{'phaseId':'P1','itemId':'REL-01','checked':False,'expectedRevision':revision})

    def test_unregistered_or_traversal_files_are_not_served(self):
        for route in ('/raw/unknown','/raw/../../task.json','/.lifecycle-store.json','/api/tasks/unknown'):
            with self.assertRaises(HTTPError): self.get(route)

    def test_html_deliverables_are_sandboxed_and_expiry_removes_access(self):
        path=self.task_dir/'deliverables'/'ui.html';path.parent.mkdir();path.write_text('<button>prototype</button>')
        identifier=self.store.add_deliverable(self.key,'P1','ui','UI',path,'v1')
        with urlopen(self.base+'/raw/'+identifier) as response:
            self.assertIn('sandbox allow-scripts',response.headers['Content-Security-Policy'])
        self.assertIn(b'sandbox="allow-scripts"',self.get('/deliverables/'+identifier))
        record=self.archive()
        self.store.cleanup(dt.datetime.fromisoformat(record['expires_at']))
        with self.assertRaises(HTTPError): self.get('/deliverables/'+identifier)


if __name__=='__main__': unittest.main()
