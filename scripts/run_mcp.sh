#!/usr/bin/env bash
set -u
cd "$(dirname "$0")/.."
source .venv/bin/activate
set -a; source .env; set +a

if [ -z "${MCP_ENDPOINT:-}" ]; then
  echo "MCP_ENDPOINT is not set (add it to .env). Aborting."
  exit 1
fi

log() { echo "[$(date +%H:%M:%S)] $*"; }

log "B01 boot latency (n=5)"
python benchmarks/b01_boot_latency.py --provider mcp --n 5

log "B02 exec throughput (1 session, 100 ops)"
python benchmarks/b02_exec_throughput.py --provider mcp

log "B03 io throughput"
python benchmarks/b03_io_throughput.py --provider mcp

log "B04 concurrent create N=5"
python benchmarks/b04_concurrent_create.py --provider mcp --n 5
log "B04 concurrent create N=20"
python benchmarks/b04_concurrent_create.py --provider mcp --n 20
log "B04 concurrent create N=50"
python benchmarks/b04_concurrent_create.py --provider mcp --n 50

log "B05 concurrent exec N=10"
python benchmarks/b05_concurrent_exec.py --provider mcp --n 10

log "B06 long running (5 min)"
python benchmarks/b06_long_running.py --provider mcp

log "DONE"
