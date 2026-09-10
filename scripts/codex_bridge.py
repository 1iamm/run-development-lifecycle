"""Small local app-server client. Never edits Codex's database or rollout files."""
from __future__ import annotations
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time


class CodexBridge:
    def __init__(self, command=None, timeout=30):
        executable = os.environ.get('LIFECYCLE_CODEX_BIN') or shutil.which('codex')
        if not executable:
            bundled = Path('/Applications/ChatGPT.app/Contents/Resources/codex')
            executable = str(bundled) if bundled.is_file() else None
        if not executable and command is None:
            raise ValueError('Codex CLI was not found; set LIFECYCLE_CODEX_BIN')
        self.command = command or [executable,'app-server','--stdio']
        self.timeout = timeout
        self.process = None
        self.messages = queue.Queue()
        self.counter = 0

    def __enter__(self):
        self.process = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, encoding='utf-8', bufsize=1)
        def read():
            try:
                for line in self.process.stdout:
                    try:
                        self.messages.put(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            finally:
                self.messages.put(None)
        self.reader = threading.Thread(target=read,daemon=True)
        self.reader.start()
        try:
            self.call('initialize',{'clientInfo':{'name':'lifecycle_workspace','title':'Lifecycle Workspace','version':'3.0.0'}})
            self._send({'method':'initialized','params':{}})
        except BaseException:
            self.__exit__(None,None,None)
            raise
        return self

    def _send(self, message):
        self.process.stdin.write(json.dumps(message)+'\n')
        self.process.stdin.flush()

    def call(self, method, params):
        if method not in {'initialize','thread/read','thread/list','thread/archive'}:
            raise ValueError('Unsupported Codex operation')
        self.counter += 1
        request_id = self.counter
        self._send({'id':request_id,'method':method,'params':params})
        deadline = time.monotonic()+self.timeout
        while True:
            try:
                message = self.messages.get(timeout=max(.01,deadline-time.monotonic()))
            except queue.Empty:
                raise TimeoutError('Codex operation timed out; archive outcome may require reconciliation')
            if message is None:
                raise ConnectionError('Codex app-server disconnected')
            if message.get('id') == request_id and 'method' not in message:
                if 'error' in message:
                    raise ValueError(str(message['error'].get('message','Codex request failed')))
                return message.get('result',{})
            if 'method' in message and 'id' in message:
                # This client never starts turns, runs commands or answers permission prompts.
                self._send({'id':message['id'],'error':{'code':-32601,'message':'Unsupported by lifecycle workspace'}})
            if time.monotonic() >= deadline:
                raise TimeoutError('Codex operation timed out')

    def read(self, thread_id):
        thread = self.call('thread/read',{'threadId':thread_id,'includeTurns':False})['thread']
        if thread.get('id') != thread_id:
            raise ValueError('Codex returned a different conversation')
        return thread

    def is_archived(self, thread_id):
        cursor = None
        seen = set()
        while True:
            params = {'archived':True,'limit':100,'useStateDbOnly':True}
            if cursor:
                params['cursor'] = cursor
            result = self.call('thread/list',params)
            if any(t.get('id')==thread_id for t in result.get('data',[])):
                return True
            cursor = result.get('nextCursor')
            if not cursor:
                return False
            if cursor in seen:
                raise ValueError('Codex returned a repeated pagination cursor')
            seen.add(cursor)

    def archive(self, thread_id):
        self.call('thread/archive',{'threadId':thread_id})

    def __exit__(self, *args):
        if self.process:
            if self.process.stdin:
                self.process.stdin.close()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            if self.process.stdout:
                self.process.stdout.close()
