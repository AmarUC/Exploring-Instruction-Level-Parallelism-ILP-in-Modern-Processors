#!/usr/bin/env bash
# run_experiments.sh - every simulation for Part 2.
#   GEM5=~/gem5 ./scripts/run_experiments.sh                 # all sections
#   GEM5=~/gem5 ./scripts/run_experiments.sh bp smt          # only some
# Sections: hello pipeline bp width smt latency
# Results: results/<section>/<run>/{stats.txt,simout,run.json,...}
# Finished runs are skipped, so the script can be re-run after a failure.
set -u
cd "$(dirname "$0")/.."
GEM5=${GEM5:-$HOME/gem5}
SIM="$GEM5/build/X86/gem5.opt"
CFG=configs/ilp.py
B=benchmarks
JOBS=${JOBS:-$(( $(nproc) / 2 ))}          # simulations in parallel (each gem5 run uses one core)
TRACE_DIR=${TRACE_DIR:-/tmp/gem5-ilp-traces}

# Workloads: binary|args   (sizes chosen for roughly 1-6 M instructions each)
WL_intalu_ilp="intalu|0 600000"
WL_intalu_dep="intalu|1 600000"
WL_fpu="fpu|4096 40"
WL_mem_stream="memory|0 2048 2"
WL_mem_chase="memory|1 2048 1"
WL_br_sorted="branchy|0 8192 20"
WL_br_random="branchy|1 8192 20"
ALL_WL="intalu_ilp intalu_dep fpu mem_stream mem_chase br_sorted br_random"

wl_bin()  { local v="WL_$1"; echo "$B/${!v%%|*}"; }
wl_args() { local v="WL_$1"; echo "${!v#*|}"; }

pending=0
run() {   # run <outdir> <ilp.py options...>
    local out=$1; shift
    if [ -f "$out/stats.txt" ] && grep -q simInsts "$out/stats.txt"; then
        echo "skip  $out (done)"; return
    fi
    mkdir -p "$out"
    echo "start $out"
    ( "$SIM" -re --outdir="$out" "$CFG" "$@"; echo "done  $out rc=$?" ) &
    pending=$((pending + 1))
    if [ "$pending" -ge "$JOBS" ]; then wait -n; pending=$((pending - 1)); fi
}

hello() {
    run results/hello/o3    --binary $B/hello --width 1
    run results/hello/minor --binary $B/hello --cpu minor
}

# Basic pipeline: scalar O3 (width 1) and the in-order MinorCPU on every workload
pipeline() {
    for w in $ALL_WL; do
        run results/pipeline/o3w1_$w  --binary "$(wl_bin $w)" --args "$(wl_args $w)" --width 1 --bp tournament
        run results/pipeline/minor_$w --binary "$(wl_bin $w)" --args "$(wl_args $w)" --cpu minor --bp tournament
    done
}

# Branch prediction: same workloads, four predictors, scalar and 4-wide
bp() {
    for w in br_sorted br_random intalu_ilp fpu mem_chase; do
        for p in static-nt local tournament ltage; do
            run results/bp/w1_${p}_$w --binary "$(wl_bin $w)" --args "$(wl_args $w)" --width 1 --bp $p
            run results/bp/w4_${p}_$w --binary "$(wl_bin $w)" --args "$(wl_args $w)" --width 4 --bp $p
        done
    done
}

# Multiple issue: widths 1, 2, 4, 8 on every workload
width() {
    for w in $ALL_WL; do
        for n in 1 2 4 8; do
            run results/width/w${n}_$w --binary "$(wl_bin $w)" --args "$(wl_args $w)" --width $n --bp tournament
        done
    done
}

# SMT: each workload alone, then pairs sharing one core (4-wide and 8-wide)
smt() {
    for w in intalu_ilp intalu_dep fpu mem_chase br_random; do
        run results/smt/st4_$w --binary "$(wl_bin $w)" --args "$(wl_args $w)" --width 4
        run results/smt/st8_$w --binary "$(wl_bin $w)" --args "$(wl_args $w)" --width 8
    done
    pairs="intalu_ilp+intalu_ilp intalu_ilp+fpu intalu_ilp+mem_chase intalu_dep+mem_chase fpu+mem_chase br_random+intalu_ilp intalu_dep+intalu_dep"
    for pr in $pairs; do
        a=${pr%+*}; b=${pr#*+}
        for n in 4 8; do
            run results/smt/smt${n}_${a}+${b} --width $n \
                --binary "$(wl_bin $a)" --args "$(wl_args $a)" \
                --binary "$(wl_bin $b)" --args "$(wl_args $b)"
        done
    done
    # Fetch-policy comparison on one mixed pair (RoundRobin is the smt4_ run above)
    for pol in Branch IQCount LSQCount; do
        run results/smt/pol${pol}_intalu_ilp+mem_chase --width 4 --smt-fetch $pol \
            --binary "$(wl_bin intalu_ilp)" --args "$(wl_args intalu_ilp)" \
            --binary "$(wl_bin mem_chase)" --args "$(wl_args mem_chase)"
    done
}

# Instruction latency needs a per-instruction trace (O3PipeView). Traces are
# about 500 bytes per instruction, so these runs use smaller inputs; each trace
# is reduced to latency.json by scripts/latency.py and then deleted.
lat_run() {  # lat_run <name> <ilp.py options...>
    local name=$1; shift
    local out=results/latency/$name tr="$TRACE_DIR/$name.trace"
    if [ -f "$out/latency.json" ]; then echo "skip  $out (done)"; return; fi
    mkdir -p "$out"; echo "start $out"
    "$SIM" -re --debug-flags=O3PipeView --debug-file="$tr" --outdir="$out" "$CFG" "$@" \
        && python3 scripts/latency.py "$tr" --stats "$out/stats.txt" -o "$out/latency.json" > /dev/null
    rm -f "$tr"
    echo "done  $out"
}
latency() {
    mkdir -p "$TRACE_DIR"
    for p in static-nt tournament; do
        for w in 1 4; do
            lat_run w${w}_${p}_br_random --binary $B/branchy --args "1 4096 4" --width $w --bp $p &
            lat_run w${w}_${p}_br_sorted --binary $B/branchy --args "0 4096 4" --width $w --bp $p &
        done
        wait
    done
    for n in 1 2 4 8; do
        lat_run w${n}_tournament_intalu_ilp --binary $B/intalu --args "0 60000" --width $n &
        lat_run w${n}_tournament_mem_chase  --binary $B/memory --args "1 512 1" --width $n &
    done
    wait
}

sections=${*:-hello pipeline bp width smt latency}
for s in $sections; do "$s"; done
wait
echo "all runs finished"
