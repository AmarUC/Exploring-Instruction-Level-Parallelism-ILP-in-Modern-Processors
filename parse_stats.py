#!/usr/bin/env python3
"""parse_stats.py - collect every run under results/ into CSV files.

  python3 scripts/parse_stats.py            # writes results/<section>.csv and results/summary.md

Each run directory holds stats.txt (gem5) and run.json (written by ilp.py).
Throughput = committed instructions per cycle (IPC). Latency comes from
results/latency/*/latency.json (scripts/latency.py on an O3PipeView trace).
"""
import csv
import glob
import json
import os
import re

ROOT = os.path.join(os.path.dirname(__file__), "..", "results")

WANT = {
    "sim_insts": r"^simInsts\s",
    "sim_ops": r"^simOps\s",
    "sim_seconds": r"^simSeconds\s",
    "cycles": r"^system\.cpu\.numCycles\s",
    "ipc": r"^system\.cpu\.ipc\s",
    "cpi": r"^system\.cpu\.cpi\s",
    "t0_insts": r"^system\.cpu\.commitStats0\.numInsts\s",
    "t1_insts": r"^system\.cpu\.commitStats1\.numInsts\s",
    "cond_predicted": r"^system\.cpu\.branchPred\.condPredicted\s",
    "cond_incorrect": r"^system\.cpu\.branchPred\.condIncorrect\s",
    "btb_hit_ratio": r"^system\.cpu\.branchPred\.BTBHitRatio\s",
    "commit_mispredicts": r"^system\.cpu\.commit\.branchMispredicts\s",
    "commit_squashed": r"^system\.cpu\.commit\.commitSquashedInsts\s",
    "fetched_insts": r"^system\.cpu\.fetchStats0\.numInsts\s",
    "issue_rate": r"^system\.cpu\.issueRate\s",
    "commit_per_cycle_mean": r"^system\.cpu\.commit\.numCommittedDist::mean\s",
    "rob_full": r"^system\.cpu\.rename\.ROBFullEvents\s",
    "iq_full": r"^system\.cpu\.rename\.IQFullEvents\s",
    "lq_full": r"^system\.cpu\.rename\.LQFullEvents\s",
    "sq_full": r"^system\.cpu\.rename\.SQFullEvents\s",
    "reg_full": r"^system\.cpu\.rename\.fullRegistersEvents\s",
    "rename_block_cycles": r"^system\.cpu\.rename\.blockCycles\s",
    "fu_busy": r"^system\.cpu\.fuBusy::total\s",
    "fu_busy_rate": r"^system\.cpu\.fuBusyRate::total\s",
    "icache_miss_rate": r"^system\.cpu\.icache\.overallMissRate::total\s",
    "dcache_miss_rate": r"^system\.cpu\.dcache\.overallMissRate::total\s",
    "l2_miss_rate": r"^system\.l2cache\.overallMissRate::total\s",
    # MinorCPU names its committed-instruction stat differently
    "minor_insts": r"^system\.cpu\.thread_0\.numInsts\s",
}
PATTERNS = {k: re.compile(v) for k, v in WANT.items()}


def read_stats(path):
    out = {}
    with open(path) as f:
        for line in f:
            if line.startswith("---------- End"):
                break                       # first dump only
            for k, rx in PATTERNS.items():
                if k not in out and rx.match(line):
                    try:
                        out[k] = float(line.split()[1])
                    except ValueError:
                        out[k] = float("nan")
    return out


def run_row(d):
    stats = os.path.join(d, "stats.txt")
    if not os.path.exists(stats):
        return None
    row = {"section": os.path.basename(os.path.dirname(d)), "run": os.path.basename(d)}
    meta = os.path.join(d, "run.json")
    if os.path.exists(meta):
        m = json.load(open(meta))
        row.update(cpu=m.get("cpu"), width=m.get("width") if m.get("cpu") == "o3" else 1,
                   bp=m.get("bp"), threads=m.get("threads"), smt_fetch=m.get("smt_fetch"),
                   rob=m.get("rob"), iq=m.get("iq"),
                   workload=" + ".join(f"{os.path.basename(b)} {a or ''}".strip()
                                       for b, a in zip(m["binary"], m.get("args") or [""] * len(m["binary"]))))
    s = read_stats(stats)
    row.update(s)
    if s.get("cond_predicted"):
        row["mispredict_rate"] = s.get("cond_incorrect", 0) / s["cond_predicted"]
    if s.get("fetched_insts") and s.get("t0_insts"):
        row["fetched_per_committed"] = s["fetched_insts"] / s["t0_insts"]
    lat = os.path.join(d, "latency.json")
    if os.path.exists(lat):
        L = json.load(open(lat))
        row["latency_mean_cycles"] = L["latency_mean_cycles"]
        row["latency_median_cycles"] = L["latency_median_cycles"]
        row["latency_p90_cycles"] = L["latency_p90_cycles"]
        row["squash_fraction"] = L["squash_fraction"]
        for k, v in L["stage_gap_mean_cycles"].items():
            row["gap_" + k.replace("->", "_to_")] = v
    return row


def main():
    sections = {}
    for d in sorted(glob.glob(os.path.join(ROOT, "*", "*"))):
        if os.path.isdir(d):
            r = run_row(d)
            if r:
                sections.setdefault(r["section"], []).append(r)
    for sec, rows in sections.items():
        keys = []
        for r in rows:
            keys += [k for k in r if k not in keys]
        path = os.path.join(ROOT, f"{sec}.csv")
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)
        print(f"{path}: {len(rows)} runs")


if __name__ == "__main__":
    main()
