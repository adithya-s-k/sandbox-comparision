from __future__ import annotations
import time
from .base import SandboxAdapter

class HFAdapter(SandboxAdapter):
    name = 'hf'
    cost_per_sandbox_sec = 1.39e-05
    cost_notes = 'HF Jobs cpu-basic, est ~$0.05/CPU-hour (assumed parity with E2B)'

    def _do_create(self, *, image: str, **kwargs):
        from hf_sandbox import Sandbox
        self.handle = Sandbox.create(image=image)
        self._created_at = time.monotonic()
        return self.handle

    def _do_exec(self, *, cmd, timeout: float):
        if isinstance(cmd, list):
            args = cmd
        else:
            args = ['sh', '-c', cmd]
        r = self.handle.exec(*args)
        return {'rc': getattr(r, 'returncode', getattr(r, 'exit_code', 0)), 'stdout': getattr(r, 'stdout', '') or '', 'stderr': getattr(r, 'stderr', '') or ''}

    def _do_write(self, *, path: str, content):
        if isinstance(content, bytes):
            content = content.decode('utf-8', errors='replace')
        self.handle.write_file(path, content)
        return None

    def _do_read(self, *, path: str):
        return self.handle.read_file(path)

    def _do_terminate(self):
        try:
            self.handle.terminate()
        except Exception:
            pass
        return None
