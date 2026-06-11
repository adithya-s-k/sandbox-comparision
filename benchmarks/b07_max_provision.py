from __future__ import annotations
import argparse
import threading
import time
from collections import Counter
from dotenv import load_dotenv
from _common import write_jsonl, stats, env_check, fresh_adapter, ROOT
load_dotenv(ROOT / '.env')
BENCH = 'b07_max_provision'

def _provision_and_hold(provider, idx, release: threading.Event, out: list) -> None:
    rec = {'idx': idx, 'adapter': None}
    try:
        a = fresh_adapter(provider)
        rec['adapter'] = a
        t0 = time.monotonic()
        c = a.create()
        rec['t_create_ms'] = (time.monotonic() - t0) * 1000.0
        if not c.ok:
            rec.update(ok=False, stage='create', error_kind=c.error_kind, error_msg=c.error_msg)
            out.append(rec)
            return
        ex = a.exec('echo ready')
        healthy = ex.ok and ex.value.get('stdout', '').strip() == 'ready'
        rec.update(ok=healthy, stage=None if healthy else 'exec', error_kind=ex.error_kind, error_msg=ex.error_msg)
        out.append(rec)
        release.wait(timeout=900)
    except BaseException as e:
        rec.setdefault('t_create_ms', 0.0)
        rec.update(ok=False, stage='exception', error_kind='harness_exception', error_msg=f'{type(e).__name__}: {e}')
        out.append(rec)

def _teardown(records: list) -> None:
    threads = []
    for r in records:
        a = r.get('adapter')
        if a is None:
            continue
        t = threading.Thread(target=a.terminate, daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join(timeout=60)
_LIVE = ('RUNNING', 'UPDATING', 'PENDING', 'QUEUED', 'STARTING')

def _sweep_orphans(provider: str, max_passes: int=15) -> int:
    if provider != 'hf':
        return 0
    try:
        from huggingface_hub import list_jobs, cancel_job
    except Exception:
        return 0
    total = 0
    for _ in range(max_passes):
        live = 0
        try:
            jobs = list_jobs()
        except Exception:
            break
        for job in jobs:
            st = getattr(getattr(job, 'status', None), 'stage', None) or getattr(job, 'status', None)
            if str(st).upper() in _LIVE:
                live += 1
                try:
                    cancel_job(job_id=job.id)
                    total += 1
                except Exception:
                    pass
        if live == 0:
            break
        time.sleep(2)
    return total

def run_rung(provider: str, n: int) -> dict:
    release = threading.Event()
    records: list = []
    threads = [threading.Thread(target=_provision_and_hold, args=(provider, i, release, records), daemon=True) for i in range(n)]
    print(f'\n[rung N={n}] firing {n} concurrent creates (holding all alive)…')
    t0 = time.monotonic()
    for t in threads:
        t.start()
    deadline = time.monotonic() + 600
    while len(records) < n and time.monotonic() < deadline:
        time.sleep(0.5)
    fan_sec = time.monotonic() - t0
    ok = [r for r in records if r.get('ok')]
    fail = [r for r in records if not r.get('ok')]
    err_kinds = Counter((r.get('error_kind') for r in fail))
    unresolved = n - len(records)
    if unresolved > 0:
        err_kinds['unresolved_timeout'] = unresolved
    err_samples: dict[str, str] = {}
    for r in fail:
        k = r.get('error_kind') or 'unknown'
        if k not in err_samples and r.get('error_msg'):
            err_samples[k] = r['error_msg'][:300]
    peak_concurrent = len(ok)
    print(f'[rung N={n}] healthy={len(ok)}/{n} ({len(ok) / n:.0%})  peak_concurrent={peak_concurrent}  fan_out={fan_sec:.1f}s')
    if err_kinds:
        print(f'           errors: {dict(err_kinds)}')
        for k, msg in err_samples.items():
            print(f'             · {k}: {msg}')
    release.set()
    print(f'[rung N={n}] tearing down {len(records)} sandboxes…')
    _teardown(records)
    swept = _sweep_orphans(provider)
    if swept:
        print(f'[rung N={n}] swept {swept} orphan job(s)')
    summary = {'bench': BENCH, 'provider': provider, 'n': n, 'healthy': len(ok), 'failed': len(fail), 'success_rate': len(ok) / n, 'peak_concurrent': peak_concurrent, 'fan_out_sec': fan_sec, 'unresolved': unresolved, 't_create_ms': stats([r['t_create_ms'] for r in records if 't_create_ms' in r]), 'error_kinds': dict(err_kinds), 'error_samples': err_samples, 'swept_orphans': swept}
    rows = [{k: v for k, v in r.items() if k != 'adapter'} for r in records]
    write_jsonl(BENCH, provider, {'summary': summary, 'results': rows})
    return summary

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--provider', required=True, choices=['e2b', 'hf', 'mcp'])
    ap.add_argument('--rungs', default='25,50,100,200,500', help='comma-separated N values to ramp through')
    ap.add_argument('--stop-below', type=float, default=0.9, help="stop ramping once a rung's success rate falls below this")
    args = ap.parse_args()
    if not env_check(args.provider):
        return
    rungs = [int(x) for x in args.rungs.split(',') if x.strip()]
    print(f'[B07] provider={args.provider}  ramp={rungs}  stop_below={args.stop_below:.0%}')
    HARD = {'quota', 'rate', '429', 'auth'}
    ceiling = None
    for n in rungs:
        s = run_rung(args.provider, n)
        kinds = s['error_kinds'] or {}
        hard_hit = sorted((k for k in kinds if k in HARD))
        novel = sorted((k for k in kinds if k not in HARD and k not in ('timeout', 'tunnel', 'sandbox_died', 'other')))
        if s['success_rate'] < args.stop_below or hard_hit or novel:
            ceiling = s
            if hard_hit:
                reason = f'hard-limit errors {hard_hit}'
            elif novel:
                reason = f"unexpected error kind(s) {novel} — sample: {s['error_samples']}"
            else:
                reason = f"success {s['success_rate']:.0%} < {args.stop_below:.0%}"
            print(f'\n[CEILING] hit at N={n} — {reason}. Stopping ramp.')
            break
        time.sleep(10)
    print('\n' + '=' * 64)
    if ceiling:
        print(f"[result] practical concurrent ceiling ≈ between previous rung and N={ceiling['n']} (N={ceiling['n']} gave {ceiling['healthy']}/{ceiling['n']}, errors={ceiling['error_kinds']})")
    else:
        print(f"[result] no ceiling found within ramp {rungs} — all rungs ≥{args.stop_below:.0%}. Highest tested N={rungs[-1]} held {run_rung.__name__ and ''}cleanly.")
    swept = _sweep_orphans(args.provider)
    if swept:
        print(f'[cleanup] final sweep cancelled {swept} orphan job(s)')
if __name__ == '__main__':
    main()
