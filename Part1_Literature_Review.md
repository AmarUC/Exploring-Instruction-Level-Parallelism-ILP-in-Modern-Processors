# Instruction-Level Parallelism: Metrics, Challenges, and Future Directions

*Part 1: Literature Review*

---

## Introduction

Instruction-level parallelism (ILP) is the overlap of independent instructions from a single thread. Hardware finds it at run time, through pipelining, dynamic scheduling, speculation and multiple issue, or a compiler exposes it ahead of time, through scheduling, unrolling and VLIW bundling (Hennessy & Patterson, 2019). For about twenty years, from the mid-1980s to the mid-2000s, ILP and rising clock rates drove most of the gains in single-thread performance. Since then the returns have shrunk. This review covers how ILP effectiveness is measured, what limits it today, how researchers are responding, and which directions look most promising.

## 1. Performance Metrics for ILP

### 1.1 Throughput: IPC and CPI

The basic measure of ILP is **instructions per cycle (IPC)**, or its reciprocal, cycles per instruction (CPI). The "iron law" of processor performance ties them to run time:

> Execution time = Instruction count × CPI × Clock period

An ILP technique succeeds if it lowers CPI without raising the instruction count or the clock period by more. An ideal *w*-wide superscalar reaches IPC = *w*. Real machines fall short because of data dependences, control hazards, structural hazards and memory stalls. Wall's (1991) limit study is still the standard reference here: even with generous hardware, realistic branch prediction and finite windows held typical programs to an IPC of about 5–7, far below the hundreds that an oracle machine could reach.

IPC on its own can mislead. It depends on the ISA (an x86 instruction is not a RISC-V instruction, and x86 cores issue micro-ops rather than instructions). It also says nothing about frequency, so a design that doubles IPC by halving its clock rate gains nothing. Agarwal, Hrishikesh, Keckler and Burger (2000) showed this tension directly: wire delay and deeper pipelines meant that clock-rate gains and IPC gains increasingly cancelled each other out.

### 1.2 Latency

**Instruction latency** is the number of cycles from fetch to commit. **Operation latency** is the number of cycles an operation takes in its functional unit, for example 1 cycle for an integer add or roughly 4 for a floating-point multiply. Pipelining raises throughput but does not reduce, and usually increases, per-instruction latency, because each stage adds latch overhead. That trade-off sets a best pipeline depth. Hartstein and Puzak (2002) and Sprangle and Carmean (2002) both modelled it and found that very deep pipelines (such as the Pentium 4's 20 or more stages) lose more to branch-misprediction penalties and latch overhead than they gain in frequency. On an out-of-order core, Little's law links the two metrics: average instructions in flight = throughput × latency. A machine that sustains high IPC with long latencies needs a large instruction window (reorder buffer, issue queue, load/store queue), and that window is exactly what costs power and complexity.

### 1.3 Power and Energy

Since the end of Dennard scaling (Dennard et al., 1974, described the scaling rules whose breakdown around 2005 ended "free" frequency gains), power has been a first-class metric. Relevant measures include:

- **Energy per instruction (EPI)** and **performance per watt**, which matter for mobile devices and datacentres.
- **Energy-delay product (EDP)** and **ED²P**, which weight performance and energy together. Gonzalez and Horowitz (1996) argued that EDP, not raw power, is the right figure of merit, because power can always be cut by slowing down.
- **Power density** (W/mm²), which sets thermal limits and leads to "dark silicon," area that cannot all be powered at once (Esmaeilzadeh et al., 2011).

ILP structures are energy-hungry. Register renaming, wakeup/select logic, wide bypass networks and large multi-ported register files grow superlinearly with issue width. Palacharla, Jouppi and Smith (1997) showed that issue-queue wakeup/select and bypass delays grow roughly quadratically with width and window size. Speculation also burns energy on wrong-path instructions that are later squashed.

### 1.4 Trade-offs Between Metrics

| Optimised metric | Typical technique | Cost to other metrics |
|---|---|---|
| Throughput (IPC) | Wider issue, larger window, aggressive speculation | Higher power, more area, possibly longer cycle time |
| Latency | Shorter pipeline, value bypassing, fast caches | Lower clock frequency, less overlap |
| Frequency | Deeper pipeline | Larger misprediction penalty, higher latency, latch power |
| Energy | Narrow in-order core, clock and power gating | Lower single-thread performance |

For multithreaded or multiprogrammed workloads, total IPC rewards running only the easy threads. Snavely and Tullsen (2000) introduced **weighted speedup**, and Eyerman and Eeckhout (2008) recommend system throughput (STP) and average normalised turnaround time (ANTT) instead, because they capture both throughput and fairness. Part 2 uses a similar normalised measure for SMT: the time to run two programs back to back divided by the time to run them together.

## 2. Current Challenges

### 2.1 Diminishing Returns

The ILP available in general-purpose integer code is limited by true data dependences and by hard-to-predict branches. Wall's (1991) study, and many later ones, show that doubling window size or issue width gives ever smaller IPC gains. Most programs sustain an IPC of 1–3 even on cores that can retire 6–8 micro-ops per cycle. Pointer-chasing and irregular codes (graph analytics, databases, interpreters) have very little ILP to find, because each load depends on the one before it.

### 2.2 Complexity and Wire Delay

Superscalar complexity grows faster than linearly with width (Palacharla et al., 1997). The critical structures are:

- **Rename**: dependency checking across a fetch group grows with the square of the group size.
- **Issue queue**: wakeup broadcasts every result tag to every entry, and select is a priority tree over all ready entries.
- **Register file**: ports grow with issue width, and area grows roughly with the square of the port count.
- **Bypass network**: the number of forwarding paths grows with the square of the number of functional units.

As transistors shrink, wire delay does not shrink with them, so a signal can no longer cross a large structure in one cycle (Agarwal et al., 2000). Designers have to cluster, pipeline or partition these structures, and each of those adds latency and scheduling penalties.

### 2.3 The Power Wall

Every extra in-flight instruction costs energy whether or not it commits. After 2005, power, not transistors, became the binding limit (Esmaeilzadeh et al., 2011). The industry's move to multicore was largely an admission that turning transistors into thread-level parallelism (TLP) was more energy-efficient than spending them on more ILP.

### 2.4 The Memory Wall

A last-level cache miss costs hundreds of cycles. An out-of-order window can hide L1 and L2 latency, but covering DRAM latency needs a window far larger than is practical. When the oldest instruction is a load waiting on memory, the reorder buffer fills and the core stalls. This is the main reason big cores achieve low IPC on server and data-analytics workloads.

### 2.5 Branch Prediction Accuracy and Misprediction Cost

As pipelines deepen and widen, each misprediction throws away more work: roughly pipeline depth × issue width instruction slots. A 95% accurate predictor still mispredicts once every 20 branches. With a branch every 5–6 instructions, that is a flush roughly every 100 instructions, which caps the IPC a wide machine can sustain. Modern predictors such as TAGE (Seznec & Michaud, 2006) and perceptron variants (Jiménez & Lin, 2001) reach very high accuracy, but the branches that remain hard to predict depend on data and resist history-based prediction.

### 2.6 Security of Speculation

Spectre and Meltdown (Kocher et al., 2019) showed that speculative execution, the very mechanism that makes deep ILP possible, leaks information through microarchitectural side channels. Mitigations such as fences, speculative load hardening and restricting speculation on certain loads cost performance, sometimes a great deal. That creates a new trade-off between ILP and security that did not exist before 2018.

### 2.7 Verification and Design Cost

Out-of-order cores with deep speculation are among the hardest digital systems to verify. Each new mechanism, such as memory-dependence prediction, value prediction or move elimination, adds corner cases and raises design cost. That makes smaller, specialised designs relatively more attractive.

## 3. How Researchers Are Addressing These Challenges

### 3.1 Better Speculation

- **Branch prediction.** TAGE and its derivatives (TAGE-SC-L) use several history lengths in a geometric series, with tagged tables, and they won successive championship branch prediction contests (Seznec & Michaud, 2006). Perceptron predictors (Jiménez & Lin, 2001) learn linear functions of long histories and have appeared in commercial cores. Current work targets the remaining hard-to-predict branches with longer-range correlation and with ideas from machine learning.
- **Value prediction.** Lipasti, Wilkerson and Shen (1996) showed that loaded values are often predictable ("value locality"), which lets dependent instructions run before their inputs arrive. Perais and Seznec (2014) made value prediction practical with high-confidence predictors and validation at commit, which removed much of the earlier hardware cost.
- **Memory-dependence prediction and load speculation** let loads run ahead of earlier stores whose addresses are not yet known.

### 3.2 Effective Larger Windows Without the Cost

- **Runahead execution** (Mutlu, Stark, Wilkerson & Patt, 2003). When a long-latency miss blocks retirement, the core checkpoints and keeps executing speculatively to issue future misses early as prefetches, then discards the results. It gets much of the memory-level parallelism (MLP) of a far larger window at small cost.
- **Instruction reuse and memoisation** (Sodani & Sohi, 1997) skip recomputation of results seen before.
- **Complexity-effective designs.** Clustered back ends, dependence-based steering and hierarchical schedulers keep each cycle-critical loop small while the total window grows (Palacharla et al., 1997).

### 3.3 Combining ILP With Thread-Level Parallelism

**Simultaneous multithreading (SMT)** (Tullsen, Eggers & Levy, 1995) issues instructions from several threads in the same cycle. It fills issue slots a single thread leaves empty because of dependences or misses, so it uses existing ILP hardware more fully. The ICOUNT fetch policy (Tullsen et al., 1996) favours the threads with the fewest instructions in the front end, which keeps one stalled thread from filling the queues. SMT is now standard (Intel Hyper-Threading, AMD SMT, IBM POWER SMT8).

### 3.4 Heterogeneity

**Single-ISA heterogeneous multicores** (Kumar et al., 2003) combine large out-of-order cores with small in-order cores and move each thread to the core that suits its current ILP. ARM big.LITTLE, Apple's performance and efficiency cores and Intel's P-core/E-core designs put this idea into production. The work is spent where ILP pays off and saved where it does not.

### 3.5 Revisiting the Hardware/Software Split

VLIW and EPIC (Fisher, 1983) moved ILP discovery to the compiler. Itanium's commercial failure showed the limits of purely static ILP when latencies are unpredictable, but the ideas live on in DSPs and accelerators. Research architectures such as TRIPS explored dataflow-like execution of large instruction blocks, aiming to extract ILP without centralised wakeup/select logic (Sankaralingam et al., 2003).

## 4. Future Directions

### 4.1 Domain-Specific Accelerators

Hennessy and Patterson (2019, *A new golden age*) argue that with Moore's law slowing and Dennard scaling over, the biggest remaining gains come from domain-specific architectures (DSAs). Google's TPU (Jouppi et al., 2017) is the standard example: a systolic array that exploits massive, regular data parallelism for neural networks and achieves an order of magnitude better performance per watt than contemporary CPUs and GPUs on its target workloads. For ILP research, this means general-purpose cores increasingly act as *orchestrators* that keep accelerators fed, and their ILP mechanisms must serve control-heavy, irregular code well.

### 4.2 Machine-Learning-Based Microarchitecture

ML is entering microarchitecture in two ways:

- **As predictors inside the core.** Perceptron branch predictors were the first example. Hashemi et al. (2018) showed that LSTM models can predict memory-access patterns for prefetching better than conventional prefetchers, though at hardware costs that are not yet practical. Reinforcement learning has been applied to memory-controller scheduling (Ipek, Mutlu, Martínez & Caruana, 2008). The main open question is cost: an ML predictor must fit in a few kilobytes and return an answer in one cycle.
- **As design tools.** ML models trained on simulation data can explore the very large space of microarchitecture parameters, such as width, window sizes and predictor sizes, much faster than exhaustive simulation.

### 4.3 Heterogeneous and Reconfigurable Cores

Beyond fixed big/little pairs, researchers are studying cores that resize their structures at run time, for example by powering down issue-queue or ROB partitions when a thread has little ILP. They are also studying the fusion of small cores into a larger logical core. These approaches treat ILP as a resource to provision by demand, which fits a power-limited world.

### 4.4 Secure Speculation

After Spectre, research into designs that keep the performance of speculation without its leakage, such as invisible speculation, delay-on-miss and taint tracking, is now central to ILP work. The next generation of speculative cores is likely to make security an explicit design dimension alongside IPC and power.

### 4.5 Wider but Smarter Cores

Commercial cores keep getting wider, with 8-wide decode and windows of several hundred entries in recent high-performance designs. Wide cores are viable because of better predictors, micro-op caches that bypass complex decode, and techniques that cut back-end pressure (move elimination, zero-idiom elimination, macro-op fusion). The lesson is that wider issue still pays off for well-predicted, cache-friendly code, as long as the front end keeps up and the extra structures are energy-efficient.

### 4.6 Synthesis

The most promising directions share one theme: **spend ILP hardware only where it pays off**. That means accurate, cheap prediction (TAGE-class and learned predictors, value prediction), MLP-oriented techniques that address the memory wall (runahead, smarter prefetching), SMT and heterogeneity to fill or avoid unused issue slots, and accelerators for regular data-parallel work that general-purpose ILP handles inefficiently. Part 2's experiments show the same pattern on a small scale. Wider issue helps independent integer and FP work, barely helps dependent chains and pointer chasing, and leaves enough unused slots that SMT can recover throughput by running a second thread.

---

## References

Agarwal, V., Hrishikesh, M. S., Keckler, S. W., & Burger, D. (2000). Clock rate versus IPC: The end of the road for conventional microarchitectures. *Proceedings of the 27th Annual International Symposium on Computer Architecture*, 248–259. https://doi.org/10.1145/339647.339691

Dennard, R. H., Gaensslen, F. H., Yu, H.-N., Rideout, V. L., Bassous, E., & LeBlanc, A. R. (1974). Design of ion-implanted MOSFET's with very small physical dimensions. *IEEE Journal of Solid-State Circuits, 9*(5), 256–268.

Esmaeilzadeh, H., Blem, E., St. Amant, R., Sankaralingam, K., & Burger, D. (2011). Dark silicon and the end of multicore scaling. *Proceedings of the 38th Annual International Symposium on Computer Architecture*, 365–376.

Eyerman, S., & Eeckhout, L. (2008). System-level performance metrics for multiprogram workloads. *IEEE Micro, 28*(3), 42–53.

Fisher, J. A. (1983). Very long instruction word architectures and the ELI-512. *Proceedings of the 10th Annual International Symposium on Computer Architecture*, 140–150.

Gonzalez, R., & Horowitz, M. (1996). Energy dissipation in general purpose microprocessors. *IEEE Journal of Solid-State Circuits, 31*(9), 1277–1284.

Hartstein, A., & Puzak, T. R. (2002). The optimum pipeline depth for a microprocessor. *Proceedings of the 29th Annual International Symposium on Computer Architecture*, 7–13.

Hashemi, M., Swersky, K., Smith, J. A., Ayers, G., Litz, H., Chang, J., Kozyrakis, C., & Ranganathan, P. (2018). Learning memory access patterns. *Proceedings of the 35th International Conference on Machine Learning*, 1919–1928.

Hennessy, J. L., & Patterson, D. A. (2019). *Computer architecture: A quantitative approach* (6th ed.). Morgan Kaufmann.

Hennessy, J. L., & Patterson, D. A. (2019). A new golden age for computer architecture. *Communications of the ACM, 62*(2), 48–60.

Ipek, E., Mutlu, O., Martínez, J. F., & Caruana, R. (2008). Self-optimizing memory controllers: A reinforcement learning approach. *Proceedings of the 35th Annual International Symposium on Computer Architecture*, 39–50.

Jiménez, D. A., & Lin, C. (2001). Dynamic branch prediction with perceptrons. *Proceedings of the 7th International Symposium on High-Performance Computer Architecture*, 197–206.

Jouppi, N. P., Young, C., Patil, N., Patterson, D., et al. (2017). In-datacenter performance analysis of a tensor processing unit. *Proceedings of the 44th Annual International Symposium on Computer Architecture*, 1–12.

Kocher, P., Horn, J., Fogh, A., Genkin, D., Gruss, D., Haas, W., Hamburg, M., Lipp, M., Mangard, S., Prescher, T., Schwarz, M., & Yarom, Y. (2019). Spectre attacks: Exploiting speculative execution. *2019 IEEE Symposium on Security and Privacy*, 1–19.

Kumar, R., Farkas, K. I., Jouppi, N. P., Ranganathan, P., & Tullsen, D. M. (2003). Single-ISA heterogeneous multi-core architectures: The potential for processor power reduction. *Proceedings of the 36th Annual IEEE/ACM International Symposium on Microarchitecture*, 81–92.

Lipasti, M. H., Wilkerson, C. B., & Shen, J. P. (1996). Value locality and load value prediction. *Proceedings of the 7th International Conference on Architectural Support for Programming Languages and Operating Systems*, 138–147.

Mutlu, O., Stark, J., Wilkerson, C., & Patt, Y. N. (2003). Runahead execution: An alternative to very large instruction windows for out-of-order processors. *Proceedings of the 9th International Symposium on High-Performance Computer Architecture*, 129–140.

Palacharla, S., Jouppi, N. P., & Smith, J. E. (1997). Complexity-effective superscalar processors. *Proceedings of the 24th Annual International Symposium on Computer Architecture*, 206–218.

Perais, A., & Seznec, A. (2014). Practical data value speculation for future high-end processors. *Proceedings of the 20th International Symposium on High-Performance Computer Architecture*, 428–439.

Sankaralingam, K., Nagarajan, R., Liu, H., Kim, C., Huh, J., Burger, D., Keckler, S. W., & Moore, C. R. (2003). Exploiting ILP, TLP, and DLP with the polymorphous TRIPS architecture. *Proceedings of the 30th Annual International Symposium on Computer Architecture*, 422–433.

Seznec, A., & Michaud, P. (2006). A case for (partially) TAgged GEometric history length branch prediction. *Journal of Instruction-Level Parallelism, 8*, 1–23.

Smith, J. E., & Sohi, G. S. (1995). The microarchitecture of superscalar processors. *Proceedings of the IEEE, 83*(12), 1609–1624.

Snavely, A., & Tullsen, D. M. (2000). Symbiotic jobscheduling for a simultaneous multithreaded processor. *Proceedings of the 9th International Conference on Architectural Support for Programming Languages and Operating Systems*, 234–244.

Sodani, A., & Sohi, G. S. (1997). Dynamic instruction reuse. *Proceedings of the 24th Annual International Symposium on Computer Architecture*, 194–205.

Sprangle, E., & Carmean, D. (2002). Increasing processor performance by implementing deeper pipelines. *Proceedings of the 29th Annual International Symposium on Computer Architecture*, 25–34.

Tullsen, D. M., Eggers, S. J., Emer, J. S., Levy, H. M., Lo, J. L., & Stamm, R. L. (1996). Exploiting choice: Instruction fetch and issue on an implementable simultaneous multithreading processor. *Proceedings of the 23rd Annual International Symposium on Computer Architecture*, 191–202.

Tullsen, D. M., Eggers, S. J., & Levy, H. M. (1995). Simultaneous multithreading: Maximizing on-chip parallelism. *Proceedings of the 22nd Annual International Symposium on Computer Architecture*, 392–403.

Wall, D. W. (1991). Limits of instruction-level parallelism. *Proceedings of the 4th International Conference on Architectural Support for Programming Languages and Operating Systems*, 176–188.
