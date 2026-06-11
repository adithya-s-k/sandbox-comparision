from __future__ import annotations
import argparse
from dotenv import load_dotenv
from _common import write_jsonl, stats, env_check, fresh_adapter, ROOT
load_dotenv(ROOT / '.env')
BENCH = 'b03_io_throughput'
SIZES = [('1KB', 1024), ('64KB', 64 * 1024), ('1MB', 1024 * 1024), ('10MB', 10 * 1024 * 1024)]

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--provider', required=True, choices=['e2b', 'hf', 'mcp'])
    ap.add_argument('--repeats', type=int, default=3)
    args = ap.parse_args()
    if not env_check(args.provider):
        return
    a = fresh_adapter(args.provider)
    c = a.create()
    if not c.ok:
        print(f'[abort] create failed: {c.error_kind} {c.error_msg}')
        return
    rows = []
    for label, nbytes in SIZES:
        payload = 'x' * nbytes
        write_lat, read_lat = ([], [])
        for k in range(args.repeats):
            wr = a.write(f'/tmp/probe_{label}.txt', payload)
            rd = a.read(f'/tmp/probe_{label}.txt')
            if wr.ok:
                write_lat.append(wr.elapsed_ms)
            if rd.ok:
                read_lat.append(rd.elapsed_ms)
            read_val = rd.value if isinstance(rd.value, str) else rd.value.decode('utf-8', 'replace') if rd.value else ''
            ok = wr.ok and rd.ok and (read_val == payload)
            print(f'  {label:>5}  rep={k + 1}/{args.repeats}  write={wr.elapsed_ms:.0f}ms  read={rd.elapsed_ms:.0f}ms  ok={ok}')
        w_med = sorted(write_lat)[len(write_lat) // 2] if write_lat else float('nan')
        r_med = sorted(read_lat)[len(read_lat) // 2] if read_lat else float('nan')
        rows.append({'size_label': label, 'size_bytes': nbytes, 'write_ms': stats(write_lat), 'read_ms': stats(read_lat), 'write_mb_per_s': nbytes / 1000000.0 / (w_med / 1000.0) if write_lat else 0, 'read_mb_per_s': nbytes / 1000000.0 / (r_med / 1000.0) if read_lat else 0})
    cost_est = a.estimated_cost_usd()
    a.terminate()
    summary = {'bench': BENCH, 'provider': args.provider, 'cost_usd_est': cost_est, 'rows': rows}
    write_jsonl(BENCH, args.provider, summary)
    print(f'\n[summary] {args.provider}:')
    print(f"  {'size':>5}   write MB/s   read MB/s")
    for r in rows:
        print(f"  {r['size_label']:>5}   {r['write_mb_per_s']:>9.2f}   {r['read_mb_per_s']:>9.2f}")
if __name__ == '__main__':
    main()
