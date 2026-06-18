from __future__ import annotations
import argparse
import time
from dotenv import load_dotenv
from _common import write_jsonl, env_check, fresh_adapter, ROOT
load_dotenv(ROOT / '.env')
BENCH = 'b06_long_running'

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--provider', required=True, choices=['e2b', 'hf', 'hf-rust', 'hf-pool', 'mcp'])
    ap.add_argument('--minutes', type=float, default=5.0)
    ap.add_argument('--interval', type=float, default=20.0, help='seconds between pings')
    args = ap.parse_args()
    if not env_check(args.provider):
        return
    a = fresh_adapter(args.provider)
    c = a.create()
    if not c.ok:
        print(f'[abort] create failed: {c.error_kind}: {c.error_msg}')
        return
    print(f'[start] sandbox up; pinging every {args.interval}s for {args.minutes:.1f} min')
    deadline = time.monotonic() + args.minutes * 60
    pings = []
    ping_idx = 0
    while time.monotonic() < deadline:
        ping_idx += 1
        t0 = time.monotonic()
        r = a.exec('echo ping')
        ok = r.ok and (r.value.get('stdout', '').strip() if r.ok else '') == 'ping'
        elapsed_alive = time.monotonic() - (a._created_at or time.monotonic())
        pings.append({'idx': ping_idx, 'ok': ok, 'alive_sec': elapsed_alive, 'elapsed_ms': r.elapsed_ms, 'error_kind': r.error_kind, 'error_msg': r.error_msg})
        status = 'OK' if ok else f'FAIL({r.error_kind})'
        print(f'  [{ping_idx:>3}] alive={elapsed_alive:>5.0f}s  ping={r.elapsed_ms:>5.0f}ms  {status}')
        if not ok and r.error_kind in ('sandbox_died', 'tunnel', 'timeout'):
            print('  [early-exit] sandbox/tunnel failure detected')
            break
        time.sleep(args.interval)
    cost_est = a.estimated_cost_usd()
    a.terminate()
    ok_pings = [p for p in pings if p['ok']]
    summary = {'bench': BENCH, 'provider': args.provider, 'minutes': args.minutes, 'interval_sec': args.interval, 'pings_total': len(pings), 'pings_ok': len(ok_pings), 'survival_rate': len(ok_pings) / max(1, len(pings)), 'first_failure_at_sec': next((p['alive_sec'] for p in pings if not p['ok']), None), 'total_alive_sec': pings[-1]['alive_sec'] if pings else 0, 'cost_usd_est': cost_est}
    write_jsonl(BENCH, args.provider, {'summary': summary, 'pings': pings})
    print(f"\n[summary] {args.provider}: {summary['pings_ok']}/{summary['pings_total']} pings ok ({summary['survival_rate']:.0%})")
    if summary['first_failure_at_sec'] is not None:
        print(f"  first failure at {summary['first_failure_at_sec']:.0f}s into life")
    print(f'  est_cost: ${cost_est:.4f}')
if __name__ == '__main__':
    main()
