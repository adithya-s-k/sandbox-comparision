#!/usr/bin/env bash
set -u
cd "$(dirname "$0")/.."
source .venv/bin/activate
set -a; source .env; set +a

log() { echo "[$(date +%H:%M:%S)] $*"; }

log "B01 boot latency (n=5)"
python benchmarks/b01_boot_latency.py --provider hf-rust --n 5

log "B02 exec throughput (1 sandbox, 100 ops)"
python benchmarks/b02_exec_throughput.py --provider hf-rust

log "B03 io throughput"
python benchmarks/b03_io_throughput.py --provider hf-rust

log "B04 concurrent create N=5"
python benchmarks/b04_concurrent_create.py --provider hf-rust --n 5
log "B04 concurrent create N=20"
python benchmarks/b04_concurrent_create.py --provider hf-rust --n 20
log "B04 concurrent create N=50"
python benchmarks/b04_concurrent_create.py --provider hf-rust --n 50

log "B05 concurrent exec N=10"
python benchmarks/b05_concurrent_exec.py --provider hf-rust --n 10

log "B06 long running (5 min)"
python benchmarks/b06_long_running.py --provider hf-rust

log "DONE"
