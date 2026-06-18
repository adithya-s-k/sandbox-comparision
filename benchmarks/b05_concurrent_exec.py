from __future__ import annotations
import argparse
import threading
import time
from collections import Counter
from dotenv import load_dotenv
from _common import write_jsonl, stats, env_check, fresh_adapter, ROOT
load_dotenv(ROOT / '.env')
BENCH = 'b05_concurrent_exec'

def worker(provider: str, idx: int, ops: int, out: list) -> None:
    a = fresh_adapter(provider)
    c = a.create()
    if not c.ok:
        out.append({'idx': idx, 'ok': False, 'stage': 'create', 'error_kind': c.error_kind, 't_create_ms': c.elapsed_ms})
        return
    lats = []
    errs = 0
    for j in range(ops):
        r = a.exec('echo x')
        if r.ok:
            lats.append(r.elapsed_ms)
        else:
            errs += 1
    a.terminate()
    out.append({'idx': idx, 'ok': True, 'ops_attempted': ops, 'ops_ok': len(lats), 'ops_err': errs, 't_create_ms': c.elapsed_ms, 'exec_ms': stats(lats), 'cost_usd_est': a.estimated_cost_usd()})

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--provider', required=True, choices=['e2b', 'hf', 'hf-rust', 'hf-pool', 'mcp'])
    ap.add_argument('--n', type=int, default=10, help='parallel sandboxes')
    ap.add_argument('--ops', type=int, default=20, help='sequential exec ops per sandbox')
    args = ap.parse_args()
    if not env_check(args.provider):
        return
    print(f'[start] N={args.n} sandboxes × {args.ops} ops each  provider={args.provider}')
    results: list[dict] = []
    threads = [threading.Thread(target=worker, args=(args.provider, i, args.ops, results), daemon=True) for i in range(args.n)]
    t0 = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = time.monotonic() - t0
    ok = [r for r in results if r.get('ok')]
    all_lats = [v for r in ok for v in r['exec_ms'].get('_values', [])]
    p50s = [r['exec_ms']['p50'] for r in ok if r['exec_ms']['n']]
    p99s = [r['exec_ms']['p99'] for r in ok if r['exec_ms']['n']]
    err_kinds = Counter((r.get('error_kind') for r in results if not r.get('ok')))
    summary = {'bench': BENCH, 'provider': args.provider, 'n_sandboxes': args.n, 'ops_per_sandbox': args.ops, 'wall_sec': wall, 'sandboxes_ok': len(ok), 'success_rate': len(ok) / args.n, 'ops_total_ok': sum((r['ops_ok'] for r in ok)), 'ops_total_err': sum((r['ops_err'] for r in ok)) + sum((1 for r in results if not r.get('ok'))), 'across_workers_p50_of_p50': sorted(p50s)[len(p50s) // 2] if p50s else 0, 'across_workers_p99_of_p99': sorted(p99s)[len(p99s) - 1] if p99s else 0, 'error_kinds': dict(err_kinds), 'total_cost_usd_est': sum((r.get('cost_usd_est', 0.0) for r in results))}
    write_jsonl(BENCH, args.provider, {'summary': summary, 'results': results})
    print(f'\n[summary] N={args.n} × {args.ops} ops  ok={len(ok)}/{args.n}  wall={wall:.1f}s')
    print(f"  ops total: {summary['ops_total_ok']} ok / {summary['ops_total_err']} err")
    print(f"  median worker p50: {summary['across_workers_p50_of_p50']:.0f}ms")
    print(f"  worst   worker p99: {summary['across_workers_p99_of_p99']:.0f}ms")
    if err_kinds:
        print(f'  errors: {dict(err_kinds)}')
    print(f"  est_cost: ${summary['total_cost_usd_est']:.4f}")
if __name__ == '__main__':
    main()
