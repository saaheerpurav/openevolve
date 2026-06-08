# TDES-FPGA: experimental results (5-experiment campaign)

All runs use the Anthropic OpenAI-compatible endpoint and the OSS CAD Suite
(Icarus Verilog 14, Yosys 0.66). **Models by experiment** (Opus's design):
**Haiku 4.5** for the broad RTLLM baseline (Exp 1), **Sonnet 4.6** for the
crossover showcase, ablation, and scaling (Exp 2/3/4). Reproduce with the configs
in `configs/` (`ANTHROPIC_API_KEY` + `OSS_CAD_SUITE_ROOT` set):

```bash
python -m openevolve.tdes.fpga.experiments.run_all \
    --haiku  configs/anthropic_haiku.yaml --sonnet configs/anthropic_sonnet.yaml \
    --seeds 0 1 2          # or run_exp{1..4}.py / convergence.py individually
```

Raw per-cell metrics land in `tdes_fpga_results/metrics_exp*.json` (gitignored);
the numbers below are transcribed from them.

**What the campaign shows, up front (and honestly).** (a) Iterative
test-feedback evolution massively beats one-shot generation, and (b) the
**hierarchical** test-pass vector is essential — flattening it to scalar fitness
collapses the solver to 0%. (c) Complementary-coverage crossover — the paper's
primary contribution — **fires on *published* ArchXBench benchmarks** (32 accepted
grafts, +2.0 tests each), combining separately-evolved correct submodules and
tops into complete designs; and it is **necessary** under a tight multi-module
budget (the controlled datapath, §S1). (d) On small (2-module) designs a
single-agent baseline is strong — TDES's population machinery is overhead there,
not a win; TDES's advantage is on *modular, budget-constrained* problems. We
report single-agent alongside TDES everywhere rather than hide it.

---

## Experiment 1 — RTLLM v2 baseline (Haiku)

9 usable single-module RTLLM v2 designs (one of the 10 sampled was auto-skipped
as not reference-sound), 3 conditions, 3 seeds (`run_exp1_baseline.py`).

| Design | tdes_full | single_agent | pass@5 |
|---|---|---|---|
| accu | ✓ | ✓ | ✓ |
| adder_8bit / adder_16bit / adder_pipe_64bit | ✓ | ✓ | ✗ |
| div_16bit / multi_8bit / right_shifter | ✓ | ✓ | ✗ |
| barrel_shifter / multi_16bit | ✗ | ✗ | ✗ |
| **solve rate** | **70%** | **70%** | **11%** |

Crossover: 27 pairs considered, **0 attempts** — *expected*: RTLLM designs are
single-module, so there is nothing to graft (crossover's value needs modules,
§2). **Takeaways.** Iterative-feedback methods (TDES, single-agent) crush one-shot
`pass@5` (70% vs 11%): the CEGIS loop does the work. On single-module designs TDES
ties single-agent — its population machinery neither helps nor hurts here.

## Experiment 2 — Crossover on *published* hierarchical ArchXBench designs (Sonnet)

The money experiment. `hierarchical_archx.py` turns five published ArchXBench
designs — each specified as *"X built from sub-component Y"* — into genuine
two-module `{TOP, SUB}` problems with a 3-tier suite (SUB unit · TOP-wiring vs an
inline golden SUB · the **native** ArchXBench testbench as SYSTEM), so
complementary-coverage crossover can fire on real benchmarks. 4 conditions, 3
seeds, diverse module scheduling, one module fixed per candidate per generation.

**Table 1 — method comparison (best over seeds):**

| Design | tdes_full | tdes_no_crossover | single_agent | pass@5 |
|---|---|---|---|---|
| comparator-8bit | ✓ | ✓ | ✓ | ✗ |
| decoder-3to8 | ✓ | ✓ | ✓ | ✗ |
| demux-1to4 | ✓ | ✓ | ✓ | ✗ |
| mux4to1 | ✗ | ✗ | ✓ | ✗ |
| carry_select_adder_32bit | ✗ | ✓ | ✓ | ✗ |
| **solve rate (per cell)** | **60%** | **60%** | **100%** | **0%** |

**Table 2 — complementary-coverage crossover (`tdes_full`):**

| Metric | Value |
|---|---|
| Crossover pairs considered | 90 |
| Complementary coverage arose | 16 (18%) |
| **Accepted (strict superset)** | **16 / 16 (100%)** |
| **Mean Δ tests per accepted graft** | **+2.0** |

**This is the contribution, on published benchmarks.** Every time the diverse
population produced two *partial* candidates — one with a correct submodule, one
with a correct top (verified against a golden submodule) — crossover grafted them
into a complete design: 16/16 accepted, each adding +2 tests (a partial → a full
3/3). The per-module timeline confirms the mechanism: e.g. on comparator-8bit,
`comparator_4bit` and `comparator_8bit` are fixed in *different* lineages, then
combined. (Pooled across Exp 2 + Exp 4's crossover conditions: **32 accepted
grafts** — comparator 12, demux 12, decoder 6, carry-select 2; `fig3_crossover.json`.)

**Honest reading of Table 1.** `tdes_full` = `tdes_no_crossover` = 60%, both below
`single_agent` (100%). On only-two-module designs at a 6-generation budget,
crossover *accelerates* but is **not necessary** — a no-crossover lineage also
fixes both modules in time on the easy three; both diverse-regime conditions miss
the two hard tops (mux4to1's X-propagation edge case; the 32-bit composition)
where single-agent's greedy whole-codebase repair succeeds. Two modules is
mathematically too few to show crossover *necessity*; that result is the
controlled 4-module datapath (§S1). What Exp 2 establishes is **external
validity**: the crossover mechanism is not an artifact of synthetic problems — it
fires and combines partial solutions on published RTL benchmarks.

## Experiment 3 — ArchXBench Level 2-3 scaling (Sonnet) — *preliminary*

L2-L3 designs (single-round AES-128, pipelined CLA/Wallace, FP adder/multiplier)
run natively (no reference RTL ships, so `require_usable=False`; the native
testbench is the system test). **Preliminary:** `aes128_single_round` reads
**0/1 for every method** (tdes_full, tdes_no_crossover, single_agent across
seeds). These designs sit at/beyond the current budget+capability frontier — a
single-round AES or an IEEE-754 datapath is not synthesized correctly in ≤6
generations by any condition. This bounds where the approach works and is
reported as-is (the run is slow — large/clocked testbenches — and continues in
the background; `metrics_exp3.json` holds whatever has completed). No design is
scored as passing that did not; the verdict parser is failure-evidence-first.

## Experiment 4 — Full mechanism ablation (Sonnet)

The five hierarchical designs, 6 conditions, 3 seeds (`run_exp4_ablation.py`).

| Condition | solve rate | what is removed |
|---|---|---|
| single_agent | **100%** | (baseline: greedy whole-codebase repair) |
| **tdes_full** | **73%** | nothing |
| tdes_no_crossover | 67% | complementary-coverage crossover |
| tdes_no_cegis | 67% | structured CEGIS feedback (pass/fail only) |
| tdes_no_memory | 60% | negative-exemplar memory |
| **tdes_scalar** | **0%** | the hierarchy (→ scalar pass-count fitness) |

**Takeaways.** A clean per-mechanism contribution ordering: `tdes_full` (73%) >
`no_crossover` (67%) ≈ `no_cegis` (67%) > `no_memory` (60%) ≫ `scalar` (**0%**).
The dramatic result is **scalar fitness = 0%**: flattening the hierarchical
test-pass vector to a scalar count destroys the solver — hierarchical selection
(which preserves partially-correct candidates instead of collapsing them to one
number) is *load-bearing*, not cosmetic. Crossover and memory each add several
points. `single_agent` remains the ceiling on these small designs (the §S1/§S3
single-vs-modular tradeoff).

## Experiment 5 — Convergence-efficiency analysis

Pooled over Exp 1/2/4 (`convergence.py`; figures in `exp5/`).

| Condition | solve rate | median calls (all) | median calls-to-solve |
|---|---|---|---|
| single_agent | 86% | 3 | 2 |
| tdes_full | 68% | 6 | 6 |
| tdes_no_cegis | 67% | 6 | 6 |
| tdes_no_crossover | 63% | 6 | 6 |
| tdes_no_memory | 60% | 6 | 6 |
| tdes_scalar | 0% | 9 | — |
| pass@5 | 7% | 5 | — |

**Honest efficiency reading.** On these small designs single-agent solves with
**fewer** LLM calls than TDES (median 3 vs 6) — mean calls-to-solve "speedup"
(single_agent / tdes_full) is **1.06×**, i.e. no TDES advantage; the population
is overhead at this scale. The efficiency win TDES targets is on *modular,
budget-tight* problems where crossover makes a free (zero-LLM-call) jump that
mutation would need several rounds to reproduce — see §S1, where no-crossover is
*structurally capped* and cannot finish at all.

---

## §S1 — Crossover *necessity* (controlled 4-module datapath, Sonnet)

The 2-module published designs (§2) cannot show crossover *necessity* (a single
lineage fixes 2 modules within budget). The controlled `datapath_problem.py` —
**four independent modules** (`add8`, `bshift`, `scmp`, `popcnt`), 4 unit + 2
integration + 1 system tests, one module fixed per candidate per generation,
diverse scheduling — isolates it.

**Tight budget (gens=3 < 4 modules):** mutation alone is *structurally capped*.

| Condition | solve rate | best passes / 7 |
|---|---|---|
| tdes_full | **1/3** (seed 1 → 7/7 via crossover) | 4, **7**, 4 |
| tdes_no_crossover | **0/3** — capped | 4, 4, 4 |

**Generous budget (gens=6):** both solve, but crossover is highly active
(6–13 accepted grafts/run, +1.9 mean lift) and reaches the solution in fewer
generations (4.67 vs 5.00). Under a budget below the module count, a single
lineage *can never* combine the separately-evolved modules — crossover is the
only path to a complete design. This is the controlled proof that crossover is
**necessary, not merely helpful**, for modular synthesis under budget — the
regime the paper targets. (Documented requirement: diverse per-candidate module
scheduling supplies the population diversity crossover needs; all
acceptance/regression rules are inherited unchanged.)

## §S2 — Equivalence-gated efficiency demo (AlphaEvolve-TPU analog)

Separately, `fpga/efficiency_demo/` reproduces AlphaEvolve's TPU Verilog result
in miniature: evolve a *correct* complex multiplier into a **provably-equivalent,
smaller** one (4→3 multipliers), gated on Yosys **formal equivalence** (miter +
SAT), optimizing RTL `$mul` count. Sonnet discovered the Gauss 3-multiplication
algorithm in 2 generations, SAT-verified. See `efficiency_demo/RESULTS.md`.

## §S3 — Honesty notes

* **Single-agent is a strong baseline on small designs** and we report it
  everywhere. TDES's population/crossover machinery is overhead on 1–2-module
  problems (Exp 1/2/4) and pays off on *modular, budget-constrained* problems
  (§S1). We do not claim TDES beats single-agent on solve rate or calls here.
* **Authored tiers (Exp 2).** ArchXBench ships only a top-level testbench; the
  SUB-unit and TOP-wiring tiers and the small submodule goldens are authored by
  us and **reference-gated** (the full hierarchical reference passes every tier;
  `tests/test_hierarchical_archx.py`). The SYSTEM tier is the unmodified native
  benchmark. The TOP-wiring tier is tagged UNIT (co-equal with the SUB tier) so
  selection keeps both partial-solution lineages alive for crossover.
* **Exp 3 is preliminary** and frontier-bounding: L2-L3 designs are not solved by
  any method in budget; nothing is scored as passing that did not.
* **`pass@5` calls-to-solve** is reported as 1 by construction (first sample that
  happens to pass); its *solve rate* (7–11%) is the meaningful figure.
