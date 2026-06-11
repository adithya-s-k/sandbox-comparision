from __future__ import annotations
import time
from .base import SandboxAdapter

class E2BAdapter(SandboxAdapter):
    name = 'e2b'
    cost_per_sandbox_sec = 1.4e-05
    cost_notes = 'e2b.dev/pricing — 1 vCPU 512 MiB cpu-basic tier, per-second'

    def _do_create(self, *, image: str, **kwargs):
        from e2b import Sandbox
        self.handle = Sandbox.create(timeout=600)
        self._created_at = time.monotonic()
        return self.handle

    def _do_exec(self, *, cmd, timeout: float):
        if isinstance(cmd, list):
            cmd_str = ' '.join(cmd)
        else:
            cmd_str = cmd
        r = self.handle.commands.run(cmd_str, timeout=int(timeout))
        return {'rc': r.exit_code, 'stdout': r.stdout or '', 'stderr': r.stderr or ''}

    def _do_write(self, *, path: str, content):
        if isinstance(content, bytes):
            self.handle.files.write(path, content)
        else:
            self.handle.files.write(path, content)
        return None

    def _do_read(self, *, path: str):
        return self.handle.files.read(path)

    def _do_terminate(self):
        try:
            self.handle.kill()
        except Exception:
            pass
        return None
