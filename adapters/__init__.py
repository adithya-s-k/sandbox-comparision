from .base import SandboxAdapter, AdapterError, OpResult
from .e2b_adapter import E2BAdapter
from .hf_adapter import HFAdapter
from .hf_rust_adapter import HFRustAdapter
from .hf_pool_adapter import HFPoolAdapter
from .mcp_adapter import MCPAdapter
ADAPTERS: dict[str, type[SandboxAdapter]] = {'e2b': E2BAdapter, 'hf': HFAdapter, 'hf-rust': HFRustAdapter, 'hf-pool': HFPoolAdapter, 'mcp': MCPAdapter}
__all__ = ['SandboxAdapter', 'AdapterError', 'OpResult', 'E2BAdapter', 'HFAdapter', 'HFRustAdapter', 'HFPoolAdapter', 'MCPAdapter', 'ADAPTERS']
