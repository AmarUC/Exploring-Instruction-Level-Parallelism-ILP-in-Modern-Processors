#!/usr/bin/env python3
"""plot_results.py - results/*.csv -> PNG charts in results/plots/.

  python3 scripts/parse_stats.py && python3 scripts/plot_results.py
"""
import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.join(os.path.dirname(__file__), "..", "results")
OUT = os.path.join(ROOT, "plots")
os.makedirs(OUT, exist_ok=True)

# Categorical slots (fixed order) and a one-hue sequential ramp for ordered values
CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SEQ = ["#b7d3f2", "#6fa5e6", "#2a78d6", "#14498a"]          # light -> dark blue
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"

plt.rcParams.update({
    "font.size": 10, "axes.edgecolor": INK2, "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False,
    "axes.spines.right": False, "axes.grid": True, "axes.grid.axis": "y",
    "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "legend.frameon": False, "figure.dpi": 150, "savefig.bbox": "tight",
})

WL_ORDER = ["intalu_ilp", "intalu_dep", "fpu", "mem_stream", "mem_chase", "br_sorted", "br_random"]
WL_LABEL = {"intalu_ilp": "int (4 chains)", "intalu_dep": "int (1 chain)", "fpu": "FP daxpy",
            "mem_stream": "mem stream", "mem_chase": "pointer chase",
            "br_sorted": "branch sorted", "br_random": "branch random"}


def load(name):
    p = os.path.join(ROOT, f"{name}.csv")
    if not os.path.exists(p):
        return []
    rows = list(csv.DictReader(open(p)))
    for r in rows:
        for k, v in list(r.items()):
            try:
                r[k] = float(v)
            except (TypeError, ValueError):
                pass
    return rows


def wl_of(run):
    for w in WL_ORDER:
        if run.endswith("_" + w):
            return w
    return None


def grouped_bars(ax, groups, series, values, colors, ylabel, fmt="{:.2f}"):
    n = len(series)
    bw = 0.8 / n
    for i, s in enumerate(series):
        xs = [g + (i - (n - 1) / 2) * bw for g in range(len(groups))]
        ys = [values.get((grp, s), 0) for grp in groups]
        bars = ax.bar(xs, ys, bw * 0.92, label=str(s), color=colors[i], edgecolor="white", linewidth=0.6)
        if n <= 4:
            for b, y in zip(bars, ys):
                if y:
                    ax.annotate(fmt.format(y), (b.get_x() + b.get_width() / 2, y), ha="center",
                                va="bottom", fontsize=6.5, color=INK2, xytext=(0, 1),
                                textcoords="offset points")
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels([WL_LABEL.get(g, g) for g in groups], rotation=20, ha="right")
    ax.set_ylabel(ylabel)


def save(fig, name):
    fig.savefig(os.path.join(OUT, name))
    plt.close(fig)
    print("wrote", os.path.join(OUT, name))


# ---- 1. Basic pipeline: scalar O3 vs in-order Minor
rows = load("pipeline")
if rows:
    vals = {}
    for r in rows:
        w = wl_of(r["run"])
        kind = "O3, width 1" if r["run"].startswith("o3w1") else "MinorCPU (in-order)"
        vals[(w, kind)] = r["ipc"] if r.get("ipc") != "" else r["minor_insts"] / r["cycles"]
    fig, ax = plt.subplots(figsize=(8, 3.6))
    grouped_bars(ax, WL_ORDER, ["MinorCPU (in-order)", "O3, width 1"], vals, CAT[:2], "IPC (instructions / cycle)")
    ax.set_title("Single-issue pipelines: throughput per workload", loc="left")
    ax.legend(ncol=2, loc="upper right")
    save(fig, "pipeline_ipc.png")

# ---- 2. Branch prediction
rows = load("bp")
if rows:
    preds = ["static-nt", "local", "tournament", "ltage"]
    wls = ["br_sorted", "br_random", "intalu_ilp", "fpu", "mem_chase"]
    for width in (1, 4):
        sub = [r for r in rows if r["run"].startswith(f"w{width}_")]
        ipc = {(wl_of(r["run"]), r["bp"]): r["ipc"] for r in sub}
        mis = {(wl_of(r["run"]), r["bp"]): 100 * r.get("mispredict_rate", 0) for r in sub}
        fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
        grouped_bars(axes[0], wls, preds, ipc, CAT[:4], "IPC")
        axes[0].set_title(f"Throughput by predictor ({width}-wide)", loc="left")
        grouped_bars(axes[1], wls, preds, mis, CAT[:4], "conditional mispredict rate (%)", fmt="{:.1f}")
        axes[1].set_title("Conditional-branch mispredict rate", loc="left")
        axes[0].legend(title="predictor", ncol=2, loc="upper right", fontsize=8)
        save(fig, f"bp_w{width}.png")

# ---- 3. Superscalar width sweep
rows = load("width")
if rows:
    vals = {(wl_of(r["run"]), int(r["width"])): r["ipc"] for r in rows}
    fig, ax = plt.subplots(figsize=(9, 3.8))
    grouped_bars(ax, WL_ORDER, [1, 2, 4, 8], vals, SEQ, "IPC", fmt="{:.2f}")
    ax.legend(title="issue width", ncol=4, loc="upper right")
    ax.set_title("Multiple issue: IPC vs pipeline width", loc="left")
    save(fig, "width_ipc.png")

    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    for i, w in enumerate(WL_ORDER):
        base = vals.get((w, 1))
        if not base:
            continue
        xs = [1, 2, 4, 8]
        ys = [vals.get((w, n), float("nan")) / base for n in xs]
        ax.plot(xs, ys, marker="o", markersize=5, linewidth=2, color=CAT[i], label=WL_LABEL[w])
        ax.annotate(WL_LABEL[w], (8, ys[-1]), xytext=(4, 0), textcoords="offset points",
                    va="center", fontsize=7, color=INK2)
    ax.plot([1, 8], [1, 8], linestyle=":", color=INK2, linewidth=1)
    ax.annotate("ideal (linear)", (4.2, 4.6), fontsize=7, color=INK2)
    ax.set_xscale("log", base=2)
    ax.set_xticks([1, 2, 4, 8]); ax.set_xticklabels(["1", "2", "4", "8"])
    ax.set_ylim(0.8, 5)
    ax.set_xlabel("issue width"); ax.set_ylabel("speedup over width 1")
    ax.set_title("Speedup from wider issue", loc="left")
    ax.legend(fontsize=7, loc="upper left")
    save(fig, "width_speedup.png")

# ---- 4. SMT
rows = load("smt")
if rows:
    st = {}
    for r in rows:
        if r["run"].startswith("st"):
            n = int(r["run"][2]); w = r["run"].split("_", 1)[1]
            st[(n, w)] = r["sim_seconds"]
    labels, speedup, ipcs = [], {}, {}
    for r in rows:
        if not r["run"].startswith("smt"):
            continue
        n = int(r["run"][3]); pair = r["run"].split("_", 1)[1]
        a, b = pair.split("+")
        if (n, a) in st and (n, b) in st:
            lab = f"{WL_LABEL[a]} +\n{WL_LABEL[b]}"
            if lab not in labels:
                labels.append(lab)
            # Throughput gain: time to run A then B on one core / time to run A and B together
            speedup[(lab, f"{n}-wide")] = (st[(n, a)] + st[(n, b)]) / r["sim_seconds"]
            ipcs[(lab, f"{n}-wide")] = r["ipc"]
    if labels:
        fig, ax = plt.subplots(figsize=(10, 3.8))
        WL_LABEL.update({l: l for l in labels})
        grouped_bars(ax, labels, ["4-wide", "8-wide"], speedup, [SEQ[1], SEQ[3]], "throughput speedup vs running back-to-back")
        ax.axhline(1.0, color=INK2, linewidth=1, linestyle=":")
        ax.set_title("SMT (2 threads): combined throughput gain", loc="left")
        ax.legend(ncol=2, loc="upper right")
        ax.tick_params(axis="x", labelsize=7.5)
        save(fig, "smt_speedup.png")

# ---- 5. Latency
rows = load("latency")
if rows:
    rows = [r for r in rows if r.get("latency_mean_cycles") not in (None, "")]
    gaps = ["gap_fetch_to_decode", "gap_decode_to_rename", "gap_rename_to_dispatch",
            "gap_dispatch_to_issue", "gap_issue_to_complete", "gap_complete_to_retire"]
    names = ["fetch→decode", "decode→rename", "rename→dispatch", "dispatch→issue (wait)",
             "issue→complete (execute)", "complete→retire (commit wait)"]
    fig, ax = plt.subplots(figsize=(9, 0.45 * len(rows) + 1.2))
    left = [0] * len(rows)
    for i, (g, nm) in enumerate(zip(gaps, names)):
        vals = [r.get(g, 0) or 0 for r in rows]
        ax.barh(range(len(rows)), vals, left=left, color=CAT[i], label=nm, edgecolor="white", linewidth=1)
        left = [l + v for l, v in zip(left, vals)]
    for y, r in enumerate(rows):
        ax.annotate(f"{r['latency_mean_cycles']:.1f}", (left[y], y), xytext=(3, 0),
                    textcoords="offset points", va="center", fontsize=7, color=INK2)
    ax.set_yticks(range(len(rows))); ax.set_yticklabels([r["run"] for r in rows], fontsize=7)
    ax.invert_yaxis()
    ax.grid(axis="x", color=GRID); ax.grid(axis="y", visible=False)
    ax.set_xlabel("mean cycles from fetch to retire (committed micro-ops)")
    ax.set_title("Instruction latency broken down by pipeline stage", loc="left")
    ax.legend(fontsize=7, ncol=3, loc="lower center", bbox_to_anchor=(0.5, 1.06))
    save(fig, "latency_breakdown.png")
