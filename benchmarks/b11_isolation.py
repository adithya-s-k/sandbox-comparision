"""B11 — isolation correctness (pool/host mode only).

Two co-resident sandboxes share one host VM but must not see each other. We check:
  · distinct uid per sandbox
  · private 0700 home — neighbour cannot read another sandbox's secret
  · NO_NEW_PRIVS set (no privilege escalation)
Emits a pass/fail table for the security section of the report.
"""
from __future__ import annotations
import time
from dotenv import load_dotenv
from _common import write_jsonl, env_check, ROOT
from adapters import HFPoolAdapter
load_dotenv(ROOT / '.env')
BENCH = 'b11_isolation'


def out(a, cmd: str) -> tuple[int, str]:
    r = a.exec(cmd)
    if not r.ok:
        return (-1, r.error_msg or '')
    return (r.value.get('rc', -1), r.value.get('stdout', '').strip())


def main() -> None:
    if not env_check('hf-pool'):
        return
    HFPoolAdapter.configure(sandboxes_per_host=4, warm_up=1, max_hosts=1)
    A, B = HFPoolAdapter(), HFPoolAdapter()
    ca, cb = A.create(), B.create()
    if not (ca.ok and cb.ok):
        print('[abort] could not create both sandboxes', ca.error_msg, cb.error_msg)
        HFPoolAdapter.reset_pool()
        return

    same_host = getattr(A.handle, 'host_id', None) == getattr(B.handle, 'host_id', 'x') and getattr(A.handle, 'host_id', None) is not None
    _, uid_a = out(A, 'id -u')
    _, uid_b = out(B, 'id -u')
    _, home_a = out(A, 'printf %s "$HOME"')
    A.exec(f'umask 077; printf SECRET-A > "$HOME/secret.txt"')
    _, perm = out(A, 'stat -c %a "$HOME" 2>/dev/null || stat -f %Lp "$HOME"')
    # B attempts to read A's secret by absolute path
    rc_read, leaked = out(B, f'cat {home_a}/secret.txt 2>/dev/null')
    _, nnp = out(B, "grep NoNewPrivs /proc/self/status | awk '{print $2}'")

    checks = {
        'co_resident_same_host': same_host,
        'distinct_uid': uid_a != uid_b and uid_a.isdigit() and uid_b.isdigit(),
        'home_is_0700': perm.strip().endswith('700'),
        'neighbor_cannot_read_secret': (rc_read != 0) or ('SECRET-A' not in leaked),
        'no_new_privs_set': nnp.strip() == '1',
    }
    detail = {'uid_a': uid_a, 'uid_b': uid_b, 'home_a': home_a, 'home_perm': perm, 'read_rc': rc_read, 'leaked': leaked[:40], 'no_new_privs': nnp}

    A.terminate(); B.terminate()
    HFPoolAdapter.reset_pool()

    verdict = all(checks.values())
    write_jsonl(BENCH, 'hf-pool', {'summary': {'bench': BENCH, 'provider': 'hf-pool', 'verdict': 'PASS' if verdict else 'FAIL', 'checks': checks, 'detail': detail}})
    print('\n[B11] isolation checks (pool, co-resident):')
    for k, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    print(f'  detail: {detail}')
    print(f"\n[verdict] {'PASS' if verdict else 'FAIL'}")


if __name__ == '__main__':
    main()
