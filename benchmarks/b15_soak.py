"""B15 — sustained soak / churn (host mode): reliability over time.

Runs create→exec→kill lifecycles at a steady concurrency for `--minutes`, reusing
one pool. Watches for the failure modes that only show up over time:
  · host leaks — pool.num_hosts should plateau, not climb monotonically
  · connection drops / timeouts under sustained load (error taxonomy per minute)
  · idle-timeout eviction of the pool's hosts mid-run

Reports success rate and error kinds bucketed per minute so degradation is visible.
"""
from __future__ import annotations
import argparse
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from _common import write_jsonl, stats, env_check, ROOT
from adapters import HFPoolAdapter
load_dotenv(ROOT / '.env')
BENCH = 'b15_soak'


def one_lifecycle(_i) -> dict:
    a = HFPoolAdapter()
    t0 = time.monotonic()
    c = a.create()
    if not c.ok:
        return {'ok': False, 'stage': 'create', 'error_kind': c.error_kind, 'error_msg': (c.error_msg or '')[:160], 't_ms': (time.monotonic() - t0) * 1000}
    ex = a.exec('echo ok')
    ok = ex.ok and ex.value.get('stdout', '').strip() == 'ok'
    a.terminate()
    return {'ok': ok, 'stage': None if ok else 'exec', 'error_kind': ex.error_kind, 'error_msg': (ex.error_msg or '')[:160] if not ok else None, 't_ms': (time.monotonic() - t0) * 1000}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--minutes', type=float, default=30.0)
    ap.add_argument('--concurrency', type=int, default=20)
    ap.add_argument('--sph', type=int, default=50)
    args = ap.parse_args()
    if not env_check('hf-pool'):
        return
    HFPoolAdapter.configure(sandboxes_per_host=args.sph, warm_up=1)
    print(f'[B15] soak {args.minutes}min  concurrency={args.concurrency}  sph={args.sph}')

    deadline = time.monotonic() + args.minutes * 60
    per_min = defaultdict(lambda: {'ok': 0, 'fail': 0, 'errs': Counter(), 'lat': []})
    host_track = []
    all_results = []
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        inflight = set()
        i = 0
        while time.monotonic() < deadline:
            while len(inflight) < args.concurrency:
                inflight.add(ex.submit(one_lifecycle, i)); i += 1
            done = {f for f in inflight if f.done()}
            for f in done:
                r = f.result()
                minute = int((time.monotonic() - start) // 60)
                b = per_min[minute]
                if r['ok']:
                    b['ok'] += 1; b['lat'].append(r['t_ms'])
                else:
                    b['fail'] += 1; b['errs'][r.get('error_kind')] += 1
                all_results.append(r)
            inflight -= done
            hosts = HFPoolAdapter._pool.num_hosts if HFPoolAdapter._pool else 0
            host_track.append((round(time.monotonic() - start, 1), hosts))
            if not done:
                time.sleep(0.2)

    total_ok = sum(b['ok'] for b in per_min.values())
    total = total_ok + sum(b['fail'] for b in per_min.values())
    peak_hosts = max((h for _, h in host_track), default=0)
    print(f'\n[B15] {total_ok}/{total} ok ({total_ok/max(total,1):.0%})  peak_hosts={peak_hosts}')
    print('  minute │ ok  fail  p50ms  errors')
    minutes = {}
    for m in sorted(per_min):
        b = per_min[m]
        p50 = stats(b['lat']).get('p50', 0)
        minutes[m] = {'ok': b['ok'], 'fail': b['fail'], 'p50_ms': p50, 'errors': dict(b['errs'])}
        print(f"  {m:>6} │ {b['ok']:>3} {b['fail']:>4}  {p50:>5.0f}  {dict(b['errs']) or ''}")
    summary = {'bench': BENCH, 'provider': 'hf-pool', 'minutes': args.minutes, 'concurrency': args.concurrency, 'sph': args.sph, 'total': total, 'ok': total_ok, 'success_rate': total_ok / max(total, 1), 'peak_hosts': peak_hosts, 'host_track': host_track[::max(1, len(host_track) // 60)], 'per_minute': minutes}
    write_jsonl(BENCH, 'hf-pool', {'summary': summary})
    HFPoolAdapter.reset_pool()


if __name__ == '__main__':
    main()
