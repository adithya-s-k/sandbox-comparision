from __future__ import annotations
import json
import sys
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'results' / 'raw'
CH = ROOT / 'results' / 'charts'
CH.mkdir(parents=True, exist_ok=True)
COLOR = {'e2b': '#59a6ff', 'hf': '#ffa05c', 'hf-rust': '#e05c5c', 'hf-pool': '#b15cff', 'mcp': '#7ddc6b'}
PROVIDERS = ['e2b', 'hf', 'hf-rust', 'hf-pool', 'mcp']

import os
SINCE = float(os.getenv('PLOT_SINCE', '0'))  # filter to runs at/after this epoch


def load(bench, provider):
    p = RAW / f'{bench}__{provider}.jsonl'
    if not p.exists():
        return []
    out = []
    for l in open(p):
        r = json.loads(l)
        ts = r.get('ts') or (r.get('summary') or {}).get('ts', 0)
        if SINCE and ts and ts < SINCE:
            continue
        out.append(r)
    return out

def plot_b01():
    fig, ax = plt.subplots(figsize=(8, 4))
    metrics = ['p50', 'p90', 'p99']
    width = 0.8 / len(PROVIDERS)
    x = list(range(len(metrics)))
    for i, prov in enumerate(PROVIDERS):
        rows = [r for r in load('b01_boot_latency', prov) if r.get('ok')]
        vals = []
        for m in metrics:
            tot = sorted([r['t_total_ms'] for r in rows])
            if not tot:
                vals.append(0)
                continue
            k = int(round({'p50': 0.5, 'p90': 0.9, 'p99': 0.99}[m] * (len(tot) - 1)))
            vals.append(tot[k])
        offset = (i - (len(PROVIDERS) - 1) / 2) * width
        bars = ax.bar([xi + offset for xi in x], vals, width, label=prov, color=COLOR[prov])
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v, f'{v:.0f}ms', ha='center', va='bottom', fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels(metrics)
    ax.set_ylabel('boot→ready (ms)')
    ax.set_title('B01 — Cold boot latency (create + first exec)')
    ax.legend()
    ax.set_yscale('log')
    plt.tight_layout()
    plt.savefig(CH / 'b01_boot_latency.png', dpi=130)
    plt.close()
    print(f"  wrote {CH / 'b01_boot_latency.png'}")

def plot_b04():
    Ns = [5, 20, 50]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))
    for prov in PROVIDERS:
        f = RAW / f'b04_concurrent_create__{prov}.jsonl'
        if not f.exists():
            continue
        rows = [json.loads(l)['summary'] for l in open(f)]
        by_n = {r['n']: r for r in rows}
        rates = [by_n[N]['success_rate'] * 100 if N in by_n else 0 for N in Ns]
        p99s = [by_n[N]['t_ready_ms']['p99'] if N in by_n and by_n[N]['t_ready_ms'].get('p99') else 0 for N in Ns]
        ax1.plot(Ns, rates, marker='o', linewidth=2.5, label=prov, color=COLOR[prov])
        ax2.plot(Ns, p99s, marker='o', linewidth=2.5, label=prov, color=COLOR[prov])
    ax1.set_xlabel('concurrent sandbox count N')
    ax1.set_ylabel('success rate (%)')
    ax1.set_title('B04 — Concurrent-create success rate')
    ax1.set_ylim(0, 105)
    ax1.grid(True, alpha=0.3)
    ax1.legend()
    ax2.set_xlabel('concurrent sandbox count N')
    ax2.set_ylabel('p99 boot→ready (ms)')
    ax2.set_title('B04 — Concurrent-create p99 boot time')
    ax2.set_yscale('log')
    ax2.grid(True, alpha=0.3)
    ax2.legend()
    plt.tight_layout()
    plt.savefig(CH / 'b04_scaling.png', dpi=130)
    plt.close()
    print(f"  wrote {CH / 'b04_scaling.png'}")

def plot_b03():
    sizes = ['1KB', '64KB', '1MB', '10MB']
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))
    for prov in PROVIDERS:
        data = load('b03_io_throughput', prov)
        if not data:
            continue
        rows = data[-1]['rows']
        w = [r['write_mb_per_s'] for r in rows]
        r = [r['read_mb_per_s'] for r in rows]
        ax1.plot(sizes, w, marker='o', linewidth=2.5, label=prov, color=COLOR[prov])
        ax2.plot(sizes, r, marker='o', linewidth=2.5, label=prov, color=COLOR[prov])
    ax1.set_ylabel('MB/s')
    ax1.set_title('B03 — write_file throughput')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax2.set_ylabel('MB/s')
    ax2.set_title('B03 — read_file throughput')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(CH / 'b03_io.png', dpi=130)
    plt.close()
    print(f"  wrote {CH / 'b03_io.png'}")

def plot_concurrency():
    # hf-pool intentionally omitted: its B07 ramp ≥50 is poisoned by the backend
    # self-pause (not a real ceiling) — re-add once the endpoint is restarted.
    series = [('hf', 'b07_max_provision', 'hf-sandbox (HF Jobs)'), ('hf-rust', 'b07_max_provision', 'hf Sandbox API — dedicated VM'), ('mcp', 'b08_mcp_concurrency', 'MCP endpoint')]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    plotted = False
    for prov, bench, label in series:
        rows = [json.loads(l)['summary'] for l in (RAW / f'{bench}__{prov}.jsonl').open()] if (RAW / f'{bench}__{prov}.jsonl').exists() else []
        if not rows:
            continue
        by_n = {r['n']: r['success_rate'] * 100 for r in rows}
        ns = sorted(by_n)
        ax.plot(ns, [by_n[n] for n in ns], marker='o', linewidth=2.5, label=label, color=COLOR[prov])
        plotted = True
    if not plotted:
        plt.close()
        return
    ax.axhline(90, ls='--', color='#888', alpha=0.6, label='90% threshold')
    ax.set_xlabel('concurrent sandboxes / sessions held open (N)')
    ax.set_ylabel('success rate (%)')
    ax.set_ylim(0, 105)
    ax.set_title('Max concurrency — success rate vs N')
    ax.grid(True, alpha=0.3)
    ax.legend()
    plt.tight_layout()
    plt.savefig(CH / 'concurrency.png', dpi=130)
    plt.close()
    print(f"  wrote {CH / 'concurrency.png'}")
def plot_b09_amortized():
    """B09 — first (cold host) vs warm create+ready, per density."""
    data = [json.loads(l)['summary'] for l in (RAW / 'b09_amortized_boot__hf-pool.jsonl').open()] if (RAW / 'b09_amortized_boot__hf-pool.jsonl').exists() else []
    if not data:
        return
    by_d = {r['density']: r for r in data}
    dens = sorted(by_d)
    first = [by_d[d]['first_ready_ms'] for d in dens]
    warm = [by_d[d]['warm_ready_ms'].get('p50', 0) for d in dens]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    x = list(range(len(dens)))
    w = 0.38
    b1 = ax.bar([xi - w / 2 for xi in x], first, w, label='first sandbox (host cold start)', color='#e05c5c')
    b2 = ax.bar([xi + w / 2 for xi in x], warm, w, label='warm sandbox (p50)', color='#b15cff')
    for bars in (b1, b2):
        for b in bars:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(), f'{b.get_height():.0f}', ha='center', va='bottom', fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels([f'{d}/host' for d in dens])
    ax.set_xlabel('sandboxes_per_host')
    ax.set_ylabel('create + first exec (ms)')
    ax.set_yscale('log')
    ax.set_title('B09 — Amortized boot: first vs warm sandbox (pool mode)')
    ax.legend()
    plt.tight_layout()
    plt.savefig(CH / 'b09_amortized_boot.png', dpi=130)
    plt.close()
    print(f"  wrote {CH / 'b09_amortized_boot.png'}")

def plot_b10_density():
    """B10 — warm create & exec p50 as one host fills up."""
    data = [json.loads(l)['summary'] for l in (RAW / 'b10_packing_density__hf-pool.jsonl').open()] if (RAW / 'b10_packing_density__hf-pool.jsonl').exists() else []
    if not data:
        return
    by_d = {r['density']: r for r in data}
    dens = sorted(by_d)
    cre = [by_d[d]['warm_create_ms'].get('p50', 0) for d in dens]
    exe = [by_d[d]['warm_exec_ms'].get('p50', 0) for d in dens]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(dens, cre, marker='o', linewidth=2.5, label='warm create p50', color='#b15cff')
    ax.plot(dens, exe, marker='s', linewidth=2.5, label='warm exec p50', color='#59a6ff')
    ax.set_xlabel('sandboxes packed on one host')
    ax.set_ylabel('latency p50 (ms)')
    ax.set_ylim(bottom=0)
    ax.set_title('B10 — Packing density: per-sandbox latency vs host fill')
    ax.grid(True, alpha=0.3)
    ax.legend()
    plt.tight_layout()
    plt.savefig(CH / 'b10_density.png', dpi=130)
    plt.close()
    print(f"  wrote {CH / 'b10_density.png'}")

def plot_b12_noisy():
    """B12 — victim exec p50 idle vs under co-resident CPU hogs."""
    data = [json.loads(l)['summary'] for l in (RAW / 'b12_noisy_neighbor__hf-pool.jsonl').open()] if (RAW / 'b12_noisy_neighbor__hf-pool.jsonl').exists() else []
    if not data:
        return
    s = data[-1]
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    labels = ['idle host', f"under {s['hogs']} hogs"]
    vals = [s['idle_exec_ms'].get('p50', 0), s['loaded_exec_ms'].get('p50', 0)]
    bars = ax.bar(labels, vals, color=['#7ddc6b', '#e05c5c'], width=0.55)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v, f'{v:.0f}ms', ha='center', va='bottom', fontsize=10)
    ax.set_ylabel('victim exec p50 (ms)')
    ax.set_title(f"B12 — Noisy neighbor on {s.get('cores')}-core host (no cgroups): {s['p50_slowdown_pct']:+.0f}%")
    plt.tight_layout()
    plt.savefig(CH / 'b12_noisy_neighbor.png', dpi=130)
    plt.close()
    print(f"  wrote {CH / 'b12_noisy_neighbor.png'}")

if __name__ == '__main__':
    plot_b01()
    plot_b04()
    plot_b03()
    plot_concurrency()
    plot_b09_amortized()
    plot_b10_density()
    plot_b12_noisy()
    print('\nAll charts in', CH)
