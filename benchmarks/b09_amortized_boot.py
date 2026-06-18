"""B09 — amortised boot (pool/host mode only).

The headline property of pool mode: the FIRST sandbox pays the host cold start,
every subsequent sandbox on that warm host is near-instant. We create N sandboxes
sequentially on one pool and split create+first-exec time into first vs warm.
"""
from __future__ import annotations
import argparse
import time
from dotenv import load_dotenv
from _common import write_jsonl, stats, env_check, ROOT
from adapters import HFPoolAdapter
load_dotenv(ROOT / '.env')
BENCH = 'b09_amortized_boot'


def run_density(density: int, n: int) -> dict:
    HFPoolAdapter.configure(sandboxes_per_host=density, warm_up=1)
    held: list = []
    rows: list[dict] = []
    print(f'\n[density={density}] creating {n} sandboxes sequentially on one warm host…')
    for i in range(n):
        a = HFPoolAdapter()
        t0 = time.monotonic()
        c = a.create()
        t_create = (time.monotonic() - t0) * 1000.0
        if not c.ok:
            rows.append({'idx': i, 'ok': False, 'error_kind': c.error_kind, 'error_msg': c.error_msg, 't_create_ms': t_create})
            continue
        t0 = time.monotonic()
        ex = a.exec('echo ready')
        t_exec = (time.monotonic() - t0) * 1000.0
        held.append(a)
        rows.append({'idx': i, 'ok': ex.ok, 't_create_ms': t_create, 't_first_exec_ms': t_exec, 't_ready_ms': t_create + t_exec, 'host_id': getattr(a.handle, 'host_id', None)})
        if i < 3 or (i + 1) % 10 == 0:
            print(f'  [{i + 1}/{n}] ready={t_create + t_exec:.0f}ms (create={t_create:.0f} exec={t_exec:.0f})')
    n_hosts = HFPoolAdapter._pool.num_hosts if HFPoolAdapter._pool else None
    for a in held:
        a.terminate()
    HFPoolAdapter.reset_pool()
    ok = [r for r in rows if r.get('ok')]
    first = ok[0]['t_ready_ms'] if ok else float('nan')
    warm = [r['t_ready_ms'] for r in ok[1:]]
    summary = {'bench': BENCH, 'provider': 'hf-pool', 'density': density, 'n': n, 'ok': len(ok), 'num_hosts': n_hosts, 'first_ready_ms': first, 'warm_ready_ms': stats(warm), 'speedup_first_over_warm': (first / (stats(warm)['p50'] or 1)) if warm else None}
    write_jsonl(BENCH, 'hf-pool', {'summary': summary, 'results': rows})
    w = summary['warm_ready_ms']
    print(f"[density={density}] first={first:.0f}ms  warm p50={w.get('p50', 0):.0f}ms p90={w.get('p90', 0):.0f}ms  hosts={n_hosts}  speedup≈{summary['speedup_first_over_warm']:.0f}×" if warm else f'[density={density}] first={first:.0f}ms (no warm samples)')
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--densities', default='10,25,50', help='comma-separated sandboxes_per_host to sweep')
    ap.add_argument('--n', type=int, default=20, help='sandboxes to create per density')
    args = ap.parse_args()
    if not env_check('hf-pool'):
        return
    densities = [int(x) for x in args.densities.split(',') if x.strip()]
    print(f'[B09] amortised boot  densities={densities}  n={args.n}')
    for d in densities:
        run_density(d, min(args.n, d))
        time.sleep(5)


if __name__ == '__main__':
    main()
