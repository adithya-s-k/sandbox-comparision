"""Extract the LATEST run's headline metrics per (bench, provider) from the
append-only raw JSONL, so the final report uses today's v1.22 data — not the
June rows sitting in the same files. Prints a compact comparison and writes
results/summary_latest.json.

Usage: python scripts/summarize.py [--since EPOCH]
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'results' / 'raw'
PROV = ['e2b', 'hf-rust', 'hf-pool', 'hf', 'mcp']


def rows(bench: str, prov: str, since: float) -> list[dict]:
    p = RAW / f'{bench}__{prov}.jsonl'
    if not p.exists():
        return []
    out = []
    for line in p.open():
        try:
            r = json.loads(line)
        except Exception:
            continue
        ts = r.get('ts') or (r.get('summary') or {}).get('ts', 0)
        if ts and ts < since:
            continue
        out.append(r)
    return out


def last(bench: str, prov: str, since: float):
    r = rows(bench, prov, since)
    return r[-1] if r else None


def g(d: dict | None, *path, default=None):
    for k in path:
        if not isinstance(d, dict):
            return default
        d = d.get(k)
    return d if d is not None else default


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--since', type=float, default=0.0, help='only rows with ts >= this epoch (0 = all, take last)')
    args = ap.parse_args()
    out = {}
    for prov in PROV:
        s = {}
        b01 = last('b01_boot_latency', prov, args.since)
        # b01 rows are per-run dicts appended individually; grab the last N ok ones
        b01_rows = [r for r in rows('b01_boot_latency', prov, args.since) if r.get('ok')]
        if b01_rows:
            tot = sorted(r['t_total_ms'] for r in b01_rows)
            cre = sorted(r['t_create_ms'] for r in b01_rows)
            s['b01_boot_ready_p50_ms'] = tot[len(tot) // 2]
            s['b01_create_min_ms'] = cre[0]
            s['b01_create_max_ms'] = cre[-1]
        b02 = last('b02_exec_throughput', prov, args.since)
        s['b02_ops_per_s'] = round(g(b02, 'ops_per_sec', default=0), 2)
        s['b02_exec_p50_ms'] = round(g(b02, 'exec_ms', 'p50', default=0))
        b03 = last('b03_io_throughput', prov, args.since)
        for row in (g(b03, 'rows', default=[]) or []):
            if row.get('size_label') == '10MB':
                s['b03_10mb_write_mbs'] = round(row.get('write_mb_per_s', 0), 2)
                s['b03_10mb_read_mbs'] = round(row.get('read_mb_per_s', 0), 2)
        for n in (5, 20, 50):
            r = [x for x in rows('b04_concurrent_create', prov, args.since) if g(x, 'summary', 'n') == n]
            if r:
                sm = r[-1]['summary']
                s[f'b04_n{n}_success'] = round(sm['success_rate'] * 100)
                s[f'b04_n{n}_wall_s'] = round(sm['wall_sec'], 1)
        b05 = last('b05_concurrent_exec', prov, args.since)
        s['b05_success'] = round(g(b05, 'summary', 'success_rate', default=0) * 100)
        b06 = last('b06_long_running', prov, args.since) or {}
        b06 = b06.get('summary', b06)  # b06 stores its summary flat
        s['b06_pings'] = f"{b06.get('pings_ok', '?')}/{b06.get('pings_total', '?')}"
        out[prov] = s

    (ROOT / 'results' / 'summary_latest.json').write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps(out, indent=2, default=str))


if __name__ == '__main__':
    main()
