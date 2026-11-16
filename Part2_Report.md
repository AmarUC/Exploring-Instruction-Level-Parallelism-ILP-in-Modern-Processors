# Practical Exploration of Instruction-Level Parallelism in gem5

*Part 2: Simulation Report*

**GitHub repository:** `https://github.com/AmarUC/Exploring-Instruction-Level-Parallelism-ILP-in-Modern-Processors`

---

## 1. Environment and Method

| Item | Value |
|---|---|
| Simulator | gem5 v23.0.0.1, `build/X86/gem5.opt` |
| Host | Ubuntu 24.04 under WSL2 on Windows 11 |
| ISA / mode | x86-64, syscall-emulation (SE) mode, statically linked binaries (gcc 13.3, `-O2 -static`) |
| CPU models | `X86O3CPU` (out-of-order, configurable width) and `X86MinorCPU` (in-order) |
| Clock | 2 GHz (1 cycle = 500 ticks) |
| Caches | L1I 32 kB 2-way, L1D 64 kB 2-way (2-cycle), L2 2 MB 8-way (20-cycle), DDR3-1600 |
| Configuration file | `configs/ilp.py` (one script, every ILP parameter set on the command line) |

All runs come from `scripts/run_experiments.sh`. `scripts/parse_stats.py` gathers `stats.txt` from every run into CSV files, and `scripts/plot_results.py` draws the charts. Throughput is **IPC**, committed x86 instructions per cycle (`system.cpu.ipc`). gem5 has no per-instruction latency statistic, so **latency** is measured from an `O3PipeView` trace by `scripts/latency.py`: the mean number of cycles from fetch to retire over all committed micro-ops, split by pipeline stage.

### Workloads

Each benchmark comes in pairs that run the same code and change one property, so differences in IPC can be traced to a single cause.

| Name | Program | What it stresses |
|---|---|---|
| `hello` | `hello.c` | Hello World check |
| `intalu_ilp` | `intalu 0 600000` | 4 independent integer chains: plenty of ILP |
| `intalu_dep` | `intalu 1 600000` | Same operations as one dependent chain: little ILP |
| `fpu` | `fpu 4096 40` | Floating-point DAXPY and dot product (multi-cycle FP latency) |
| `mem_stream` | `memory 0 2048 2` | Sequential sum over 2 MB (cache misses, but independent) |
| `mem_chase` | `memory 1 2048 1` | Random pointer chase over 2 MB (each load waits for the previous one) |
| `br_sorted` | `branchy 0 8192 20` | `if (v[i] >= 128)` on sorted data: predictable branch |
| `br_random` | `branchy 1 8192 20` | Same branch on random data |

`branchy.c` is compiled with `-fno-if-conversion` so that gcc keeps a real conditional branch rather than turning it into a `cmov`.

---

## 2. Basic Pipeline Simulation

### 2.1 Configuration

gem5 does not ship a textbook 5-stage pipeline, so two models are used:

- **`X86O3CPU` with every width set to 1** (`--width 1`): fetch, decode, rename, dispatch, issue, execute, writeback and commit each handle one micro-op per cycle. Mapped onto the classic stages: **IF** = fetch; **ID** = decode and rename; **EX** = dispatch, issue and execute; **MEM** = the load/store queue inside execute; **WB** = writeback and commit. This model supports the pipeline viewer.
- **`X86MinorCPU`** (`--cpu minor`): an in-order pipeline with stages Fetch1, Fetch2, Decode and Execute. Memory access happens inside Execute.

```python
# configs/ilp.py (excerpt)
cpu = X86O3CPU(numThreads=nthreads)
for param in ("fetchWidth", "decodeWidth", "renameWidth", "dispatchWidth",
              "issueWidth", "wbWidth", "commitWidth", "squashWidth"):
    setattr(cpu, param, w)
cpu.numROBEntries = opts.rob or min(192, 32 * w)
cpu.numIQEntries  = opts.iq  or min(64, 16 * w)
cpu.branchPred    = branch_predictor(opts.bp)
```

### 2.2 Hello World

```
$ ~/gem5/build/X86/gem5.opt --outdir=results/hello/o3 configs/ilp.py --binary benchmarks/hello --width 1
...
Beginning simulation
Hello world!
Exiting @ tick 209138000 because exiting with last active thread context
```

| CPU | Instructions | Cycles | IPC |
|---|---|---|---|
| O3, width 1 | 130,273 | 418,276 | 0.311 |
| MinorCPU | 130,291 | 512,396 | 0.254 |

*[Screenshot 3: Hello World run]*

### 2.3 Cycle-by-Cycle Behaviour

The trace is captured with `--debug-flags=O3PipeView` and turned into a timeline by `util/o3-pipeview.py`. `scripts/pipeview_demo.sh` automatically picks a window inside `main`'s loop. Each row is one micro-op, and each character is one cycle: **f** fetch, **d** decode, **n** rename, **p** dispatch, **i** issue, **c** complete, **r** retire.

**Scalar pipeline, integer loop** (`results/trace/intalu_ilp_w1/pipeview.txt`):

```
[....fdn.ic.r.......]  0x004017c3.1 JNZ_I
[.....fdn.ic.r......]  0x004017c3.2 JNZ_I
[.......fdn.ic.r....]  0x00401790.0 MOV_R_R
[........fdn.ic.r...]  0x00401793.0 XOR_R_R
[.........fdn.ic.r..]  0x00401796.0 LEA_R_M
[..........fdn.ic.r.]  0x0040179a.0 MOV_R_R
```

What this shows:

- **One micro-op enters each stage per cycle**, so each row starts one cycle after the one above. That is the pipeline overlap: at any moment about 8 micro-ops are in different stages.
- **Fetch to retire is 8 cycles** in steady state (`fdn.ic.r`), the minimum depth of this pipeline.
- **The taken loop branch (`JNZ`) costs one fetch bubble**: there is a one-cycle gap before `MOV_R_R`, the first instruction of the next iteration. The BTB supplies the target, but redirecting fetch takes a cycle.

**4-wide pipeline, same loop** (`results/trace/intalu_ilp_w4/pipeview.txt`):

```
[........fdn.pic..r..]  0x0040179d.0 SHR_R_I
[........fdn.p.ic.r..]  0x004017a1.0 XOR_R_R
[........fdn.p..ic.r.]  0x004017a4.0 ADD_R_R
[........fdn.p..ic.r.]  0x004017a7.0 LEA_R_M
[.........fdn.p..ic.r]  0x004017ab.0 SAL_R_I
[.........fdn.p...ic.r] 0x004017af.0 XOR_R_R
```

**Groups of four micro-ops** are fetched, decoded and renamed in the same cycle. The gaps between `p` (dispatch) and `i` (issue) are dependences: a micro-op waits in the issue queue until its producer completes.

**Mispredicted path** (`results/trace/br_random_w4_static/pipeview_with_squashed.txt`, static not-taken predictor):

```
[....f..dn.pic.r....]  0x004017a0.2 CALL_NEAR_I
[=====f=============]  0x004017a5.0 -----ADD_R_I        <- fetched down the wrong path
[=====f=============]  0x004017a9.0 -----CQO_R_R           and squashed (never retires)
...
[.........fdn.ic.r..]  0x00405850.0 HINT_NOP            <- correct target, fetched later
```

The front end keeps fetching the fall-through instructions after the `CALL`. When the call resolves, those micro-ops are **squashed** (the `=` rows) and fetch restarts at the target. That wasted work is what branch prediction exists to avoid.

### 2.4 Visualisation

*[Screenshot 5: `o3-pipeview.py` timelines above, and optionally the same trace in the Konata viewer]*

---

## 3. Performance Metrics: Throughput and Latency

### 3.1 Throughput (IPC) on Single-Issue Pipelines

![Single-issue pipelines](../results/plots/pipeline_ipc.png)

| Workload | MinorCPU IPC | O3 width-1 IPC | L1D miss rate (O3) |
|---|---|---|---|
| int, 4 chains | 0.665 | 0.747 | 4.6% |
| int, 1 chain | 0.679 | 0.714 | 4.6% |
| FP daxpy | 0.267 | 0.520 | 2.7% |
| memory stream | 0.186 | 0.300 | 32.3% |
| pointer chase | 0.194 | 0.285 | 6.5% |
| branch sorted | 0.336 | 0.433 | 0.2% |
| branch random | 0.353 | 0.352 | 0.5% |

Patterns:

- **No single-issue machine reaches IPC 1.** Micro-op expansion (an x86 instruction averages about 1.4–2 micro-ops here), taken-branch bubbles, cache misses and multi-cycle operations all add cycles.
- **Out-of-order execution helps even at width 1**, by up to 2× on FP code (0.267 → 0.520). The in-order MinorCPU stalls behind every 4-cycle FP operation, while O3 keeps executing independent micro-ops around it. On integer code the gain is small, because most operations take 1 cycle and there is little latency to hide.
- **Memory-bound code is slowest.** Both memory workloads stay below 0.30 IPC. The stream's 32% miss rate is the 2 MB array not fitting in L1.

### 3.2 Latency

![Latency breakdown](../results/plots/latency_breakdown.png)

| Run (trace, smaller inputs) | Mean latency (cycles) | Median | 90th percentile | Squashed fraction | IPC |
|---|---|---|---|---|---|
| width 1, int 4 chains | 16.4 | 7 | 44 | 0.7% | 0.64 |
| width 4, int 4 chains | 22.0 | 10 | 33 | 1.9% | 1.64 |
| width 8, int 4 chains | 49.9 | 41 | 44 | 2.7% | 1.87 |
| width 1, pointer chase | 75.1 | 75 | 92 | 9.1% | 0.29 |
| width 4, pointer chase | 113.0 | 104 | 138 | 24.2% | 0.41 |
| width 8, pointer chase | 126.2 | 108 | 149 | 27.0% | 0.43 |
| width 1, static NT, branch random | 22.9 | 12 | 40 | 29.4% | 0.29 |
| width 1, tournament, branch random | 58.8 | 67 | 81 | 6.4% | 0.35 |

Patterns:

- **Higher throughput comes with *higher* latency.** As width grows from 1 to 8, integer IPC nearly triples, but mean latency also triples (16 → 50 cycles). Little's law explains it: instructions in flight = IPC × latency. A wider core keeps far more instructions in its 192-entry ROB, and each one waits longer for its turn to issue and retire.
- **Most latency is waiting, not computing.** In every bar, the execute segment (issue→complete) is 1–2 cycles. The time goes to *dispatch→issue* (waiting for operands) and *complete→retire* (waiting for older instructions to commit in order). For the pointer chase, the long fetch→decode segment is the front end stalled because the ROB and load queue are full behind a cache miss.
- **A better branch predictor raised latency.** With static not-taken, the core keeps squashing its window, so few instructions are ever in flight and each one finishes quickly (22.9 cycles), but IPC is lower. Latency on its own is therefore a misleading metric for an out-of-order core: throughput has to be reported alongside it.

The trace runs use smaller inputs, since traces cost about 500 bytes per micro-op, so start-up code makes up a larger share. That explains why their IPC differs slightly from the full runs.

---

## 4. Impact of Branch Prediction

### 4.1 Configuration

gem5 has no switch to turn branch prediction off: every CPU model predicts. The "no prediction" baseline (`--bp static-nt`) is a `LocalBP` that can never learn "taken": 2 entries with 1-bit counters, a 2-entry BTB and a 1-entry return stack. Without a BTB hit, fetch continues at the fall-through address, so almost every taken branch behaves as **predict not-taken** and is fixed when it executes. It is compared with three dynamic predictors that ship with gem5:

```python
def branch_predictor(name):
    if name == "static-nt":
        return LocalBP(localPredictorSize=2, localCtrBits=1, BTBEntries=2,
                       RASSize=1, indirectBranchPred=NULL)
    if name == "local":      return LocalBP()        # 2K 2-bit counters by PC
    if name == "tournament": return TournamentBP()   # local + global + chooser
    if name == "ltage":      return LTAGE()          # TAGE + loop predictor
```

### 4.2 Results

![Branch prediction, scalar](../results/plots/bp_w1.png)
![Branch prediction, 4-wide](../results/plots/bp_w4.png)

| Workload | Width | Static NT IPC (mispredict %) | Local | Tournament | LTAGE |
|---|---|---|---|---|---|
| branch sorted | 1 | 0.329 (48.4%) | 0.421 (10.8%) | 0.433 (7.4%) | 0.436 (6.4%) |
| branch random | 1 | 0.310 (29.1%) | 0.339 (16.9%) | 0.352 (14.0%) | 0.399 (2.7%) |
| int, 4 chains | 1 | 0.742 (2.1%) | 0.747 (0.2%) | 0.747 (0.2%) | 0.747 (0.2%) |
| pointer chase | 1 | 0.240 (48.8%) | 0.279 (5.8%) | 0.285 (3.6%) | 0.286 (3.1%) |
| branch sorted | 4 | 0.455 (37.1%) | 0.915 (9.8%) | 0.971 (6.9%) | 0.986 (6.1%) |
| branch random | 4 | 0.462 (16.8%) | 0.585 (10.3%) | 0.633 (9.6%) | 0.857 (2.4%) |
| int, 4 chains | 4 | 2.134 (2.3%) | 2.188 (0.2%) | 2.188 (0.2%) | 2.188 (0.2%) |
| pointer chase | 4 | 0.279 (17.7%) | 0.374 (4.0%) | 0.392 (2.8%) | 0.396 (2.5%) |

Mispredict rates cover every conditional branch in the program, start-up code included.

| Extra statistic (branch sorted, 4-wide) | Static NT | Tournament |
|---|---|---|
| Branches mispredicted at commit | 407,215 | 50,907 |
| Micro-ops fetched per instruction committed | 2.80 | 1.16 |
| BTB hit ratio | 29% | 99.8% |

### 4.3 Analysis

- **Prediction matters more the wider the machine.** On the scalar core, going from static to tournament raises `br_sorted` IPC by 32% (0.329 → 0.433). On the 4-wide core it raises it by 113% (0.455 → 0.971). Each misprediction throws away everything fetched since the branch, roughly pipeline depth × width slots. With static NT, the 4-wide core fetched 2.8 micro-ops for every instruction it committed, so about two thirds of its front-end work was wasted.
- **Static NT fails even on easy code.** Every loop back-edge is a taken branch, so a not-taken predictor mispredicts once per iteration. Sorted data is perfectly predictable for any dynamic predictor, yet static NT still mispredicts 48% of conditional branches there.
- **Code without hard branches barely notices.** `intalu` has one well-behaved loop branch per iteration. All dynamic predictors reach 0.2%, and even static NT loses only 2.5% of IPC, because the loop body is long relative to the one bad branch.
- **History length matters for "random" data.** `br_random` repeats the same 8,192 random values 20 times. Local (by PC) and tournament (12-bit history) predictors cannot learn the pattern (10–17% mispredicts). LTAGE's geometric histories, hundreds of branches long, effectively memorise the repeating sequence and reach 2.4%, giving 35% more IPC than tournament at width 4. On truly fresh random data, no predictor could beat 50% on that branch.
- **Why accurate prediction is crucial:** an out-of-order core builds its ILP from a window of speculatively fetched instructions. Each misprediction drains that window, and refilling it takes the full front-end depth. The deeper and wider the pipeline, the more each misprediction costs, so ILP from width cannot be realised without prediction accuracy close to 100%.

---

## 5. Multiple Issue (Superscalar)

### 5.1 Configuration

`--width N` sets every O3 stage width to N, and the window grows with it (ROB = min(192, 32N), IQ = min(64, 16N), LQ/SQ = min(32, 8N)), so wider machines are not starved by a tiny window. The tournament predictor is used for all width runs.

### 5.2 Results

![IPC vs width](../results/plots/width_ipc.png)
![Speedup vs width](../results/plots/width_speedup.png)

| Workload | Width 1 | Width 2 | Width 4 | Width 8 | Speedup 8 vs 1 |
|---|---|---|---|---|---|
| int, 4 chains | 0.747 | 1.296 | 2.188 | 2.544 | 3.41× |
| int, 1 chain | 0.714 | 1.296 | 1.558 | 1.564 | 2.19× |
| FP daxpy | 0.520 | 0.934 | 1.333 | 1.497 | 2.88× |
| memory stream | 0.300 | 0.387 | 0.461 | 0.492 | 1.64× |
| pointer chase | 0.285 | 0.371 | 0.392 | 0.410 | 1.44× |
| branch sorted | 0.433 | 0.700 | 0.971 | 1.189 | 2.75× |
| branch random | 0.352 | 0.516 | 0.633 | 0.693 | 1.97× |

| Stall statistic at width 8 | int 4 chains | int 1 chain | pointer chase |
|---|---|---|---|
| Issue rate (micro-ops/cycle) | 3.05 | 1.87 | 1.08 |
| Rename stalls: IQ full | 1.51 M | 3.99 M | 9.40 M |
| Rename stalls: SQ full | 7,979 | 7,979 | 4.63 M |

### 5.3 Analysis

- **Superscalar shines on independent work.** `intalu_ilp` (4 independent chains) and FP DAXPY (independent loop iterations) scale best: 3.4× and 2.9× at width 8. `br_sorted` also scales well (2.75×) once its branch is predicted.
- **Dependences cap the gain.** `intalu_dep` matches `intalu_ilp` at width 1 and 2, then flattens at IPC ≈ 1.56. With one serial chain, width beyond about 2 has nothing to issue: the issue queue fills with micro-ops waiting on the chain (3.99 M IQ-full stalls) while issue slots go unused.
- **Memory-bound code hardly benefits.** The pointer chase gains only 1.44× at width 8: each load needs the previous load's value, so a wider core just fills its queues faster and waits (9.4 M IQ-full and 4.6 M SQ-full stalls). The stream gains a bit more (1.64×) because its misses are independent and can overlap (memory-level parallelism).
- **Returns shrink at every width.** No workload doubles from 4 to 8 (best: +23% for `br_sorted`), even though 8-wide hardware costs far more. This matches Wall's (1991) limits and Palacharla et al.'s (1997) complexity argument.

---

## 6. Simultaneous Multithreading

### 6.1 Configuration

Giving `--binary` twice creates a 2-thread O3 core: two separate processes share the fetch, decode, rename, issue, execute and commit stages, the functional units, the caches and the branch predictor.

```python
cpu = X86O3CPU(numThreads=2)
system.multi_thread = True
cpu.smtFetchPolicy = "RoundRobin"        # also tested: IQCount, LSQCount
cpu.smtNumFetchingThreads = 1
cpu.smtROBPolicy = cpu.smtIQPolicy = cpu.smtLSQPolicy = "Partitioned"
cpu.numPhysIntRegs = cpu.numPhysFloatRegs = 320   # shared physical register file
cpu.numPhysMatRegs = 4                             # see Troubleshooting #3
cpu.workload = [proc_a, proc_b]
```

**Partitioned** means each thread gets a fixed half of the ROB, issue queue and load/store queue. The physical register file, functional units, caches and predictor are shared freely.

**Measurement.** Each program is first run alone on the same core. Each pair is then simulated for 90% of the *shorter* program's solo time (`--max-ticks`). A thread on a shared core is never faster than alone, so both threads are active for the whole window. Two metrics are reported:

- **Total IPC**: instructions committed by both threads, divided by cycles.
- **Weighted speedup** (Snavely & Tullsen, 2000): Σ IPC<sub>SMT,i</sub> / IPC<sub>alone,i</sub>. A value of 1.0 means the pair does no better than running the programs one after another; 2.0 means each thread runs as fast as it would alone.

### 6.2 Results

![SMT weighted speedup](../results/plots/smt_speedup.png)
![SMT total IPC](../results/plots/smt_ipc.png)

| Pair (4-wide core) | Thread A IPC (alone) | Thread B IPC (alone) | Total IPC | Weighted speedup |
|---|---|---|---|---|
| int 1 chain + int 1 chain | 1.546 (1.558) | 1.477 (1.558) | 3.023 | **1.94** |
| int 4 chains + int 4 chains | 1.524 (2.188) | 1.524 (2.188) | 3.048 | **1.39** |
| FP daxpy + pointer chase | 0.589 (1.333) | 0.153 (0.392) | 0.742 | 0.83 |
| int 1 chain + pointer chase | 0.824 (1.558) | 0.023 (0.392) | 0.847 | 0.59 |
| int 4 chains + pointer chase | 0.818 (2.188) | 0.032 (0.392) | 0.850 | 0.46 |
| branch random + int 4 chains | 0.050 (0.633) | 0.804 (2.188) | 0.853 | 0.45 |
| int 4 chains + FP daxpy | 0.781 (2.188) | 0.084 (1.333) | 0.865 | 0.42 |

| Pair (8-wide core) | Total IPC | Weighted speedup |
|---|---|---|
| int 1 chain + int 1 chain | 3.115 | **1.99** |
| int 4 chains + int 4 chains | 4.790 | **1.88** |
| FP daxpy + pointer chase | 0.830 | 0.86 |
| int 4 chains + FP daxpy | 0.889 | 0.37 |

Fetch policy (int 4 chains + pointer chase, 4-wide): RoundRobin 0.850, IQCount 0.852, LSQCount 0.852 total IPC.

### 6.3 Resource Utilisation and Contention

| Statistic (4-wide) | int 4 chains + int 4 chains | int 4 chains + FP daxpy | FP daxpy alone |
|---|---|---|---|
| Cycles in window | 4,004,629 | 1,566,104 | 1,740,116 (whole run) |
| Rename blocked (thread-cycles) | 154,600 | **1,925,073** | 79,010 |
| Decode blocked (thread-cycles) | 182,197 | **2,363,285** | 471,155 |
| ROB-full stall events | 5,391 | **407,243** | 173,262 |
| Branch mispredicts at commit | 1,075 | 1,088 | n/a |
| L1I miss rate | 0.10% | 0.85% | n/a |

### 6.4 Analysis

- **SMT clearly pays off when one thread cannot fill the machine.** Two dependent-chain threads (`intalu_dep`) each run at 95–99% of their solo speed, a weighted speedup of 1.94–1.99. Alone, a single chain uses only 1.56 of 4 issue slots. The second thread fills the empty slots, so total IPC doubles to 3.0 with no extra execution hardware.
- **Threads that already use the core well gain less.** Two `intalu_ilp` threads, each able to reach IPC 2.19 alone, compete for the same 4 issue slots. Total IPC rises to 3.05, close to the width limit, but each thread slows to 70% of its solo speed (weighted speedup 1.39). On the 8-wide core there are spare slots again, and weighted speedup climbs to 1.88 with total IPC 4.79, the highest throughput in any experiment. **SMT and width reinforce each other**: SMT is how a very wide core gets enough independent instructions to use its width.
- **Contention point: the partitioned ROB, and the front end it blocks.** In every *mixed* pair, total IPC collapses to about 0.85 whatever the partner, and one thread nearly stops. The statistics in 6.3 show why. The slower thread (FP with 4-cycle operations, or the pointer chase with cache misses) fills its 64-entry half of the ROB, which caused 407,000 ROB-full stalls against 5,000 in the identical pair. Rename and decode then spend about 62% of thread-cycles blocked. In gem5's model that blocking holds back the shared front end for the other thread too, so the fast thread is held to about 0.8 IPC. It is not a branch or cache effect: mispredicts are identical and the L1I miss rate stays under 1%.
- **Changing fetch policy did not help**, because fetch is not where the bottleneck is. IQCount and LSQCount (variants of the ICOUNT idea from Tullsen et al., 1996) choose which thread fetches, but the stall happens later, at rename. Real SMT cores reduce this with per-thread front-end queues, dynamic rather than fixed partitions, and by stopping fetch for threads that miss in the cache. gem5 v23's `Dynamic` sharing option crashed in our tests (Troubleshooting #6), so it could not be evaluated. These mixed-pair numbers should therefore be read as a worst case for statically partitioned SMT, not as typical hardware behaviour.
- **Does SMT significantly improve throughput?** Yes, for well-matched threads: up to +94% IPC on the 4-wide core and up to +88% (4.79 vs 2.54) on the 8-wide core. It does not help, and can hurt badly, when a long-latency thread hogs a statically partitioned structure. How much SMT helps depends on how threads are paired and how shared resources are managed, which is why OS schedulers and fetch policies matter (Snavely & Tullsen, 2000).

---

## 7. Key Questions

**How do the techniques interact?**
- **Width multiplies the cost of mispredictions.** The same predictor change was worth +32% on the scalar core and +113% on the 4-wide core. Wide issue only pays off together with accurate prediction.
- **Width and window size go together.** A wide core needs a large ROB and IQ to find independent work, and that larger window raises per-instruction latency (Little's law).
- **SMT feeds on what width cannot use.** The slots a single thread leaves empty, because of dependence chains or cache misses, are exactly what a second thread fills.

**What are the limitations?** True data dependences (`intalu_dep` stops at 1.56 IPC), memory latency (pointer chase at 0.41 IPC even 8-wide), branches that are hard to predict, and, for SMT, contention for shared, partitioned structures. Under each limitation, adding hardware gives a falling return.

**How can complexity be balanced against benefit?** In these runs, most of the achievable gain arrives by width 4. Going from 4 to 8 adds at most 23%, while doubling rename, issue-queue and bypass hardware. The cheaper wins were a better predictor (up to +35% from LTAGE on `br_random`) and SMT, which reuses existing hardware. That supports the direction in Part 1: moderate width, accurate prediction and multithreading, rather than ever-wider single-thread cores.

---

## 8. Troubleshooting

Each issue below was hit during this work. The fixes are in `configs/ilp.py` and `scripts/`, with comments.

| # | Symptom | Diagnosis | Resolution |
|---|---|---|---|
| 1 | `se.py --smt` fails with `assert args.cpu_type == "DerivO3CPU"`, then `panic: Int port not connected to anything!` | gem5's deprecated `se.py` wires only the first thread's x86 interrupt controller | Wrote my own config that wires every thread's interrupt controller in a loop |
| 2 | SMT run aborts: `Assertion 'system->multiThread \|\| numThreads == 1' failed` | SMT requires a system-level flag | `system.multi_thread = True` |
| 3 | SMT run never ends; stats after a time limit show 0 instructions committed and `rename.blockCycles` equal to every cycle, with no "FullEvents" | Rename stalls if *any* register class has no free physical registers. x86 uses one dummy matrix register per thread, and gem5's default `numPhysMatRegs = 2` leaves none free with 2 threads. Found by reading `UnifiedRenameMap::numFreeEntries()` | `numPhysMatRegs = 2 × threads` |
| 4 | Width-1 runs abort: `timebuf.hh:54: Assertion 'idx >= -past && idx <= future' failed` | With a writeback width of 1, completing micro-ops are pushed into later writeback slots and overrun O3's 5-entry inter-stage time buffer | `forwardComSize = backComSize = 32` when width ≤ 2. Re-running a finished width-1 run gave **identical cycle counts** (5,423,536) with depth 5 and 32, so the fix adds capacity without changing timing |
| 5 | WSL (Ubuntu) froze and crashed during the latency runs | 8 trace analyses ran at once, and `latency.py` held every traced micro-op in memory (hundreds of MB each), exhausting WSL's 7.7 GB | `latency.py` now streams the trace and keeps only running totals; latency runs go two at a time |
| 6 | SMT pairs where one program is shorter showed SMT *slower* than running the programs one after the other (down to 0.46×) | ROB/IQ/LSQ are partitioned per thread and not given back when a thread exits: `intalu` paired with Hello World took 5.85 ms against 2.23 ms alone. `Dynamic` sharing segfaulted | SMT pairs are measured in a fixed window (90% of the shorter program's solo time) while both threads run, and reported as weighted speedup |
| 6b | Two SMT pairs aborted: `decode.cc:408: Assertion 'skidBuffer[tid].size() <= skidBufferMax'` (8-wide) and `cpu.cc:650: Assertion 'commit.rob->isEmpty(tid)'` in `CPU::removeThread` (when a thread exits) | gem5 v23 bugs on thread exit and in the SMT decode path | Both disappeared with the fixed-window measurement (no thread exits during the window); all 16 pair runs then completed |
| 7 | `fetch.cc:1500: panic: Branch Count Fetch policy unimplemented` | The `Branch` SMT fetch policy exists in gem5's parameters but not in its code | Dropped from the experiments; `IQCount` and `LSQCount` used instead |
| 8 | No way to disable branch prediction | All gem5 CPU models predict | `static-nt` approximation (Section 4.1), described as such |
| 9 | PowerShell → WSL commands failed (`-re: command not found`, quoting errors) | PowerShell expanded `$G` before bash saw it | Put command sequences in `.sh` files and ran them with `wsl bash script.sh` |
| 10 | `branchy` had no branch to predict at first check | gcc converts simple if/else into `cmov` at `-O2` | Compiled with `-fno-if-conversion -fno-if-conversion2`; checked with `objdump` (0 `cmov` in `main`) |

---

## 9. Screenshots

*(Insert in order.)*

1. gem5 version and build (`git describe --tags`, `ls build/X86/gem5.opt`)
2. Building the benchmarks (`make -C benchmarks`)
3. Hello World run in gem5
4. `configs/ilp.py`: options, branch predictor function, width/SMT section
5. Pipeline viewer output (scalar, 4-wide, squashed path)
6. Throughput and latency statistics (`stats.txt` grep, `latency.json`)
7. Branch-prediction comparison statistics
8. SMT run with both threads committing
9. Charts from `results/plots/`
10. Troubleshooting: README issue table and the time-buffer check
11. GitHub repository page

---

## References

Binkert, N., Beckmann, B., Black, G., Reinhardt, S. K., Saidi, A., Basu, A., Hestness, J., Hower, D. R., Krishna, T., Sardashti, S., Sen, R., Sewell, K., Shoaib, M., Vaish, N., Hill, M. D., & Wood, D. A. (2011). The gem5 simulator. *ACM SIGARCH Computer Architecture News, 39*(2), 1–7.

Hennessy, J. L., & Patterson, D. A. (2019). *Computer architecture: A quantitative approach* (6th ed.). Morgan Kaufmann.

Lowe-Power, J., Ahmad, A. M., Akram, A., Alian, M., Amslinger, R., Andreozzi, M., et al. (2020). *The gem5 simulator: Version 20.0+* (arXiv:2007.03152). arXiv.

Palacharla, S., Jouppi, N. P., & Smith, J. E. (1997). Complexity-effective superscalar processors. *Proceedings of the 24th Annual International Symposium on Computer Architecture*, 206–218.

Snavely, A., & Tullsen, D. M. (2000). Symbiotic jobscheduling for a simultaneous multithreaded processor. *Proceedings of the 9th International Conference on Architectural Support for Programming Languages and Operating Systems*, 234–244.

Tullsen, D. M., Eggers, S. J., & Levy, H. M. (1995). Simultaneous multithreading: Maximizing on-chip parallelism. *Proceedings of the 22nd Annual International Symposium on Computer Architecture*, 392–403.

Wall, D. W. (1991). Limits of instruction-level parallelism. *Proceedings of the 4th International Conference on Architectural Support for Programming Languages and Operating Systems*, 176–188.
