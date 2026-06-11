from __future__ import annotations
import argparse
import time
from dotenv import load_dotenv
from _common import write_jsonl, stats, env_check, fresh_adapter, ROOT
load_dotenv(ROOT / '.env')
BENCH = 'b02_exec_throughput'

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--provider', required=True, choices=['e2b', 'hf', 'mcp'])
    ap.add_argument('--ops', type=int, default=100)
    args = ap.parse_args()
    if not env_check(args.provider):
        return
    a = fresh_adapter(args.provider)
    c = a.create()
    if not c.ok:
        print(f'[abort] create failed: {c.error_kind} {c.error_msg}')
        return
    latencies: list[float] = []
    errors = 0
    t0 = time.monotonic()
    for i in range(args.ops):
        r = a.exec('echo x')
        if r.ok:
            latencies.append(r.elapsed_ms)
        else:
            errors += 1
        if (i + 1) % 25 == 0:
            print(f'  [{i + 1}/{args.ops}] running … last={r.elapsed_ms:.0f}ms')
    total_sec = time.monotonic() - t0
    cost_est = a.estimated_cost_usd()
    a.terminate()
    row = {'bench': BENCH, 'provider': args.provider, 'ops_attempted': args.ops, 'ops_ok': len(latencies), 'errors': errors, 'total_sec': total_sec, 'ops_per_sec': len(latencies) / total_sec if total_sec else 0, 'exec_ms': stats(latencies), 'cost_usd_est': cost_est}
    write_jsonl(BENCH, args.provider, row)
    print(f"\n[summary] {args.provider}: {len(latencies)}/{args.ops} ok in {total_sec:.1f}s = {row['ops_per_sec']:.1f} ops/s")
    print(f"  exec_ms: {row['exec_ms']}")
if __name__ == '__main__':
    main()
