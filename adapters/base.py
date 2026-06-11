from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any, ClassVar

@dataclass
class OpResult:
    ok: bool
    elapsed_ms: float
    value: Any = None
    error_kind: str | None = None
    error_msg: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

class AdapterError(RuntimeError):
    pass

class SandboxAdapter:
    name: ClassVar[str] = 'base'
    cost_per_sandbox_sec: ClassVar[float] = 0.0
    cost_notes: ClassVar[str] = ''

    def __init__(self) -> None:
        self.handle: Any = None
        self._created_at: float | None = None

    def create(self, image: str='python:3.12-slim', **kwargs) -> OpResult:
        return self._timed(self._do_create, image=image, **kwargs)

    def exec(self, cmd: str | list[str], timeout: float=60.0) -> OpResult:
        return self._timed(self._do_exec, cmd=cmd, timeout=timeout)

    def write(self, path: str, content: str | bytes) -> OpResult:
        return self._timed(self._do_write, path=path, content=content)

    def read(self, path: str) -> OpResult:
        return self._timed(self._do_read, path=path)

    def terminate(self) -> OpResult:
        return self._timed(self._do_terminate)

    def _do_create(self, *, image: str, **kwargs) -> Any:
        raise NotImplementedError

    def _do_exec(self, *, cmd, timeout: float) -> dict:
        raise NotImplementedError

    def _do_write(self, *, path: str, content) -> None:
        raise NotImplementedError

    def _do_read(self, *, path: str) -> str:
        raise NotImplementedError

    def _do_terminate(self) -> None:
        raise NotImplementedError

    def _timed(self, fn, **kwargs) -> OpResult:
        t0 = time.monotonic()
        try:
            value = fn(**kwargs)
            return OpResult(ok=True, elapsed_ms=(time.monotonic() - t0) * 1000.0, value=value, extra={'sandbox_id': getattr(self.handle, 'sandbox_id', None)})
        except Exception as e:
            return OpResult(ok=False, elapsed_ms=(time.monotonic() - t0) * 1000.0, error_kind=self._classify(e), error_msg=f'{type(e).__name__}: {e}')

    @staticmethod
    def _classify(e: Exception) -> str:
        msg = str(e).lower()
        if 'timeout' in msg or 'timed out' in msg:
            return 'timeout'
        if '401' in msg or 'unauth' in msg or 'auth' in msg:
            return 'auth'
        if '429' in msg or 'rate' in msg or 'quota' in msg or ('limit' in msg):
            return 'quota'
        if 'tunnel' in msg or 'cloudflare' in msg:
            return 'tunnel'
        if 'sandbox' in msg and ('dead' in msg or 'removed' in msg or 'killed' in msg):
            return 'sandbox_died'
        return 'other'

    def alive_seconds(self) -> float:
        return time.monotonic() - self._created_at if self._created_at else 0.0

    def estimated_cost_usd(self) -> float:
        return self.alive_seconds() * self.cost_per_sandbox_sec
