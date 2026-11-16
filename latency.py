#!/usr/bin/env python3
"""latency.py - per-instruction latency from a gem5 O3PipeView trace.

gem5 prints one block per dynamic micro-op:
  O3PipeView:fetch:<tick>:<pc>:<upc>:<seq>:<disasm>
  O3PipeView:decode:<tick>   (then rename, dispatch, issue, complete)
  O3PipeView:retire:<tick>:store:<tick>
A tick of 0 means the micro-op never reached that stage (it was squashed).

Reports, over committed micro-ops: mean fetch->retire latency in cycles, the
mean time between each pair of stages, and how many fetched micro-ops were
squashed (wrong-path work thrown away after a misprediction).

  python3 scripts/latency.py trace.out --stats results/x/stats.txt -o latency.json
"""
import argparse
import json
import statistics

STAGES = ["fetch", "decode", "rename", "dispatch", "issue", "complete", "retire"]

ap = argparse.ArgumentParser()
ap.add_argument("trace")
ap.add_argument("--stats", help="stats.txt of the same run (reads the clock period)")
ap.add_argument("--cycle", type=int, default=None, help="ticks per cycle (default: from stats, else 500)")
ap.add_argument("-o", "--out")
a = ap.parse_args()

cycle = a.cycle
if cycle is None and a.stats:
    for line in open(a.stats):
        if line.startswith("system.clk_domain.clock"):
            cycle = int(float(line.split()[1]))
            break
cycle = cycle or 500

committed, squashed = [], 0
cur = None
with open(a.trace, errors="replace") as f:
    for line in f:
        if not line.startswith("O3PipeView:"):
            continue
        parts = line.rstrip("\n").split(":")
        stage = parts[1]
        if stage == "fetch":
            cur = {"fetch": int(parts[2])}
        elif cur is not None and stage in STAGES:
            cur[stage] = int(parts[2])
            if stage == "retire":
                if all(cur.get(s, 0) > 0 for s in STAGES):
                    committed.append(cur)
                else:
                    squashed += 1
                cur = None

if not committed:
    raise SystemExit("no committed instructions found in trace")

lat = sorted((c["retire"] - c["fetch"]) / cycle for c in committed)
gaps = {f"{s0}->{s1}": statistics.fmean((c[s1] - c[s0]) / cycle for c in committed)
        for s0, s1 in zip(STAGES, STAGES[1:])}
span = (max(c["retire"] for c in committed) - min(c["fetch"] for c in committed)) / cycle
res = {
    "cycle_ticks": cycle,
    "committed_uops": len(committed),
    "squashed_uops": squashed,
    "squash_fraction": squashed / (squashed + len(committed)),
    "latency_mean_cycles": statistics.fmean(lat),
    "latency_median_cycles": statistics.median(lat),
    "latency_p90_cycles": lat[int(0.9 * len(lat))],
    "stage_gap_mean_cycles": gaps,
    "uops_per_cycle": len(committed) / span if span else None,
}
print(json.dumps(res, indent=2))
if a.out:
    with open(a.out, "w") as f:
        json.dump(res, f, indent=2)
