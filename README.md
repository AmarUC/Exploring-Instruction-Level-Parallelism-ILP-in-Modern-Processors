# Instruction-Level Parallelism in gem5

Part 2 of the ILP assignment: pipelining, branch prediction, multiple issue and SMT experiments on an x86 out-of-order core in gem5 v23.0. The report for both parts is in `report/`.

```
configs/ilp.py               x86 SE-mode system: O3 or Minor CPU, L1I/L1D/L2, DDR3.
                             --width, --bp, --cpu, --smt-fetch, repeat --binary for SMT
benchmarks/hello.c           Hello World check
benchmarks/intalu.c          integer ALU: 4 independent chains (0) vs 1 dependent chain (1)
benchmarks/fpu.c             floating point: DAXPY + dot product
benchmarks/memory.c          sequential stream (0) vs random pointer chase (1)
benchmarks/branchy.c         data-dependent branch on sorted (0) vs random (1) data
scripts/run_experiments.sh   every run, in sections: hello pipeline bp width smt latency
scripts/latency.py           O3PipeView trace -> mean fetch-to-retire latency + stage breakdown
scripts/parse_stats.py       results/<section>/<run>/stats.txt -> results/<section>.csv
scripts/plot_results.py      CSVs -> results/plots/*.png
report/                      Part 1 literature review, Part 2 report
screenshots/                 terminal and viewer screenshots for the report
```

## 1. Requirements

gem5 v23.0 built for X86 (`build/X86/gem5.opt`) on Ubuntu 22.04/24.04 (WSL2 works), gcc, Python 3 with matplotlib.

```bash
sudo apt install -y build-essential scons python3-dev git zlib1g-dev libprotobuf-dev \
    protobuf-compiler libgoogle-perftools-dev libboost-all-dev libhdf5-serial-dev \
    python3-pydot m4 libpng-dev libelf-dev pkg-config python3-matplotlib
git clone https://github.com/gem5/gem5.git ~/gem5 && cd ~/gem5
git checkout v23.0.0.1
scons build/X86/gem5.opt -j"$(nproc)"      # 30-90 min, ~8 GB RAM
```

## 2. Build the benchmarks and run Hello World

```bash
make -C benchmarks                          # static binaries (SE mode needs -static)
~/gem5/build/X86/gem5.opt --outdir=results/hello/o3 configs/ilp.py --binary benchmarks/hello --width 1
```

Expected output ends with:

```
Beginning simulation
Hello world!
Exiting @ tick ... because exiting with last active thread context
```

## 3. Run the experiments

```bash
GEM5=~/gem5 JOBS=6 ./scripts/run_experiments.sh            # everything (~1-2 h with 6 parallel jobs)
GEM5=~/gem5 ./scripts/run_experiments.sh bp                # or one section
python3 scripts/parse_stats.py                             # -> results/*.csv
python3 scripts/plot_results.py                            # -> results/plots/*.png
```

Single runs:

```bash
G=~/gem5/build/X86/gem5.opt
$G --outdir=results/x configs/ilp.py --binary benchmarks/branchy --args "1 8192 20" --width 1 --bp static-nt
$G --outdir=results/x configs/ilp.py --binary benchmarks/branchy --args "1 8192 20" --width 1 --bp ltage
$G --outdir=results/x configs/ilp.py --binary benchmarks/intalu --args "0 600000" --width 8
# SMT: one --binary per hardware thread
$G --outdir=results/x configs/ilp.py --width 4 \
   --binary benchmarks/intalu --args "0 600000" --binary benchmarks/memory --args "1 2048 1"
```

## 4. Pipeline visualisation

```bash
$G --debug-flags=O3PipeView --debug-file=trace.out --outdir=results/trace \
   configs/ilp.py --binary benchmarks/hello --width 1
python3 ~/gem5/util/o3-pipeview.py -c 500 -o results/trace/pipeview.txt --color \
   -i 1000:1100 results/trace/trace.out
less -r results/trace/pipeview.txt
python3 scripts/latency.py results/trace/trace.out --stats results/trace/stats.txt
```

`-c 500` is the cycle time in ticks at 2 GHz. The same `trace.out` opens in the Konata viewer (https://github.com/shioyadan/Konata) for a graphical view.

## 5. Issues found and fixed

| Symptom | Cause | Fix in `configs/ilp.py` |
|---|---|---|
| `Assertion 'system->multiThread \|\| numThreads == 1' failed` | SMT needs the system flag | `system.multi_thread = True` |
| SMT run never finishes; 0 instructions committed, `rename.blockCycles` = all cycles | x86 needs one physical matrix register per thread; default `numPhysMatRegs = 2` leaves the free list empty with 2 threads, so rename blocks forever | `numPhysMatRegs = 2 * threads` |
| `timebuf.hh:54: Assertion 'idx >= -past && idx <= future' failed` at width 1 | Writeback slots overflow the 5-entry O3 time buffer | `forwardComSize = backComSize = 32` for width <= 2 |
| `se.py --smt` fails: `assert args.cpu_type == "DerivO3CPU"`, then `Int port not connected` | gem5's deprecated se.py wires only one x86 interrupt controller | Own config wires every thread's interrupt controller |
| No branch prediction "off" switch in gem5 | All CPU models predict | `--bp static-nt`: 1-bit, 2-entry predictor + 2-entry BTB, so taken branches are effectively predicted not-taken |
