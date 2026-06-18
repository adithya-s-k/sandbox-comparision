from __future__ import annotations
import atexit
import os
import threading
import time
from .base import SandboxAdapter

# Per-host billing rate (HF Jobs cpu-basic) — same machine class as `hf-rust`,
# but in pool mode one host is shared by `sandboxes_per_host` sandboxes, so the
# effective per-sandbox cost is the host rate amortised across the packing density.
HOST_RATE_PER_SEC = 1.39e-05


class HFPoolAdapter(SandboxAdapter):
    """SandboxPool host mode (PR #4350): 1 Job == 1 host == N sandboxes (uid + Landlock).

    All adapter instances in a process share ONE class-level pool, so concurrent
    benchmarks pack many sandboxes onto a few hosts rather than spinning a Job each.
    """
    name = 'hf-pool'
    cost_per_sandbox_sec = HOST_RATE_PER_SEC  # see estimated_cost_usd for amortised value
    cost_notes = 'HF Jobs cpu-basic host, amortised across sandboxes_per_host'

    # Shared pool + config (mutate via configure()/reset_pool() before first create).
    _pool = None
    _lock = threading.Lock()
    _cfg: dict = {
        'image': os.getenv('HF_POOL_IMAGE', 'python:3.12'),
        'flavor': os.getenv('HF_POOL_FLAVOR', 'cpu-basic'),
        'sandboxes_per_host': int(os.getenv('HF_POOL_SANDBOXES_PER_HOST', '50')),
        'warm_up': int(os.getenv('HF_POOL_WARM_UP', '1')),
    }

    @classmethod
    def configure(cls, **kwargs) -> None:
        """Override pool params (e.g. sandboxes_per_host). Closes any existing pool."""
        cls.reset_pool()
        cls._cfg.update({k: v for k, v in kwargs.items() if v is not None})

    @classmethod
    def reset_pool(cls) -> None:
        with cls._lock:
            if cls._pool is not None:
                try:
                    cls._pool.close()
                except Exception:
                    pass
                cls._pool = None

    @classmethod
    def _ensure_pool(cls):
        if cls._pool is None:
            with cls._lock:
                if cls._pool is None:
                    from huggingface_hub import SandboxPool
                    cls._pool = SandboxPool(
                        image=cls._cfg['image'],
                        flavor=cls._cfg['flavor'],
                        sandboxes_per_host=cls._cfg['sandboxes_per_host'],
                        warm_up=cls._cfg['warm_up'],
                    )
        return cls._pool

    def _do_create(self, *, image: str, **kwargs):
        pool = self._ensure_pool()
        self.handle = pool.create()
        self._created_at = time.monotonic()
        return self.handle

    def _do_exec(self, *, cmd, timeout: float):
        r = self.handle.run(cmd, timeout=timeout, check=False)
        return {'rc': r.exit_code, 'stdout': r.stdout or '', 'stderr': r.stderr or ''}

    def _do_write(self, *, path: str, content):
        self.handle.files.write(path, content)
        return None

    def _do_read(self, *, path: str):
        return self.handle.files.read_text(path)

    def _do_terminate(self):
        try:
            self.handle.kill()
        except Exception:
            pass
        return None

    def estimated_cost_usd(self) -> float:
        # Amortise the host-second cost across the packing density.
        per_host = self._cfg['sandboxes_per_host'] or 1
        return self.alive_seconds() * HOST_RATE_PER_SEC / per_host


@atexit.register
def _close_shared_pool() -> None:
    HFPoolAdapter.reset_pool()
