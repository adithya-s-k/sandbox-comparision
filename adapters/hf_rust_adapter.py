from __future__ import annotations
import time
from .base import SandboxAdapter

class HFRustAdapter(SandboxAdapter):
    """Sandbox API built into huggingface_hub (PR #4350) — Rust sbx-server on HF Jobs."""
    name = 'hf-rust'
    cost_per_sandbox_sec = 1.39e-05
    cost_notes = 'HF Jobs cpu-basic, est ~$0.05/CPU-hour (same infra as hf)'

    def _do_create(self, *, image: str, **kwargs):
        from huggingface_hub import Sandbox
        self.handle = Sandbox.create(image=image)
        self._created_at = time.monotonic()
        return self.handle

    def _do_exec(self, *, cmd, timeout: float):
        r = self.handle.run(cmd, timeout=timeout, check=False)
        return {'rc': r.exit_code, 'stdout': r.stdout or '', 'stderr': r.stderr or ''}

    def _do_write(self, *, path: str, content):
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
