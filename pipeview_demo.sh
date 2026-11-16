#!/usr/bin/env bash
# pipeview_demo.sh - cycle-by-cycle pipeline views for the report.
# Produces results/trace/<name>/pipeview.txt (o3-pipeview timeline) and latency.json.
set -eu
cd "$(dirname "$0")/.."
GEM5=${GEM5:-$HOME/gem5}
SIM="$GEM5/build/X86/gem5.opt"

trace() {   # trace <name> <ilp.py options...>
    local name=$1; shift
    local out=results/trace/$name
    mkdir -p "$out"
    "$SIM" -re --debug-flags=O3PipeView --debug-file=/tmp/$name.trace --outdir="$out" configs/ilp.py "$@"
    # Show instructions from inside main's loop, not start-up code: find main's
    # address range in the binary, then the first traced instruction there
    # (skipping ahead SKIP instructions so the loop is in steady state).
    local bin=$2          # options start with: --binary <path>

    local range
    range=$(python3 - "$bin" /tmp/$name.trace "${SKIP:-2000}" "${COUNT:-40}" <<'PY'
import subprocess, sys
binary, trace, skip, count = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
lo = hi = None
for line in subprocess.run(["nm", "-S", binary], capture_output=True, text=True).stdout.splitlines():
    f = line.split()
    if len(f) == 4 and f[3] == "main":
        lo = int(f[0], 16); hi = lo + int(f[1], 16)
seen = 0
for line in open(trace, errors="replace"):
    if line.startswith("O3PipeView:fetch:"):
        p = line.split(":")
        if lo <= int(p[3], 16) < hi:
            seen += 1
            if seen >= skip:
                s = int(p[5]); print(f"{s}:{s + count}"); break
PY
)
    echo "$name: instruction range $range"
    python3 "$GEM5/util/o3-pipeview.py" -c 500 -w 60 --only_committed \
        -i "$range" -o "$out/pipeview.txt" /tmp/$name.trace
    python3 "$GEM5/util/o3-pipeview.py" -c 500 -w 60 \
        -i "$range" -o "$out/pipeview_with_squashed.txt" /tmp/$name.trace
    python3 scripts/latency.py /tmp/$name.trace --stats "$out/stats.txt" -o "$out/latency.json"
    head -c 20000000 /tmp/$name.trace > "$out/trace_head.out"     # first ~20 MB, for Konata
    rm -f /tmp/$name.trace
}

SKIP=5 trace hello_w1 --binary benchmarks/hello --width 1
trace intalu_ilp_w1 --binary benchmarks/intalu --args "0 20000" --width 1
trace intalu_dep_w1 --binary benchmarks/intalu --args "1 20000" --width 1
trace intalu_ilp_w4 --binary benchmarks/intalu --args "0 20000" --width 4
COUNT=60 SKIP=20000 trace br_random_w4_static --binary benchmarks/branchy --args "1 2048 4" --width 4 --bp static-nt
COUNT=60 SKIP=20000 trace br_random_w4_ltage  --binary benchmarks/branchy --args "1 2048 4" --width 4 --bp ltage
