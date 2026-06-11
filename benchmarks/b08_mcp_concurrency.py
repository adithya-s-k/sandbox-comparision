from __future__ import annotations
import argparse
import asyncio
import os
import time
from dotenv import load_dotenv
from _common import write_jsonl, stats, ROOT
load_dotenv(ROOT / '.env')
BENCH = 'b08_mcp_concurrency'
_TOOL = 'remote_code_execution'

def _headers() -> dict[str, str]:
    return {'Authorization': f"Bearer {os.getenv('HF_TOKEN', '')}"}

def _leaf_error(e: BaseException) -> tuple[str, str]:
    cur = e
    while getattr(cur, 'exceptions', None):
        cur = cur.exceptions[0]
    return (type(cur).__name__, str(cur)[:300])

async def one_session(idx: int, endpoint: str, release: asyncio.Event, out: list) -> None:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    rec: dict = {'idx': idx}
    t0 = time.monotonic()
    try:
        async with streamablehttp_client(endpoint, headers=_headers()) as (r, w, _):
            async with ClientSession(r, w) as s:
                await asyncio.wait_for(s.initialize(), timeout=120)
                rec['t_create_ms'] = (time.monotonic() - t0) * 1000.0
                res = await asyncio.wait_for(s.call_tool(_TOOL, {'runtime': 'python', 'code': "print('ready')"}), timeout=120)
                txt = ''.join((getattr(c, 'text', '') for c in res.content))
                rec['ok'] = 'ready' in txt
                if not rec['ok']:
                    rec['error_kind'] = 'bad_output'
                    rec['error_msg'] = txt[:200]
                out.append(rec)
                await release.wait()
    except BaseException as e:
        rec.setdefault('t_create_ms', (time.monotonic() - t0) * 1000.0)
        rec['ok'] = False
        rec['error_kind'], rec['error_msg'] = _leaf_error(e)
        out.append(rec)

async def run_rung(endpoint: str, n: int) -> dict:
    release = asyncio.Event()
    out: list = []
    print(f'\n[rung N={n}] opening {n} concurrent MCP sessions (holding all open)…')
    t0 = time.monotonic()
    tasks = [asyncio.create_task(one_session(i, endpoint, release, out)) for i in range(n)]
    deadline = time.monotonic() + 300
    while len(out) < n and time.monotonic() < deadline:
        await asyncio.sleep(0.2)
    fan_sec = time.monotonic() - t0
    ok = [r for r in out if r.get('ok')]
    fail = [r for r in out if not r.get('ok')]
    from collections import Counter
    err_kinds = Counter((r.get('error_kind') for r in fail))
    unresolved = n - len(out)
    if unresolved:
        err_kinds['unresolved_timeout'] = unresolved
    err_samples: dict[str, str] = {}
    for r in fail:
        k = r.get('error_kind') or 'unknown'
        if k not in err_samples and r.get('error_msg'):
            err_samples[k] = r['error_msg']
    print(f'[rung N={n}] healthy={len(ok)}/{n} ({len(ok) / n:.0%})  peak_concurrent={len(ok)}  fan_out={fan_sec:.1f}s')
    if err_kinds:
        print(f'           errors: {dict(err_kinds)}')
        for k, msg in err_samples.items():
            print(f'             · {k}: {msg}')
    release.set()
    await asyncio.gather(*tasks, return_exceptions=True)
    summary = {'bench': BENCH, 'provider': 'mcp', 'n': n, 'healthy': len(ok), 'failed': len(fail), 'success_rate': len(ok) / n, 'peak_concurrent': len(ok), 'fan_out_sec': fan_sec, 'unresolved': unresolved, 't_create_ms': stats([r['t_create_ms'] for r in out if 't_create_ms' in r]), 'error_kinds': dict(err_kinds), 'error_samples': err_samples}
    write_jsonl(BENCH, 'mcp', {'summary': summary, 'results': out})
    return summary

async def main_async(rungs: list[int], stop_below: float) -> None:
    endpoint = os.getenv('MCP_ENDPOINT', '')
    if not endpoint:
        print('MCP_ENDPOINT not set')
        return
    print(f'[B08] endpoint={endpoint}  ramp={rungs}  stop_below={stop_below:.0%}')
    ceiling = None
    for n in rungs:
        s = await run_rung(endpoint, n)
        kinds = s['error_kinds'] or {}
        if s['success_rate'] < stop_below or kinds:
            ceiling = s
            print(f"\n[CEILING] hit at N={n} — success {s['success_rate']:.0%}, errors={kinds}. Stopping.")
            break
        await asyncio.sleep(5)
    print('\n' + '=' * 64)
    if ceiling:
        print(f"[result] MCP endpoint concurrency ceiling ≈ between prior rung and N={ceiling['n']} (N={ceiling['n']} held {ceiling['healthy']}/{ceiling['n']}, errors={ceiling['error_kinds']})")
    else:
        print(f'[result] no ceiling within ramp {rungs} — endpoint held all rungs ≥{stop_below:.0%}.')

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--rungs', default='10,25,50,100,200,400')
    ap.add_argument('--stop-below', type=float, default=0.9)
    args = ap.parse_args()
    rungs = [int(x) for x in args.rungs.split(',') if x.strip()]
    asyncio.run(main_async(rungs, args.stop_below))
if __name__ == '__main__':
    main()
