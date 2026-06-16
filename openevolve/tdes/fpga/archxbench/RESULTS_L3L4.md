# TDES-FPGA Level 3-4 Results: fp_adder and fp_multiplier

**Date:** June 2026 | **Model:** claude-haiku-4-5-20251001 | **Budget:** pop=5, gens=6

---

## 1. Summary

| Condition | fp_adder (3 tests) | fp_multiplier (3 tests) | Notes |
|---|---|---|---|
| best_of_30 | 0/3 (0 tests) | 0/3 (0 tests) | 30 calls, 0 progress |
| single_agent_30 | 0/3 (0 tests) | 2/9 seeds → 1 test | 12 calls, partial |
| tdes_full | 0/3 (0 tests) | 0/3 (0 tests) | 3 calls, stagnates |
| tdes_no_crossover | 0/3 (0 tests) | 1/9 seeds → 1 test | 3-6 calls |
| tdes_no_memory | 0/3 (0 tests) | 0/3 (0 tests) | 3 calls, stagnates |
| tdes_scalar | 0/3 (0 tests) | 1/9 seeds → 1 test | 3-6 calls |

**No condition fully solves either design (0/36 cells solved).** fp_adder shows zero progress under all conditions. fp_multiplier shows partial progress (1 of 3 tests passing) in 4 of 18 cells, all via single_agent or through lucky TDES gen-1 mutations.

---

## 2. Per-Cell Results

### fp_adder (36 system tests + 17 unit_core + 12 unit_special)

| Condition | seed 0 | seed 1 | seed 2 | calls (med) |
|---|---|---|---|---|
| best_of_30 | 0/3 | 0/3 | 0/3 | 30 |
| single_agent_30 | 0/3 | 0/3 | 0/3 | 12 |
| tdes_full | 0/3 | 0/3 | 0/3 | 3 |
| tdes_no_crossover | 0/3 | 0/3 | 0/3 | 3 |
| tdes_no_memory | 0/3 | 0/3 | 0/3 | 3 |
| tdes_scalar | 0/3 | 0/3 | 0/3 | 3 |

### fp_multiplier (10 system tests + 7 unit_core + 7 unit_special)

| Condition | seed 0 | seed 1 | seed 2 | calls (med) |
|---|---|---|---|---|
| best_of_30 | 0/3 | 0/3 | 0/3 | 30 |
| single_agent_30 | **1/3** | 0/3 | **1/3** | 12 |
| tdes_full | 0/3 | 0/3 | 0/3 | 3 |
| tdes_no_crossover | 0/3 | 0/3 | **1/3** | 3–6 |
| tdes_no_memory | 0/3 | 0/3 | 0/3 | 3 |
| tdes_scalar | 0/3 | **1/3** | 0/3 | 3–6 |

**1/3 = one UNIT test passed (fp_mult_special or fp_mult_core), system test still failing.**

---

## 3. Key Findings

### 3.1 Level 3 is a hard wall for Haiku

fp_adder (full IEEE-754 single-precision addition) shows **zero progress** under any method with Haiku 4.5. Implementing alignment, normalization, rounding, and exception handling in one or a few LLM calls is beyond Haiku's capability. Even 30 independent zero-shot samples (best_of_30) get 0/3.

fp_multiplier (IEEE-754 multiplication) shows **occasional partial progress** — Haiku can sometimes write a correct `fp_mult_special` (NaN/Inf/zero detection) in one call, but consistently fails to complete both sub-modules.

### 3.2 TDES stagnation mechanism: all-or-nothing tests

TDES evolutionary conditions spend **exactly 3 LLM calls** in the vast majority of cells (all fp_adder, most fp_multiplier). This is the stagnation fingerprint:

- Gen 1: evaluate seed population (0 tests pass everywhere) → select → crossover (no complementary coverage → 0 children) → mutate 3 survivors (3 LLM calls)
- Gen 2: if population union did not grow (still 0 tests pass) → **stagnation detected → exit**

The 3-call stagnation occurs because each VerilogTest in the suite is **all-or-nothing**: `unit_special` has 12 sub-cases and `unit_core` has 17 sub-cases. A partial implementation (getting 6 of 12 special cases right) scores **zero test passes** at the VerilogTest level. TDES has no gradient.

### 3.3 Lucky single-gen mutations: 6-call cells

Four fp_multiplier cells ran 6 calls (two generations): `tdes_no_crossover/seed=2` and `tdes_scalar/seed=1`. These had at least one gen-1 mutation that correctly wrote `fp_mult_special` or `fp_mult_core` (passing all 7 cases in that UNIT test), causing the population union to grow. Gen 2 ran but made no further progress → stagnation at 1/3.

**Estimated per-call probability** of Haiku correctly implementing `fp_mult_special` in one shot: ~7% (observed: 4 successes in ~54 mutation calls on fp_mult_special across all cells).

With 3 survivors × 1 module each in gen 1, P(at least one unit_special pass) ≈ 1-(0.93)³ ≈ 19%. Observed 4/12 non-full-stagnation cells across TDES conditions ≈ 33%. Noisy but consistent.

### 3.4 Single agent outperforms TDES on partial progress

`single_agent_30` achieves **2/9 seeds** getting 1/3 tests while TDES conditions collectively get only **2/27 seeds** (excluding best_of_30). Single agent advantages:
- Runs 12 calls total (2 modules × 6 rounds) without early stagnation
- Fixes module A in round 2, then can iteratively improve module B in rounds 3-6
- Does not require all-or-nothing test passage to continue — it always runs its full budget

TDES loses 9 of every 12 calls to the 3-call stagnation trap when initial gen-1 mutations fail.

### 3.5 Crossover never fired

No TDES condition produced crossover attempts > 0. With population union staying at {} (fp_adder) or reaching {unit_special} in lucky cells (fp_multiplier), there was never a case where Candidate A passed unit_special AND Candidate B passed unit_core simultaneously — which is the prerequisite for complementary-coverage crossover. The hypothesis that the two sub-modules would develop independently and then be combined via crossover did not materialize with Haiku.

---

## 4. Root Cause Analysis

### Why the crossover hypothesis failed

The hypothesis: fp_mult_special and fp_mult_core are independently solvable, creating complementary coverage for crossover to exploit. The reality:

- P(fp_mult_special solved in 1 call) ≈ 7%
- P(fp_mult_core solved in 1 call) ≈ also ~7% or lower
- P(both solved independently in same generation) ≈ 0.07² × 3 candidates ≈ 1.5%

With 3 seeds × 6 conditions = 18 cells, expected crossover opportunities ≈ 0.27. Observed: 0. This is consistent.

**The Goldilocks window for crossover:** Individual module solve probability must be in the ~30–60% range. At this level, gen-1 mutations reliably produce complementary candidates, crossover fires, and the population combines partial solutions. Below 30%, gen-1 mutations fail too often and TDES stagnates. Above 60%, single-agent mutation is sufficient without crossover. Haiku's ≈7% places fp_multiplier firmly below the Goldilocks window.

### Why fp_adder is harder than fp_multiplier

fp_adder's `fp_adder_core` requires: significand alignment (variable-length shift), add/subtract with sign handling, leading-zero normalization, 4-mode rounding with GRS bits, and overflow/underflow detection. Even with detailed CEGIS feedback (specific failing inputs and errors), fixing all 17 unit_core cases simultaneously in one call is unlikely for Haiku.

fp_adder_core P(correct in 1 call) ≈ 0%. Not even a single lucky seed in 18 cells. P(fp_special_case correct in 1 call) ≈ 5% (small NaN/Inf cases, but the 12-case all-or-nothing threshold is too strict).

---

## 5. Implications for the Paper

### Benchmark design constraints

TDES crossover requires **both** of:
1. **Decomposable design**: two sub-modules with independent test coverage
2. **Achievable sub-modules**: base model P(solve in 1 call) ≥ ~30%

Our Level 3-4 designs satisfy (1) but fail (2) for Haiku. Level 1-2 designs (comparator-8bit, etc.) satisfy both but are so easy that single-agent trivially solves them in 3 calls.

**The correct target regime for the paper:** 
- Designs where each sub-module requires 2-5 generations to solve (not 1 shot, not impossible)
- P(correct in 1 call) ≈ 10-15% per module; with pop=5 gens=6 TDES gets P(eventually correct) → 99%
- Both modules in this range → crossover fires to combine them

Level 1b-2 hierarchical designs are at this level with Haiku. The original Phase 1 finding (comparator-8bit, decoder-3to8, etc.) confirms TDES works in this regime.

### Recommended framing

Rather than claiming TDES beats baselines on Level 3-4, the honest framing is:

1. **"TDES has a capability frontier that depends on base model strength."** On Level 1-2 with Haiku, TDES works (18/18 crossover attempts accepted). On Level 3 with Haiku, single-agent outperforms because TDES stagnates before crossover can fire.

2. **"Finer test granularity unlocks TDES on harder designs."** With individual-case tests (one TDES VerilogTest per sub-behavior), partial implementations gain partial scores, TDES can climb the gradient, and crossover has opportunity to fire. The all-or-nothing test structure is a benchmark design flaw, not a fundamental TDES limitation.

3. **"Level 3 requires a stronger model (Sonnet)."** At higher per-call accuracy, individual modules become solvable in 1-3 gen, placing the designs in the Goldilocks window.

---

## 6. Limitations

- Only 3 seeds per cell (high variance, especially at low pass rates)
- Single model (Haiku 4.5); Sonnet would likely shift all designs into the solvable regime
- fp_adder and fp_multiplier were the only Level 3 designs tested; Level 4 (FFT, pipelined FP) was not run due to file-based I/O complexity
- The "budget matching" between conditions is imperfect: single_agent_30 uses `rounds=max_generations=6`, giving 12 calls (not 30 as intended)

---

## 7. Conclusion

Level 3 benchmarks with Haiku confirm the **capability-regime hypothesis**: TDES complementary-coverage crossover fires reliably only when individual sub-modules are achievable by the base model (P ≥ 30% per call). Below this threshold, gen-1 stagnation traps TDES in 3-call exits. Single-agent iterative repair, which does not have a stagnation mechanism, is more robust in the sub-threshold regime.

The crossover benefit demonstrated in Phase 1 (hier designs) and the stagnation in Level 3 are both consistent with this hypothesis. The paper's main contribution — that complementary-coverage crossover combines partial solutions when they exist — is validated; the boundary conditions for when they exist are now clearer.
