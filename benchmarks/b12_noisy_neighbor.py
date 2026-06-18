"""B12 — noisy neighbour (pool/host mode only).

Pool mode has no cgroup CPU isolation, so a co-resident sandbox running hot can
starve its neighbours. We measure a victim sandbox's exec throughput on an idle
host, then again while N CPU-bound hogs run in sibling sandboxes on the same host.
Reports the throughput degradation.
"""
from __future__ import annotations
import argparse
import time
from dotenv import load_dotenv
from _common import write_jsonl, stats, env_check, ROOT
from adapters import HFPoolAdapter
load_dotenv(ROOT / '.env')
BENCH = 'b12_noisy_neighbor'

# CPU-bound busy loop; runs until the sandbox is killed.
HOG = "python3 -c \"\nwhile True:\n    pass\n\""


def measure(victim, ops: int) -> list[float]:
    lats = []
    for _ in range(ops):
        # a small CPU task so contention actually shows up (not just a round-trip)
        r = victim.exec("python3 -c 'sum(i*i for i in range(200000))'")
        if r.ok:
            lats.append(r.elapsed_ms)
    return lats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--hogs', type=int, default=3, help='co-resident CPU-bound sandboxes')
    ap.add_argument('--ops', type=int, default=30, help='victim exec ops per phase')
    args = ap.parse_args()
    if not env_check('hf-pool'):
        return
    HFPoolAdapter.configure(sandboxes_per_host=args.hogs + 2, warm_up=1, max_hosts=1)

    victim = HFPoolAdapter()
    if not victim.create().ok:
        print('[abort] victim create failed'); HFPoolAdapter.reset_pool(); return
    _, cores = (victim.exec('nproc').value.get('rc'), victim.exec('nproc').value.get('stdout', '').strip())

    print(f'\n[B12] host cores={cores}  hogs={args.hogs}  ops={args.ops}')
    print('[phase 1] measuring victim on IDLE host…')
    idle = measure(victim, args.ops)

    hogs = []
    for i in range(args.hogs):
        h = HFPoolAdapter()
        if h.create().ok:
            h.handle.spawn(HOG, tag=f'hog{i}')
            hogs.append(h)
    same_host = all(getattr(h.handle, 'host_id', None) == getattr(victim.handle, 'host_id', None) for h in hogs)
    print(f'[phase 2] {len(hogs)} hogs spawned (same_host={same_host}); measuring victim under load…')
    time.sleep(2)
    loaded = measure(victim, args.ops)

    for h in hogs:
        h.terminate()
    victim.terminate()
    HFPoolAdapter.reset_pool()

    idle_s, loaded_s = stats(idle), stats(loaded)
    degr = (loaded_s.get('p50', 0) / idle_s['p50'] - 1) * 100 if idle_s.get('p50') else float('nan')
    summary = {'bench': BENCH, 'provider': 'hf-pool', 'cores': cores, 'hogs': len(hogs), 'same_host': same_host, 'ops': args.ops, 'idle_exec_ms': idle_s, 'loaded_exec_ms': loaded_s, 'p50_slowdown_pct': degr}
    write_jsonl(BENCH, 'hf-pool', {'summary': summary})
    print(f"\n[summary] idle p50={idle_s.get('p50', 0):.0f}ms → loaded p50={loaded_s.get('p50', 0):.0f}ms  ({degr:+.0f}% under {len(hogs)} hogs)")


if __name__ == '__main__':
    main()
