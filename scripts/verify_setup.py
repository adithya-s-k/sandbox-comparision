from __future__ import annotations
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters import ADAPTERS

def check_one(name: str) -> bool:
    print(f'\n── {name} ──')
    if name == 'e2b' and (not os.getenv('E2B_API_KEY')):
        print(f'  [skip] E2B_API_KEY not set')
        return False
    if name in ('hf', 'hf-rust', 'hf-pool') and (not os.getenv('HF_TOKEN')):
        print(f'  [skip] HF_TOKEN not set')
        return False
    a = ADAPTERS[name]()
    r = a.create()
    print(f"  create:    {('ok' if r.ok else 'FAIL')}  {r.elapsed_ms:.0f}ms{(f'  ({r.error_kind}: {r.error_msg})' if not r.ok else '')}")
    if not r.ok:
        return False
    r = a.exec('echo hello')
    print(f"  exec:      {('ok' if r.ok else 'FAIL')}  {r.elapsed_ms:.0f}ms  stdout={r.value['stdout'].strip()!r}" if r.ok else f'  FAIL  {r.error_kind}')
    exec_ok = r.ok and r.value['stdout'].strip() == 'hello'
    r = a.write('/tmp/probe.txt', 'world')
    print(f"  write:     {('ok' if r.ok else 'FAIL')}  {r.elapsed_ms:.0f}ms")
    r = a.read('/tmp/probe.txt')
    rd_ok = r.ok and (r.value.strip() if isinstance(r.value, str) else r.value.decode().strip()) == 'world'
    print(f"  read:      {('ok' if rd_ok else 'FAIL')}  {r.elapsed_ms:.0f}ms  content={r.value!r}")
    r = a.terminate()
    print(f"  terminate: {('ok' if r.ok else 'FAIL')}  {r.elapsed_ms:.0f}ms")
    verdict = exec_ok and rd_ok
    print(f"  verdict: {('PASS' if verdict else 'FAIL')}")
    return verdict
if __name__ == '__main__':
    results = {n: check_one(n) for n in ADAPTERS}
    print('\n' + '=' * 60)
    print('summary:', ' · '.join((f"{n}={('PASS' if v else 'FAIL')}" for n, v in results.items())))
    sys.exit(0 if all(results.values()) else 1)
