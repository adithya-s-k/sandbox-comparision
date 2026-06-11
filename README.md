# sandbox-comparison

Side-by-side scalability benchmark of code-execution sandboxes (CPU-only):

- **E2B** — `e2b` Python SDK
- **hf-sandbox** — Modal-style sandbox on HF Jobs ([PR #7](https://github.com/huggingface/hf-sandbox/pull/7) HF Jobs proxy path)
- **MCP** — a remote-code-execution MCP server over Streamable HTTP

📋 **[REPORT.md](REPORT.md)** — full writeup with charts, tables, and recommendation.

## TL;DR

- hf-sandbox PR #7 (cloudflared → HF Jobs proxy) removes the N=50 concurrent-create
  failure cliff: **100% at N=5/20/50** (was 58% at N=50), **10/10 concurrent exec** (was 4/10).
- Warm exec on hf-sandbox is now ~2.3× faster than E2B (8.4 vs 3.6 ops/s); 10 MB writes ~2.9× faster.
- E2B still wins cold boot (~0.6s vs ~16s) and large reads (~34 vs ~4 MB/s).
- MCP boots in ~0.9s (E2B-class) and holds 50 concurrent in ~3s, but is execution-only (no shell, no file transfer).
- HF Jobs max-provision (B07): 100% up to ~200 concurrent sandboxes; ~63% at 500 (boot-timeout, not quota).

## Layout

```
.
├── REPORT.md            # the writeup
├── report.html          # self-contained HTML version
├── adapters/            # uniform 5-method API per provider (e2b / hf / mcp)
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

- **MCP**: set `MCP_ENDPOINT` in `.env` to a Streamable-HTTP MCP server exposing a
  `remote_code_execution(code, runtime)` tool (`runtime` ∈ {python, node}).

## Run

```bash
python scripts/verify_setup.py            # smoke test each configured provider

# Individual benchmarks (provider ∈ e2b | hf | mcp):
python benchmarks/b01_boot_latency.py     --provider e2b --n 5
python benchmarks/b02_exec_throughput.py  --provider hf
python benchmarks/b03_io_throughput.py    --provider mcp
python benchmarks/b04_concurrent_create.py --provider hf --n 50
python benchmarks/b05_concurrent_exec.py  --provider hf --n 10
python benchmarks/b06_long_running.py     --provider hf --minutes 5
python benchmarks/b07_max_provision.py    --provider hf --rungs 25,50,100,200,500,1000

# Full batteries:
bash scripts/run_hf_pr7.sh
bash scripts/run_mcp.sh

# Charts + HTML report:
python scripts/plot_results.py
python scripts/build_html_report.py
```

Raw results are appended to `results/raw/<bench>__<provider>.jsonl`. Charts are written
to `results/charts/`.
