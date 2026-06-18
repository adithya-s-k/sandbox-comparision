"""B10 — packing density (pool/host mode only).

Fill ONE host to `sandboxes_per_host` and watch how per-sandbox create latency and
warm exec latency move as the host gets denser. Surfaces the point where packing
starts to cost (CPU contention on a shared cpu-basic VM, no cgroups).
"""
from __future__ import annotations
import argparse
import time
from dotenv import load_dotenv
from _common import write_jsonl, stats, env_check, ROOT
from adapters import HFPoolAdapter
load_dotenv(ROOT / '.env')
BENCH = 'b10_packing_density'


def fill_host(density: int) -> dict:
    # max_hosts=1 forces everything onto a single host so we measure packing, not fan-out.
    HFPoolAdapter.configure(sandboxes_per_host=density, warm_up=1, max_hosts=1)
    held: list = []
    create_lat: list[float] = []
    failed = 0
    print(f'\n[density={density}] filling one host to {density} sandboxes…')
    for i in range(density):
        a = HFPoolAdapter()
        c = a.create()
        if not c.ok:
            failed += 1
            continue
        # skip the cold first create so create_lat reflects warm packing cost
        if i > 0:
            create_lat.append(c.elapsed_ms)
        held.append(a)
    # warm exec latency on a full host
    exec_lat: list[float] = []
    if held:
        victim = held[-1]
        for _ in range(20):
            r = victim.exec('echo x')
            if r.ok:
                exec_lat.append(r.elapsed_ms)
    n_hosts = HFPoolAdapter._pool.num_hosts if HFPoolAdapter._pool else None
    n_sbx = HFPoolAdapter._pool.num_sandboxes if HFPoolAdapter._pool else None
    for a in held:
        a.terminate()
    HFPoolAdapter.reset_pool()
    summary = {'bench': BENCH, 'provider': 'hf-pool', 'density': density, 'filled': len(held), 'failed': failed, 'num_hosts': n_hosts, 'num_sandboxes': n_sbx, 'warm_create_ms': stats(create_lat), 'warm_exec_ms': stats(exec_lat)}
    write_jsonl(BENCH, 'hf-pool', {'summary': summary})
    cm, em = summary['warm_create_ms'], summary['warm_exec_ms']
    print(f"[density={density}] filled={len(held)}/{density} hosts={n_hosts}  create p50={cm.get('p50', 0):.0f}ms  exec p50={em.get('p50', 0):.0f}ms p90={em.get('p90', 0):.0f}ms")
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--densities', default='1,10,25,50,100', help='comma-separated sandboxes_per_host')
    args = ap.parse_args()
    if not env_check('hf-pool'):
        return
    densities = [int(x) for x in args.densities.split(',') if x.strip()]
    print(f'[B10] packing density sweep  densities={densities}')
    for d in densities:
        fill_host(d)
        time.sleep(5)


if __name__ == '__main__':
    main()
