# TDES-FPGA Decompose-Then-Evolve: Level-4 Results

**Date**: 2026-06-17  
**Design**: `fp_mult_pipeline` — IEEE-754 single-precision pipelined FP multiplier  
**Sub-modules (evolved)**: fpm_unpack, fpm_multiply, fpm_normalize, fpm_round_pack, fpm_special  
**Top module (fixed)**: fp_mult_pipeline — pipeline registers + mux (not evolved)  
**Tests**: 59 total — 34 UNIT (8+6+5+8+7 per module) + 25 SYSTEM  
**Baselines**: Level-4 monolithic = 0/N solved in all prior experiments

---

## Complete Results Table

| Model | Condition | Seed 0 | Seed 1 | Seed 2 | Solve Rate | Med Calls |
|---|---|---|---|---|---|---|
| Haiku 4.5 | single_agent_30 | 26/59 | 26/59 | 26/59 | **0/3** | 13 |
| Haiku 4.5 | tdes_no_crossover | 37/59 | 55/59 | 58/59 | **0/3** | 24 |
| Haiku 4.5 | tdes_full | 37/59 | **59/59** | 53/59 | **1/3** | 22 |
| Sonnet 4.6 | single_agent_30 | **59/59** | **59/59** | **59/59** | **3/3** | 6 |
| Sonnet 4.6 | tdes_no_crossover | **59/59** | **59/59** | **59/59** | **3/3** | 18 |
| Sonnet 4.6 | tdes_full | **59/59** | **59/59** | **59/59** | **3/3** | 18 |

*Monolithic baseline (all prior experiments): Level-4 = 0/N solved.*

---

## Generation Trajectory

**Sonnet `single_agent_30`** (most efficient path):
```
Gen 1 (round 1): seed 2/59 → 5 targeted LLM calls (one per module) → 59/59 SOLVED
Total: 6 calls, ~90 seconds
```

**Sonnet `tdes_full`** (representative):
```
Gen 1: 2/59 (pop union 2)
Gen 2: 58/59 (pop union 59)  ← all modules solved by gen 2
Gen 3: 59/59 SOLVED (stagnation check fires post-solve)
Total: 18 calls
```

**Haiku `tdes_full` seed 1** (only Haiku solve):
```
Gen 1: 2/59  (pop union 2)
Gen 2: 38/59 (pop union 43)  ← 4/5 modules solved
Gen 3: 59/59 SOLVED          ← gen 3 mutation cracked fpm_round_pack
Total: 22 calls, xo_attempts=2, xo_accepted=0
```

**Haiku `single_agent_30`** (stuck pattern):
```
Round 1: 4/5 modules solved → 26/59 (fpm_round_pack = 0/8, 13 consecutive 
         "no full rewrite" errors for fpm_round_pack) → 26/59 final
```

---

## Module First-Solved Generation

Every run, both models, all conditions:

| Module | Gen solved |
|---|---|
| fpm_multiply (sign XOR, product) | **Gen 1** |
| fpm_special (NaN/Inf/Zero priority) | **Gen 1** |
| fpm_unpack (field extraction, flags) | Gen 2 |
| fpm_normalize (shift, guard/sticky) | Gen 2 |
| fpm_round_pack (R-N-E, signed exp) | Gen 2 (Sonnet) / Gen 3 or never (Haiku) |

---

## Crossover Activity

| Model | Condition | Seed 0 | Seed 1 | Seed 2 |
|---|---|---|---|---|
| Haiku | tdes_full | 0 att / 0 acc | 2 att / 0 acc | 2 att / 0 acc |
| Sonnet | tdes_full | 0 att / 0 acc | 0 att / 0 acc | 0 att / 0 acc |

Crossover was *attempted* in Haiku seeds 1 and 2 (complementary coverage did emerge)
but no child passed the strict-superset gate. Sonnet solved so fast (gen 1–2) that
the population never developed complementary coverage.

---

## Key Findings

### 1. Level-4 solved for the first time by evolutionary synthesis

`fp_mult_pipeline` — a full IEEE-754 pipeline with round-to-nearest-even,
NaN/Inf/Zero/overflow/underflow handling — was never solved monolithically.
Decomposition into 5 sub-modules with targeted unit testbenches makes it tractable:

- **Sonnet: 9/9 solved** (100%, all three conditions)
- **Haiku: 1/9 solved** via TDES population (0/3 single_agent, 0/3 no_crossover)

### 2. Decomposition + targeted CEGIS is the critical enabler

Sonnet's `single_agent_30` solved 3/3 in **6 LLM calls** — just one round of 
per-module mutations. The hierarchical unit tests give Sonnet exactly the feedback
it needs: when `fpm_round_pack` fails, the testbench shows which of the 8 unit
cases failed and why (expected overflow flag, got underflow; expected +Inf, got 0).
No population, no crossover — targeted feedback is sufficient.

### 3. The hard module: fpm_round_pack (signed exponent arithmetic)

The blocking test for Haiku in all non-TDES conditions:
```
sys_underflow: min_normal × min_normal → expected 0x00000000, got 0x7F800000
  root cause: raw_exp = 1+1-127 = -125 wraps to 899 in 10-bit unsigned
  Haiku bug: checks (exp >= 255) first → 899 >= 255 = TRUE → overflow, not underflow
  Sonnet: correctly checks exp_final[9] (sign bit) → detects -125 → underflow
```

Haiku also fails to produce any valid `fpm_round_pack` rewrite in `single_agent_30`
(13 consecutive "no full rewrite" errors), suggesting the module is at the edge of
Haiku's Verilog generation capability.

### 4. Population diversity, not crossover grafting, explains Haiku tdes_full > others

`tdes_full` 1/3 vs `tdes_no_crossover` 0/3 is potentially stochastic, but mechanistically:
- The population gives 5 independent candidates, each with separate mutation context
- The diverse schedule rotates which module each candidate repairs
- Across multiple candidates × multiple generations, there are many independent shots
  at the hard `fpm_round_pack` module
- One candidate eventually got it right (gen 3, seed 1) — this luck could have happened
  in tdes_no_crossover too with more seeds

In contrast, `single_agent_30` serially retries only `fpm_round_pack` after the other
4 are solved, burning all 8 rounds on the same module, and Haiku can't produce a valid
rewrite even 13 times in a row.

Crossover attempted (seeds 1,2: 2 attempts each, 0 accepted) but didn't produce the
solve. The solve came from a mutation.

### 5. Efficiency comparison across conditions (Sonnet)

| Condition | Calls to solve (med) | Wall time |
|---|---|---|
| single_agent_30 | **6** | ~90s |
| tdes_full | 18 | ~6 min |
| tdes_no_crossover | 18 | ~6 min |

Sonnet's `single_agent_30` is 3× more LLM-call efficient than TDES because it
completes in one round (5 modules × 1 call + ~1 retry), while TDES evaluates a
population of 6 candidates per generation. For a capable model, the population
overhead is pure cost with no benefit. The TDES mechanism is most valuable when
the per-module solve probability is <1 (i.e., Haiku), where population diversity
provides multiple independent tries.

---

## Interpretation: Decomposition as a Capability Multiplier

The results reveal a **capability-dependent mechanism hierarchy**:

```
                    Sonnet (high capability)
single_agent_30:    3/3 solved, 6 calls   ← decomposition alone is sufficient
tdes_no_crossover:  3/3 solved, 18 calls  ← population adds overhead, not benefit
tdes_full:          3/3 solved, 18 calls  ← crossover never fires (solves too fast)

                    Haiku (low capability)
single_agent_30:    0/3 solved, stuck at 26/59  ← fpm_round_pack walls it
tdes_no_crossover:  0/3 solved, stuck at 55-58/59  ← close but blocked
tdes_full:          1/3 solved             ← population diversity provided extra shots
```

The decomposition eliminates the exponential complexity penalty of monolithic
synthesis (Wolf et al. 2024). But it doesn't increase per-module pass rates — it
just isolates failures so that partial solutions (correct in 4/5 modules) can exist
and be selected in a population.

At Sonnet's capability level, P(correct per module | one LLM call) ≈ 1.0, so a
single round of decomposed targeted feedback solves everything. The TDES population
mechanism is redundant.

At Haiku's capability level, P(correct for fpm_round_pack) is low but non-zero.
Population × diversity × generations gives enough independent attempts that one
eventually succeeds. This is a genuine (if modest) benefit of the population mechanism.

---

## Comparison to Literature

| Method | Target | Solve Rate |
|---|---|---|
| EvolVE (Hsin et al. Jan 2026) | RTLLM v2 (Level 1-2 designs) | 92% |
| REvolution (Rashid et al. 2025) | VerilogEval (mixed levels) | 87.1% |
| Monolithic TDES (prior work) | ArchXBench Level 3-4 | 0/N |
| **Decomposed TDES + Sonnet** | **ArchXBench Level 4** | **100% (3/3)** |
| **Decomposed TDES + Haiku** | **ArchXBench Level 4** | **33% (1/3)** |

Prior evolutionary methods target Level 1-2 benchmark designs. This is the first
demonstration of evolutionary synthesis on ArchXBench Level 4, enabled by the
combination of:
1. Manual decomposition into 5 independent sub-modules
2. Hierarchical test suite with per-module UNIT testbenches
3. CEGIS feedback routing to the specific failing module

---

## What's Next

1. **fp_adder_pipeline (L4)**: Does the same approach generalize? The adder has
   alignment + cancellation — a 6-module decomposition.

2. **Automatic decomposition**: Can an LLM decompose an arbitrary L4 design spec
   into sub-modules automatically? This would make the approach fully end-to-end.

3. **Larger Haiku budget**: pop=8, gens=12 with 5 seeds to get a cleaner solve rate
   estimate (is it really ~33% per seed, or was seed 1 a lucky outlier?).

4. **Crossover tuning**: Relax the strict-superset gate to accept improvements by
   partial score to see if Haiku crossover can contribute directly.
