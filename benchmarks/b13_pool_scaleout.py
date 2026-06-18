"""B13 — pooled scale-out (host mode only).

Reproduce the upstream claim: "1000 sandboxes created, exec'd and killed in ~16s
across 20 hosts" (sandboxes_per_host=50). We fan out `--total` create→exec→kill
lifecycles through one shared SandboxPool at a bounded `--concurrency`, and report
wall time, success rate, host fan-out, and amortised cost.

Includes a health probe (small burst) first so we don't dump 1000 requests onto a
paused backend.
"""
from __future__ import annotations
import argparse
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from _common import write_jsonl, stats, env_check, ROOT
from adapters import HFPoolAdapter
load_dotenv(ROOT / '.env')
BENCH = 'b13_pool_scaleout'


def one_lifecycle(idx: int) -> dict:
    a = HFPoolAdapter()
    t0 = time.monotonic()
    c = a.create()
    t_create = (time.monotonic() - t0) * 1000.0
    if not c.ok:
        return {'idx': idx, 'ok': False, 'stage': 'create', 'error_kind': c.error_kind, 'error_msg': (c.error_msg or '')[:200], 't_create_ms': t_create}
    ex = a.exec('echo hi')
    healthy = ex.ok and ex.value.get('stdout', '').strip() == 'hi'
    host = getattr(a.handle, 'host_id', None)
    a.terminate()
    return {'idx': idx, 'ok': healthy, 'stage': None if healthy else 'exec', 'error_kind': ex.error_kind, 'error_msg': (ex.error_msg or '')[:200] if not healthy else None, 't_create_ms': t_create, 'host_id': host}


def run_hold(total: int, concurrency: int, max_hosts: int, label: str) -> dict:
    """Upstream methodology: create ALL sandboxes (hold them, packing 50/host),
    then exec 'hello' on each, then kill all. Measure each phase + total."""
    print(f'\n[{label}] create→hold {total} (max_hosts={max_hosts}), then exec, then kill…')
    held: list = []
    held_lock = threading.Lock()
    create_errs: list = []

    def mk(i):
        a = HFPoolAdapter()
        c = a.create()
        if c.ok:
            with held_lock:
                held.append(a)
        else:
            with held_lock:
                create_errs.append({'error_kind': c.error_kind, 'error_msg': (c.error_msg or '')[:200]})

    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        list(as_completed([ex.submit(mk, i) for i in range(total)]))
    t_create = time.monotonic() - t0
    print(f'[{label}] created {len(held)}/{total} in {t_create:.1f}s')

    t0 = time.monotonic()
    exec_ok = 0
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        for r in as_completed([ex.submit(lambda a: a.exec('echo hello'), a) for a in held]):
            v = r.result()
            if v.ok and v.value.get('stdout', '').strip() == 'hello':
                exec_ok += 1
    t_exec = time.monotonic() - t0

    pool_hosts = HFPoolAdapter._pool.num_hosts if HFPoolAdapter._pool else None
    pool_sbx = HFPoolAdapter._pool.num_sandboxes if HFPoolAdapter._pool else None

    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        list(as_completed([ex.submit(lambda a: a.terminate(), a) for a in held]))
    t_kill = time.monotonic() - t0

    total_wall = t_create + t_exec + t_kill
    err_kinds = Counter(e['error_kind'] for e in create_errs)
    summary = {'bench': BENCH, 'provider': 'hf-pool', 'label': label, 'mode': 'hold', 'total': total, 'concurrency': concurrency, 'max_hosts': max_hosts, 'created': len(held), 'exec_ok': exec_ok, 'success_rate': exec_ok / total, 'wall_total_sec': total_wall, 't_create_sec': t_create, 't_exec_sec': t_exec, 't_kill_sec': t_kill, 'pool_num_hosts': pool_hosts, 'pool_num_sandboxes': pool_sbx, 'error_kinds': dict(err_kinds), 'error_sample': (create_errs[0]['error_msg'] if create_errs else None)}
    write_jsonl(BENCH, 'hf-pool', {'summary': summary})
    print(f'[{label}] created={len(held)}/{total}  exec_ok={exec_ok}  hosts={pool_hosts}  '
          f'TOTAL={total_wall:.1f}s (create {t_create:.1f} + exec {t_exec:.1f} + kill {t_kill:.1f})')
    if err_kinds:
        print(f'[{label}] create errors: {dict(err_kinds)}  sample: {summary["error_sample"]}')
    return summary


def run_burst(total: int, concurrency: int, label: str) -> dict:
    print(f'\n[{label}] firing {total} lifecycles (create→exec→kill) at concurrency={concurrency}…')
    results: list[dict] = []
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futs = [ex.submit(one_lifecycle, i) for i in range(total)]
        for f in as_completed(futs):
            results.append(f.result())
    wall = time.monotonic() - t0
    ok = [r for r in results if r.get('ok')]
    fail = [r for r in results if not r.get('ok')]
    err_kinds = Counter(r.get('error_kind') for r in fail)
    err_sample = next((r.get('error_msg') for r in fail if r.get('error_msg')), None)
    hosts = {r['host_id'] for r in ok if r.get('host_id')}
    pool_hosts = HFPoolAdapter._pool.num_hosts if HFPoolAdapter._pool else None
    summary = {'bench': BENCH, 'provider': 'hf-pool', 'label': label, 'total': total, 'concurrency': concurrency, 'ok': len(ok), 'failed': len(fail), 'success_rate': len(ok) / total, 'wall_sec': wall, 'distinct_hosts': len(hosts), 'pool_num_hosts': pool_hosts, 't_create_ms': stats([r['t_create_ms'] for r in results if 't_create_ms' in r]), 'error_kinds': dict(err_kinds), 'error_sample': err_sample}
    write_jsonl(BENCH, 'hf-pool', {'summary': summary, 'results': results})
    print(f"[{label}] ok={len(ok)}/{total} ({summary['success_rate']:.0%})  wall={wall:.1f}s  hosts={len(hosts)} (pool reports {pool_hosts})")
    if err_kinds:
        print(f'[{label}] errors: {dict(err_kinds)}')
        if err_sample:
            print(f'[{label}]   sample: {err_sample}')
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--total', type=int, default=1000)
    ap.add_argument('--concurrency', type=int, default=200)
    ap.add_argument('--sandboxes-per-host', type=int, default=50)
    ap.add_argument('--probe', type=int, default=25, help='health-probe burst before the big run (0 to skip)')
    ap.add_argument('--hold', action='store_true', help='upstream methodology: create-all → hold → exec → kill (packs 50/host)')
    ap.add_argument('--max-hosts', type=int, default=None, help='cap hosts (e.g. 20 for 1000@50) — hold mode')
    args = ap.parse_args()
    if not env_check('hf-pool'):
        return
    print(f'[B13] pooled scale-out  total={args.total}  concurrency={args.concurrency}  sph={args.sandboxes_per_host}  hold={args.hold}')
    cfg = dict(sandboxes_per_host=args.sandboxes_per_host, warm_up=1)
    if args.max_hosts:
        cfg['max_hosts'] = args.max_hosts
    HFPoolAdapter.configure(**cfg)

    if args.probe:
        probe = run_burst(args.probe, min(args.concurrency, args.probe), label=f'probe N={args.probe}')
        if probe['success_rate'] < 0.9:
            print(f"\n[ABORT] probe only {probe['success_rate']:.0%} healthy — backend looks paused/unhealthy. "
                  f"Not firing the {args.total} run. errors={probe['error_kinds']}")
            HFPoolAdapter.reset_pool()
            return
        print('[probe OK] backend healthy — proceeding to full scale-out.')
        HFPoolAdapter.reset_pool()
        HFPoolAdapter.configure(**cfg)
        time.sleep(3)

    if args.hold:
        run_hold(args.total, args.concurrency, args.max_hosts or 0, label=f'hold N={args.total}')
    else:
        run_burst(args.total, args.concurrency, label=f'scaleout N={args.total}')
    HFPoolAdapter.reset_pool()


if __name__ == '__main__':
    main()
