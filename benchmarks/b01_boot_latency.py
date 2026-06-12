from __future__ import annotations
import argparse
import time
from dotenv import load_dotenv
from _common import write_jsonl, stats, env_check, fresh_adapter, ROOT
load_dotenv(ROOT / '.env')
BENCH = 'b01_boot_latency'

def run_once(provider: str, run_id: int) -> dict:
    a = fresh_adapter(provider)
    t0 = time.monotonic()
    create = a.create()
    t_create = (time.monotonic() - t0) * 1000.0
    if not create.ok:
        return {'run_id': run_id, 'ok': False, 'stage': 'create', 'error_kind': create.error_kind, 'error_msg': create.error_msg, 't_create_ms': t_create}
    t0 = time.monotonic()
    ex = a.exec('echo ready')
    t_first_exec = (time.monotonic() - t0) * 1000.0
    if not ex.ok:
        a.terminate()
        return {'run_id': run_id, 'ok': False, 'stage': 'first_exec', 'error_kind': ex.error_kind, 'error_msg': ex.error_msg, 't_create_ms': t_create, 't_first_exec_ms': t_first_exec}
    cost_est = a.estimated_cost_usd()
    a.terminate()
    return {'run_id': run_id, 'ok': True, 't_create_ms': t_create, 't_first_exec_ms': t_first_exec, 't_total_ms': t_create + t_first_exec, 'cost_usd_est': cost_est}

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--provider', required=True, choices=['e2b', 'hf', 'hf-rust', 'mcp'])
    ap.add_argument('--n', type=int, default=5)
    args = ap.parse_args()
    if not env_check(args.provider):
        return
    rows: list[dict] = []
    for i in range(args.n):
        r = run_once(args.provider, i)
        r.update(bench=BENCH, provider=args.provider)
        write_jsonl(BENCH, args.provider, r)
        rows.append(r)
        tag = 'ok' if r.get('ok') else f"FAIL({r.get('error_kind')})"
        print(f"  [{i + 1}/{args.n}] {tag}  create={r.get('t_create_ms', 0):.0f}ms  first_exec={r.get('t_first_exec_ms', 0):.0f}ms")
    ok = [r for r in rows if r.get('ok')]
    print(f'\n[summary] {args.provider}: {len(ok)}/{args.n} ok')
    print(f"  create_ms:     {stats([r['t_create_ms'] for r in ok])}")
    print(f"  first_exec_ms: {stats([r['t_first_exec_ms'] for r in ok])}")
    print(f"  total_ms:      {stats([r['t_total_ms'] for r in ok])}")
if __name__ == '__main__':
    main()
