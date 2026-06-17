# ArchXBench Auto-Decompose Direction

## Why L4 Matters

ArchXBench Level-4 is where direct monolithic LLM RTL synthesis has been failing in our experiments. Frontier models could make partial progress on easier RTL tasks, but Level-4 monolithic designs were not solved by direct prompting or iterative repair: the integrated RTL still failed the original system testbench.

This matters because Level-4 tasks require coordinated floating-point behavior, special cases, normalization, rounding, overflow/underflow handling, and module-level consistency. They are not simple syntax-fix problems.

## Core Idea

The new paper direction is **Auto-Decompose-Then-Evolve for hard RTL synthesis**.

The pipeline:

1. Give the LLM the ArchXBench design spec and original system testbench.
2. Ask it to generate a modular scaffold: submodule interfaces, reference implementations, weak seeds, unit tests, and a top wrapper.
3. Gate the scaffold:
   - composed reference must pass the original ArchXBench system testbench
   - generated unit tests must be nontrivial: reference passes, seed fails
4. Run TDES / repair over the generated module scaffold.
5. Count final success only against the original ArchXBench system testbench.

Generated unit tests are search scaffolding, not the benchmark judge.

## Current L4 Result

We tested this on the hard ArchXBench Level-4 `fp_mult_pipeline` design.

Prior monolithic LLM attempts had not solved this Level-4 design in our setup. The new auto-decompose pipeline did.

The accepted auto-generated scaffold had five modules:

- `fp_mult_decode`
- `fp_mult_special`
- `fp_mult_multiply`
- `fp_mult_normalize`
- `fp_mult_round`

The scaffold passed both gates:

- reference passed original system test: `1/1`
- generated training suite: reference `6/6`, seed `0/6`

Stage 2 results on the accepted scaffold:

| Method | Seeds | Original System Passes | Notes |
|---|---:|---:|---|
| `tdes_full` | 3 | 3/3 | Passed L4 system test in 12-13 Codex calls |
| `tdes_no_crossover` | 3 | 1/3 | Weaker in this small run |
| `single_agent` | 3 | 2/3 | Catches up with larger 8-round budget |

So the important result is:

**The auto-decompose pipeline passed the original ArchXBench Level-4 system testbench for `fp_mult_pipeline`.**

## Honest Interpretation

This does not yet prove that crossover is the main contribution.

Important caveat:

- `tdes_full` passed `3/3`, but accepted crossover attempts were `0`.
- The likely contribution is auto-decomposition plus generated verification scaffolding, population search, and iterative repair pressure.
- Crossover should be treated as an ablation component unless future data shows accepted crossover is actually responsible.

## Current Claim

The honest claim right now:

**Auto-generated modular verification scaffolds can turn an ArchXBench Level-4 RTL task that direct monolithic LLM repair failed to solve into a solvable search/repair problem, while preserving the original ArchXBench system testbench as the final judge.**

## What Remains

To become AAAI-grade evidence, this needs:

- more ArchXBench Level-4 designs
- at least 5 seeds per condition
- monolithic LLM baselines under fair budgets
- auto-decompose + single-agent baseline
- auto-decompose + no-crossover baseline
- auto-decompose + full TDES
- ablations separating decomposition, generated tests, population search, and crossover
