from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters import ADAPTERS, SandboxAdapter
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'results' / 'raw'
RAW.mkdir(parents=True, exist_ok=True)

def write_jsonl(bench: str, provider: str, row: dict[str, Any]) -> None:
    p = RAW / f'{bench}__{provider}.jsonl'
    row.setdefault('ts', time.time())
    with open(p, 'a') as f:
        f.write(json.dumps(row, default=str) + '\n')

def pct(arr: list[float], p: float) -> float:
    if not arr:
        return float('nan')
    s = sorted(arr)
    k = int(round(p / 100 * (len(s) - 1)))
    return s[max(0, min(k, len(s) - 1))]

def stats(arr: list[float]) -> dict:
    if not arr:
        return {'n': 0}
    return {'n': len(arr), 'min': min(arr), 'p50': pct(arr, 50), 'p90': pct(arr, 90), 'p99': pct(arr, 99), 'max': max(arr), 'mean': sum(arr) / len(arr)}

def env_check(provider: str) -> bool:
    if provider == 'e2b' and (not os.getenv('E2B_API_KEY')):
        print(f'[skip] E2B_API_KEY missing')
        return False
    if provider in ('hf', 'hf-rust', 'hf-pool') and (not os.getenv('HF_TOKEN')):
        print(f'[skip] HF_TOKEN missing')
        return False
    return True

def fresh_adapter(provider: str) -> SandboxAdapter:
    return ADAPTERS[provider]()
