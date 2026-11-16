# ilp.py - x86 SE-mode system for the ILP assignment (gem5 v23.0).
#
# One detailed CPU (O3 or Minor) with L1I/L1D/L2 caches and DDR3 memory.
# Every ILP knob the assignment varies is a command-line option:
#   --width       fetch/decode/rename/dispatch/issue/writeback/commit width
#                 (1 = scalar pipeline, 2/4/8 = superscalar)
#   --bp          branch predictor (static-nt approximates "no prediction")
#   --binary      one binary per hardware thread; 2+ binaries = SMT
#
# Usage (gem5 v23.0 X86 build):
#   ~/gem5/build/X86/gem5.opt --outdir=results/x configs/ilp.py \
#       --binary benchmarks/intalu --width 1 --bp local
#   # SMT: two threads on one core
#   ~/gem5/build/X86/gem5.opt --outdir=results/smt configs/ilp.py \
#       --binary benchmarks/intalu --binary benchmarks/fpu --width 4
#   # Pipeline trace for o3-pipeview.py / Konata
#   ~/gem5/build/X86/gem5.opt --debug-flags=O3PipeView --debug-file=trace.out \
#       --outdir=results/trace configs/ilp.py --binary benchmarks/hello

import argparse
import shlex

import m5
from m5.objects import *

p = argparse.ArgumentParser(description="ILP experiments: pipeline width, branch prediction, SMT")
p.add_argument("--binary", action="append", required=True,
               help="static x86 binary; repeat for SMT (one per hardware thread)")
p.add_argument("--args", action="append", default=None,
               help="arguments for the matching --binary (quoted); repeat in the same order")
p.add_argument("--cpu", default="o3", choices=["o3", "minor"],
               help="o3 = out-of-order X86O3CPU, minor = in-order X86MinorCPU")
p.add_argument("--width", type=int, default=1, help="pipeline width (O3 only)")
p.add_argument("--rob", type=int, default=None, help="ROB entries (default scales with width)")
p.add_argument("--iq", type=int, default=None, help="issue-queue entries (default scales with width)")
p.add_argument("--bp", default="tournament",
               choices=["static-nt", "local", "bimode", "tournament", "ltage"],
               help="branch predictor")
p.add_argument("--smt-fetch", default="RoundRobin",
               choices=["RoundRobin", "Branch", "IQCount", "LSQCount"],
               help="SMT fetch policy (O3 only)")
p.add_argument("--clock", default="2GHz")
p.add_argument("--max-ticks", type=int, default=None,
               help="stop after this many ticks (stats are still dumped)")
opts = p.parse_args()

nthreads = len(opts.binary)
args = opts.args or []
args += [""] * (nthreads - len(args))


# ---------------------------------------------------------------- branch predictor
def branch_predictor(name):
    if name == "static-nt":
        # gem5 has no "off" switch for branch prediction. A predictor that never
        # learns "taken" (1-bit counters biased to not-taken in a 2-entry table)
        # plus a 2-entry BTB means almost every taken branch is fetched down the
        # fall-through path and squashed at execute, i.e. static predict-not-taken.
        return LocalBP(localPredictorSize=2, localCtrBits=1, BTBEntries=2,
                       RASSize=1, indirectBranchPred=NULL)
    if name == "local":
        return LocalBP()            # 2K 2-bit counters indexed by PC
    if name == "bimode":
        return BiModeBP()
    if name == "tournament":
        return TournamentBP()       # local + global + chooser (Alpha 21264 style)
    if name == "ltage":
        return LTAGE()              # TAGE + loop predictor
    raise ValueError(name)


# ---------------------------------------------------------------- caches
class L1ICache(Cache):
    size = "32kB"; assoc = 2
    tag_latency = data_latency = response_latency = 2
    mshrs = 4; tgts_per_mshr = 20; is_read_only = True


class L1DCache(Cache):
    size = "64kB"; assoc = 2
    tag_latency = data_latency = response_latency = 2
    mshrs = 8; tgts_per_mshr = 20


class L2Cache(Cache):
    size = "2MB"; assoc = 8
    tag_latency = data_latency = response_latency = 20
    mshrs = 20; tgts_per_mshr = 12


# ---------------------------------------------------------------- system
system = System()
system.clk_domain = SrcClockDomain(clock=opts.clock, voltage_domain=VoltageDomain())
system.mem_mode = "timing"
system.mem_ranges = [AddrRange("2GB")]

if opts.cpu == "minor":
    if nthreads > 1:
        p.error("SMT needs --cpu o3 (MinorCPU is single-threaded in SE mode)")
    cpu = X86MinorCPU()
    cpu.branchPred = branch_predictor(opts.bp)
else:
    w = opts.width
    cpu = X86O3CPU(numThreads=nthreads)
    for param in ("fetchWidth", "decodeWidth", "renameWidth", "dispatchWidth",
                  "issueWidth", "wbWidth", "commitWidth", "squashWidth"):
        setattr(cpu, param, w)
    # Window sizes grow with width so wider machines are not starved by a tiny
    # window; defaults are gem5's (ROB 192, IQ 64) at width 8.
    cpu.numROBEntries = opts.rob or min(192, 32 * w)
    cpu.numIQEntries = opts.iq or min(64, 16 * w)
    cpu.LQEntries = min(32, 8 * w)
    cpu.SQEntries = min(32, 8 * w)
    cpu.branchPred = branch_predictor(opts.bp)
    if w <= 2:
        # With wbWidth 1-2, a burst of instructions finishing in the same cycle
        # is pushed into later writeback slots; with the default 5-entry
        # time buffers that overruns and gem5 aborts with
        # "timebuf.hh:54: Assertion `idx >= -past && idx <= future' failed".
        # Deeper buffers only add capacity; stage-to-stage delays are unchanged.
        cpu.forwardComSize = 32
        cpu.backComSize = 32
    if nthreads > 1:
        # Without this gem5 aborts in BaseCPU::registerThreadContexts():
        # "Assertion `system->multiThread || numThreads == 1' failed."
        system.multi_thread = True
        cpu.smtFetchPolicy = opts.smt_fetch
        cpu.smtNumFetchingThreads = 1      # one thread fetches per cycle, picked by policy
        cpu.smtCommitPolicy = "RoundRobin"
        # Shared physical register file must hold every thread's architectural state
        cpu.numPhysIntRegs = 256 + 64 * (nthreads - 1)
        cpu.numPhysFloatRegs = 256 + 64 * (nthreads - 1)
        # x86 maps one dummy matrix register per thread, and gem5's default is
        # numPhysMatRegs = 2. With 2 threads both are taken, the free list is
        # empty and rename blocks forever (0 instructions committed, no
        # "FullEvents" stats). Rename stalls if ANY register class has no
        # free entries (UnifiedRenameMap::numFreeEntries takes the minimum).
        cpu.numPhysMatRegs = 2 * nthreads
        cpu.numPhysVecPredRegs = max(32, 2 * nthreads)
system.cpu = cpu

cpu.icache = L1ICache()
cpu.dcache = L1DCache()
cpu.icache_port = cpu.icache.cpu_side
cpu.dcache_port = cpu.dcache.cpu_side

system.membus = SystemXBar()
system.l2bus = L2XBar()
cpu.icache.mem_side = system.l2bus.cpu_side_ports
cpu.dcache.mem_side = system.l2bus.cpu_side_ports
system.l2cache = L2Cache()
system.l2cache.cpu_side = system.l2bus.mem_side_ports
system.l2cache.mem_side = system.membus.cpu_side_ports
cpu.mmu.connectWalkerPorts(system.l2bus.cpu_side_ports, system.l2bus.cpu_side_ports)

# x86 needs one interrupt controller per hardware thread
cpu.createInterruptController()
for intr in cpu.interrupts:
    intr.pio = system.membus.mem_side_ports
    intr.int_requestor = system.membus.cpu_side_ports
    intr.int_responder = system.membus.mem_side_ports

system.system_port = system.membus.cpu_side_ports
system.mem_ctrl = MemCtrl()
system.mem_ctrl.dram = DDR3_1600_8x8(range=system.mem_ranges[0])
system.mem_ctrl.port = system.membus.mem_side_ports

# ---------------------------------------------------------------- workload
system.workload = SEWorkload.init_compatible(opts.binary[0])
procs = []
for i, (binary, a) in enumerate(zip(opts.binary, args)):
    proc = Process(pid=100 + i)
    proc.cmd = [binary] + shlex.split(a)
    procs.append(proc)
cpu.workload = procs
cpu.createThreads()

# Save the run's settings next to stats.txt so parse_stats.py can label it
import json, os
with open(os.path.join(m5.options.outdir, "run.json"), "w") as f:
    json.dump(dict(vars(opts), threads=nthreads,
                   rob=getattr(cpu, "numROBEntries", None) if opts.cpu == "o3" else None,
                   iq=getattr(cpu, "numIQEntries", None) if opts.cpu == "o3" else None),
              f, indent=2, default=str)

print("=== ilp.py configuration ===")
for k, v in sorted(vars(opts).items()):
    print(f"  {k:10s} = {v}")
if opts.cpu == "o3":
    print(f"  ROB={cpu.numROBEntries} IQ={cpu.numIQEntries} LQ={cpu.LQEntries} SQ={cpu.SQEntries}")
print("============================")

root = Root(full_system=False, system=system)
m5.instantiate()
print("Beginning simulation")
exit_event = m5.simulate(opts.max_ticks) if opts.max_ticks else m5.simulate()
print(f"Exiting @ tick {m5.curTick()} because {exit_event.getCause()}")
