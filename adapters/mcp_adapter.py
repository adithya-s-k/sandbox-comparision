from __future__ import annotations
import asyncio
import base64
import json
import os
import shlex
import threading
import time
from .base import SandboxAdapter
_ENDPOINT = os.getenv('MCP_ENDPOINT', '')
_TOOL = 'remote_code_execution'

def _headers() -> dict[str, str]:
    tok = os.getenv('HF_TOKEN') or ''
    return {'Authorization': f'Bearer {tok}'}

class MCPAdapter(SandboxAdapter):
    name = 'mcp'
    cost_per_sandbox_sec = 0.0
    cost_notes = 'HF Inference Endpoint — billed by endpoint uptime (instance·hr), not per-session'

    def _do_create(self, *, image: str='python', **kwargs):
        self._loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._init_err: Exception | None = None
        self._session = None
        self._session_id = None
        self._closed = None
        self._thr = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thr.start()
        self._owner_fut = asyncio.run_coroutine_threadsafe(self._owner(), self._loop)
        if not self._ready.wait(timeout=120):
            raise TimeoutError('MCP session did not initialize within 120s')
        if self._init_err is not None:
            raise self._init_err
        self.handle = self._session_id or 'mcp-session'
        self._created_at = time.monotonic()
        return self.handle

    async def _owner(self) -> None:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
        self._closed = asyncio.Event()
        try:
            async with streamablehttp_client(_ENDPOINT, headers=_headers()) as (r, w, get_sid):
                async with ClientSession(r, w) as s:
                    await s.initialize()
                    self._session = s
                    try:
                        self._session_id = get_sid()
                    except Exception:
                        self._session_id = None
                    self._ready.set()
                    await self._closed.wait()
        except Exception as e:
            self._init_err = e
            self._ready.set()

    def _do_terminate(self):
        try:
            if self._closed is not None:
                self._loop.call_soon_threadsafe(self._closed.set)
                self._owner_fut.result(timeout=30)
        except Exception:
            pass
        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
        except Exception:
            pass
        return None

    def _run(self, coro, timeout: float=120.0):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    def _exec_code(self, code: str, runtime: str='python', timeout: float=120.0) -> dict:
        res = self._run(self._session.call_tool(_TOOL, {'runtime': runtime, 'code': code}), timeout=timeout)
        txt = ''.join((getattr(c, 'text', '') for c in res.content))
        try:
            j = json.loads(txt)
            if isinstance(j, dict) and 'exit_code' in j:
                return {'rc': j.get('exit_code', 0), 'stdout': j.get('stdout', '') or '', 'stderr': j.get('stderr', '') or ''}
        except (json.JSONDecodeError, TypeError):
            pass
        return {'rc': 0, 'stdout': txt, 'stderr': ''}

    def _do_exec(self, *, cmd, timeout: float):
        if isinstance(cmd, list):
            cmd_str = ' '.join((shlex.quote(c) for c in cmd))
        else:
            cmd_str = cmd
        code = f'import subprocess,sys\nr=subprocess.run({cmd_str!r},shell=True,capture_output=True,text=True)\nsys.stdout.write(r.stdout);sys.stderr.write(r.stderr);sys.exit(r.returncode)'
        return self._exec_code(code, 'python', timeout=timeout)

    def _do_write(self, *, path: str, content):
        if isinstance(content, str):
            content = content.encode()
        b64 = base64.b64encode(content).decode()
        code = f"import base64\nopen({path!r},'wb').write(base64.b64decode({b64!r}))\nprint('ok')"
        self._exec_code(code, 'python')
        return None

    def _do_read(self, *, path: str):
        code = f"import base64\nprint(base64.b64encode(open({path!r},'rb').read()).decode())"
        r = self._exec_code(code, 'python')
        return base64.b64decode(r['stdout'].strip())
