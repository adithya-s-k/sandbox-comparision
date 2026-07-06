"""B14 — pool correctness (host mode): does the v1.22 fix actually hold?

Directly re-tests the three things that were broken in the pre-release branch
(Slack: Lucain added a per-process host-spawn lock + eager warm_up):

  A. warm_up=N pre-provisions N hosts BEFORE the first create() returns.
  B. max_hosts=M caps hosts at M even when we over-request sandboxes.
  C. packing: creating `total` sandboxes concurrently lands them on ~ceil(total/sph)
     hosts (not ~1 host/sandbox). Run at low + high concurrency to compare.

Pass/fail per check, so it doubles as a regression guard.
"""
from __future__ import annotations
import argparse
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from _common import write_jsonl, env_check, ROOT
from adapters import HFPoolAdapter
from huggingface_hub import SandboxPool
load_dotenv(ROOT / '.env')
BENCH = 'b14_pool_correctness'


def check_warm_up(n: int, sph: int) -> dict:
    print(f'\n[A warm_up] SandboxPool(warm_up={n}) — expect {n} hosts before any create()…')
    t0 = time.monotonic()
    pool = SandboxPool(image='python:3.12', flavor='cpu-basic', sandboxes_per_host=sph, warm_up=n)
    warm_sec = time.monotonic() - t0
    hosts = pool.num_hosts
    pool.close()
    ok = hosts >= n
    print(f'[A warm_up] hosts_after_init={hosts} (want ≥{n})  warm={warm_sec:.1f}s  -> {"PASS" if ok else "FAIL"}')
    return {'check': 'warm_up', 'requested': n, 'hosts_after_init': hosts, 'warm_sec': warm_sec, 'pass': ok}


def check_max_hosts(cap: int, total: int, sph: int, concurrency: int) -> dict:
    print(f'\n[B max_hosts] max_hosts={cap}, request {total} sandboxes — hosts must stay ≤{cap}…')
    pool = SandboxPool(image='python:3.12', flavor='cpu-basic', sandboxes_per_host=sph, warm_up=1, max_hosts=cap)
    made = []

    def mk(i):
        try:
            made.append(pool.create())
        except Exception:
            pass
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        list(as_completed([ex.submit(mk, i) for i in range(total)]))
    hosts = pool.num_hosts
    pool.close()
    ok = hosts <= cap
    print(f'[B max_hosts] created={len(made)} hosts={hosts} (cap {cap})  -> {"PASS" if ok else "FAIL"}')
    return {'check': 'max_hosts', 'cap': cap, 'requested': total, 'created': len(made), 'hosts': hosts, 'pass': ok}


def check_packing(total: int, sph: int, concurrency: int) -> dict:
    expected = math.ceil(total / sph)
    print(f'\n[C packing] {total} sandboxes @ sph={sph}, concurrency={concurrency} — expect ~{expected} hosts…')
    pool = SandboxPool(image='python:3.12', flavor='cpu-basic', sandboxes_per_host=sph, warm_up=1)
    made = []

    def mk(i):
        try:
            made.append(pool.create())
        except Exception:
            pass
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        list(as_completed([ex.submit(mk, i) for i in range(total)]))
    dt = time.monotonic() - t0
    hosts = pool.num_hosts
    pool.close()
    per_host = len(made) / max(hosts, 1)
    # pass if within 2x of the ideal host count (some slack for boundary/races)
    ok = hosts <= expected * 2
    print(f'[C packing] created={len(made)} hosts={hosts} ({per_host:.1f}/host) in {dt:.1f}s '
          f'(ideal {expected})  -> {"PASS" if ok else "FAIL"}')
    return {'check': 'packing', 'total': total, 'sph': sph, 'concurrency': concurrency, 'created': len(made), 'hosts': hosts, 'expected_hosts': expected, 'per_host': per_host, 'wall_sec': dt, 'pass': ok}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--sph', type=int, default=50)
    ap.add_argument('--warm', type=int, default=3)
    ap.add_argument('--max-hosts', type=int, default=2)
    ap.add_argument('--total', type=int, default=100)
    ap.add_argument('--concurrency', type=int, default=100)
    args = ap.parse_args()
    if not env_check('hf-pool'):
        return
    print(f'[B14] pool correctness  sph={args.sph}')
    results = []
    results.append(check_warm_up(args.warm, args.sph))
    time.sleep(3)
    results.append(check_max_hosts(args.max_hosts, args.total, args.sph, args.concurrency))
    time.sleep(3)
    # packing at low vs high concurrency — the regression that was broken
    results.append(check_packing(args.total, args.sph, concurrency=4))
    time.sleep(3)
    results.append(check_packing(args.total, args.sph, args.concurrency))
    HFPoolAdapter.reset_pool()

    verdict = all(r['pass'] for r in results)
    write_jsonl(BENCH, 'hf-pool', {'summary': {'bench': BENCH, 'provider': 'hf-pool', 'verdict': 'PASS' if verdict else 'FAIL', 'checks': results}})
    print('\n[B14] summary:')
    for r in results:
        print(f"  {'PASS' if r['pass'] else 'FAIL'}  {r['check']}  {r}")
    print(f"\n[verdict] {'PASS' if verdict else 'FAIL'}")


if __name__ == '__main__':
    main()
