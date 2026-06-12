from __future__ import annotations
import argparse
import threading
import time
from collections import Counter
from dotenv import load_dotenv
from _common import write_jsonl, stats, env_check, fresh_adapter, ROOT
load_dotenv(ROOT / '.env')
BENCH = 'b04_concurrent_create'

def one_lifecycle(provider: str, idx: int, out: list) -> None:
    a = fresh_adapter(provider)
    t0 = time.monotonic()
    c = a.create()
    t_create = (time.monotonic() - t0) * 1000.0
    if not c.ok:
        out.append({'idx': idx, 'ok': False, 'stage': 'create', 'error_kind': c.error_kind, 'error_msg': c.error_msg, 't_create_ms': t_create})
        return
    t0 = time.monotonic()
    ex = a.exec('echo ready')
    t_exec = (time.monotonic() - t0) * 1000.0
    a.terminate()
    out.append({'idx': idx, 'ok': ex.ok, 'stage': None if ex.ok else 'exec', 'error_kind': ex.error_kind, 'error_msg': ex.error_msg, 't_create_ms': t_create, 't_first_exec_ms': t_exec, 't_ready_ms': t_create + t_exec, 'cost_usd_est': a.estimated_cost_usd()})

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--provider', required=True, choices=['e2b', 'hf', 'hf-rust', 'mcp'])
    ap.add_argument('--n', type=int, default=10)
    args = ap.parse_args()
    if not env_check(args.provider):
        return
    results: list[dict] = []
    threads = [threading.Thread(target=one_lifecycle, args=(args.provider, i, results), daemon=True) for i in range(args.n)]
    print(f'[start] N={args.n} parallel sandboxes  provider={args.provider}')
    t0 = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall_sec = time.monotonic() - t0
    ok = [r for r in results if r.get('ok')]
    fail = [r for r in results if not r.get('ok')]
    err_kinds = Counter((r.get('error_kind') for r in fail))
    summary = {'bench': BENCH, 'provider': args.provider, 'n': args.n, 'wall_sec': wall_sec, 'ok_count': len(ok), 'fail_count': len(fail), 'success_rate': len(ok) / args.n, 't_create_ms': stats([r['t_create_ms'] for r in results if 't_create_ms' in r]), 't_ready_ms': stats([r['t_ready_ms'] for r in ok]), 'error_kinds': dict(err_kinds), 'total_cost_usd_est': sum((r.get('cost_usd_est', 0.0) for r in results))}
    write_jsonl(BENCH, args.provider, {'summary': summary, 'results': results})
    print(f"\n[summary] N={args.n}  ok={len(ok)}/{args.n} ({summary['success_rate']:.0%})  wall={wall_sec:.1f}s")
    print(f"  t_create_ms:  {summary['t_create_ms']}")
    print(f"  t_ready_ms:   {summary['t_ready_ms']}")
    if err_kinds:
        print(f'  errors:       {dict(err_kinds)}')
    print(f"  est_cost:     ${summary['total_cost_usd_est']:.4f}")
if __name__ == '__main__':
    main()
