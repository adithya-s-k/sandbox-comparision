#!/usr/bin/env bash
set -u
cd "$(dirname "$0")/.."
source .venv/bin/activate
set -a; source .env; set +a

log() { echo "[$(date +%H:%M:%S)] $*"; }

# ── Phase A: uniform b01–b07 column (same shape as other providers) ──
log "B01 boot latency (n=5)"
python benchmarks/b01_boot_latency.py --provider hf-pool --n 5

log "B02 exec throughput (1 sandbox, 100 ops)"
python benchmarks/b02_exec_throughput.py --provider hf-pool

log "B03 io throughput"
python benchmarks/b03_io_throughput.py --provider hf-pool

log "B04 concurrent create N=5 / 20 / 50"
python benchmarks/b04_concurrent_create.py --provider hf-pool --n 5
python benchmarks/b04_concurrent_create.py --provider hf-pool --n 20
python benchmarks/b04_concurrent_create.py --provider hf-pool --n 50

log "B05 concurrent exec N=10"
python benchmarks/b05_concurrent_exec.py --provider hf-pool --n 10

log "B06 long running (5 min)"
python benchmarks/b06_long_running.py --provider hf-pool

log "B07 max provision (ramp 25,50,100,200)"
python benchmarks/b07_max_provision.py --provider hf-pool --rungs 25,50,100,200

# ── New pool-only measurements (new columns) ──
log "B09 amortised boot (densities 10,25,50)"
python benchmarks/b09_amortized_boot.py --densities 10,25,50 --n 20

log "B10 packing density sweep (1,10,25,50,100)"
python benchmarks/b10_packing_density.py --densities 1,10,25,50,100

log "B11 isolation correctness"
python benchmarks/b11_isolation.py

log "B12 noisy neighbour (24 hogs — oversubscribe the ~16-core host)"
python benchmarks/b12_noisy_neighbor.py --hogs 24

log "DONE"
