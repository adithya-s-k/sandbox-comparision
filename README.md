# sandbox-comparison

Side-by-side scalability benchmark of code-execution sandboxes (CPU-only):

- **E2B** — `e2b` Python SDK
- **hf-sandbox** — Modal-style sandbox on HF Jobs ([PR #7](https://github.com/huggingface/hf-sandbox/pull/7) HF Jobs proxy path)
- **hf-rust** — `Sandbox` API built into `huggingface_hub` ([PR #4350](https://github.com/huggingface/huggingface_hub/pull/4350)), **dedicated-VM** mode (Rust `sbx-server`, 1 sandbox = 1 Job)
- **hf-pool** — same `huggingface_hub` API ([PR #4350](https://github.com/huggingface/huggingface_hub/pull/4350)), **host/pool** mode: `SandboxPool`, 1 Job = 1 host = N sandboxes (uid + Landlock)
- **MCP** — a remote-code-execution MCP server over Streamable HTTP

📋 **[REPORT.md](REPORT.md)** — full writeup with charts, tables, and recommendation.

## TL;DR

- hf-sandbox PR #7 (cloudflared → HF Jobs proxy) removes the N=50 concurrent-create
  failure cliff: **100% at N=5/20/50** (was 58% at N=50), **10/10 concurrent exec** (was 4/10).
- Warm exec on hf-sandbox is now ~2.3× faster than E2B (8.4 vs 3.6 ops/s); 10 MB writes ~2.9× faster.
- E2B still wins cold boot (~0.6s vs ~16s) and large reads (~34 vs ~4 MB/s).
- MCP boots in ~0.9s (E2B-class) and holds 50 concurrent in ~3s, but is execution-only (no shell, no file transfer).
- Max concurrency (held simultaneously): HF Jobs ~200 at 100% (B07, cliff at 500, boot-timeout);
  MCP endpoint ~300 at 100% when warm (B08, cliff at 400, request-timeout). Both cap on throughput, not quota.
- **hf-pool (host mode, PR #4350):** first sandbox on a host pays ~6s cold start, every
  subsequent one is **~250ms (~26×)**; **100 sandboxes pack onto one host** with no idle
  latency penalty; isolation (uid + Landlock) holds — but **no cgroups**, so a CPU-bound
  neighbour can slow peers ~8×.
- **hf-pool 1000-sandbox scale-out (B13):** could **not** reproduce upstream's "20 hosts /
  16s" — `SandboxPool.create()` doesn't pack under concurrency (a host-reuse race spawns
  ~1 host/sandbox at conc=100, vs 20/host at conc=4), so 1000 sandboxes sprawled to
  107–218 hosts in 65–129s at ~90% success. Packing only works with paced creates;
  `max_hosts`/`warm_up` had no effect. The earlier "endpoint paused" error was transient.

## Layout

```
.
├── REPORT.md            # the writeup
├── report.html          # self-contained HTML version
├── adapters/            # uniform 5-method API per provider (e2b / hf / hf-rust / mcp)
├── benchmarks/          # b01..b07 micro-benchmarks
├── scripts/             # verify_setup, plot_results, build_html_report, run_*.sh
└── results/
    ├── raw/             # append-only JSONL per (bench, provider)
    ├── raw_cloudflare_v0/  # archived pre-PR#7 hf-sandbox data
    └── charts/          # PNGs used in the report
```

## Setup

```bash
uv venv --python 3.12 && source .venv/bin/activate
uv pip install -e .
cp .env.example .env   # then fill in keys for the providers you want to run
```

Dependency notes:

- **hf-sandbox** PR #7 is not yet on PyPI. Until it merges, install it from the branch
  (it needs `huggingface_hub>=1.19`):

  ```bash
  uv pip install "huggingface_hub>=1.19"
  uv pip install --no-deps "git+https://github.com/huggingface/hf-sandbox.git@chore/drop-cloudflared"
  ```

- **hf-rust** benchmarks the `Sandbox` API from
  [huggingface_hub PR #4350](https://github.com/huggingface/huggingface_hub/pull/4350),
  not yet released. Until it merges, install `huggingface_hub` from the branch:

  ```bash
  uv pip install "git+https://github.com/huggingface/huggingface_hub.git@sandbox-api"
  ```

- **hf-pool** is the **host/pool** mode of that same `huggingface_hub` install (no extra
  dependency). Tune packing via env: `HF_POOL_SANDBOXES_PER_HOST` (default 50),
  `HF_POOL_WARM_UP` (default 1), `HF_POOL_IMAGE`, `HF_POOL_FLAVOR`.

- **MCP**: set `MCP_ENDPOINT` in `.env` to a Streamable-HTTP MCP server exposing a
  `remote_code_execution(code, runtime)` tool (`runtime` ∈ {python, node}).

## Run

```bash
python scripts/verify_setup.py            # smoke test each configured provider

# Individual benchmarks (provider ∈ e2b | hf | hf-rust | hf-pool | mcp):
python benchmarks/b01_boot_latency.py     --provider e2b --n 5
python benchmarks/b02_exec_throughput.py  --provider hf
python benchmarks/b03_io_throughput.py    --provider mcp
python benchmarks/b04_concurrent_create.py --provider hf --n 50
python benchmarks/b05_concurrent_exec.py  --provider hf --n 10
python benchmarks/b06_long_running.py     --provider hf --minutes 5
python benchmarks/b07_max_provision.py    --provider hf --rungs 25,50,100,200,500,1000
python benchmarks/b08_mcp_concurrency.py   --rungs 10,25,50,100,200,400   # MCP endpoint only

# Pool/host-mode only (hf-pool):
python benchmarks/b09_amortized_boot.py   --densities 10,25,50 --n 20  # first-vs-warm boot
python benchmarks/b10_packing_density.py  --densities 1,10,25,50,100   # latency vs host fill
python benchmarks/b11_isolation.py                                     # uid + Landlock checks
python benchmarks/b12_noisy_neighbor.py   --hogs 24                    # no-cgroups contention
python benchmarks/b13_pool_scaleout.py    --total 1000 --concurrency 200  # scale-out (1000 sandboxes)
python benchmarks/b14_pool_correctness.py                              # warm_up / max_hosts / packing
python benchmarks/b15_soak.py             --minutes 30 --concurrency 20   # sustained churn / leak watch

# Full batteries:
bash scripts/run_hf_pr7.sh
bash scripts/run_hf_rust.sh
bash scripts/run_hf_pool.sh    # b01–b07 column + b09–b12 pool-only
bash scripts/run_mcp.sh

# Charts + HTML report:
python scripts/plot_results.py
python scripts/build_html_report.py
```

Raw results are appended to `results/raw/<bench>__<provider>.jsonl`. Charts are written
to `results/charts/`.
