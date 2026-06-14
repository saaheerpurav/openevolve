# TDES-Repair: automated bug repair via complementary-coverage crossover

An **additive** TDES layer (sibling of `tdes/fpga/` and `tdes/combopt/`) that
applies TDES to real-world **Python software bug repair** — the SWE-bench
setting. The base TDES controller / selection / crossover / memory are reused
**unchanged** (duck-typed against the suite). Only the test runner and mutation
prompts are swapped.

The novel mechanism this layer exercises: two partial repairs targeting
**different** bugs in the same codebase pass non-overlapping test subsets, making
them natural inputs for complementary-coverage crossover. Crossover grafts the
blockmatrix fix from one candidate into the point-velocity candidate (or vice
versa), producing a fully-repaired codebase that neither parent reached alone.

## What is evolved

A candidate is a **multi-module Python codebase** `{module_name: source}`. For
`sympy_swe` the two evolving modules are:

* `point` — `sympy/physics/mechanics/point.py`: the `vel()` method raises
  `ValueError` whenever velocity is not cached, even when it can be derived via
  BFS over `_pos_dict`. The fix is to auto-compute velocity by walking the
  kinematic chain.
* `blockmatrix` — `sympy/matrices/expressions/blockmatrix.py`: `BlockMatrix._entry()`
  uses `(i < numrows) != False` to locate the block containing index `i`. Because
  `i < numrows` is a SymPy `StrictLessThan` relational (not a Python bool), the
  check is always `True`, so the loop always breaks on the first block. The fix is
  to call `.simplify()` on the comparison, fall back to `MatrixElement(self, i, j)`
  for unresolvable symbolic cases, and break unconditionally on the last block.

An LLM mutator (`CodexMutator`, `gpt-5.5` via the Codex CLI) rewrites one module
at a time given CEGIS feedback: `(description, failing input, error)` per failing
test. Test source is withheld to prevent Goodharting.

## Hierarchical tests (the `TestVector` levels)

The `sympy_swe` suite contains 9 tests:

* **UNIT (7)** — 4 regression tests for `vel()` correctness (multi-hop kinematic
  chains, unset-velocity error) + 3 regression tests for `BlockMatrix._entry()`
  correctness (symbolic indexing, last-block, numeric). A point-only fix scores
  4/9; a blockmatrix-only fix scores 3/9. The two pass sets are disjoint.
* **INTEGRATION (1)** — a mixed test exercising both modules together (a dynamic
  system whose equations require both correct velocity propagation and correct
  block-matrix element access).
* **SYSTEM (1)** — end-to-end: the full SymPy mechanics pipeline returns the
  correct equations of motion, gated on both modules being simultaneously correct.

A fully-repaired candidate scores 9/9 (system 1, integration 1, unit 7).

## Why complementary-coverage crossover fires here

Under **lexicase selection** (implemented in `repair/ablation.py`), test order is
shuffled independently per survivor slot. A candidate that passes blockmatrix
tests 5–7 survives in slots where those tests appear first, even if another
candidate passes more tests in total. Both partial repairers coexist in the
survivor set. Complementary-coverage crossover then detects the non-overlapping
pass sets, grafts the blockmatrix module from the 3/9 candidate into the 4/9
candidate, and accepts the child only if it achieves a strict superset — in
practice 9/9 in one step.

**Empirical result (seed 0, `gpt-5.5` via Codex, `pop_size=8`):**
```
Gen 1: 8 LLM calls → best 0/9
Gen 2: population union 7/9 (point-fixed 4/9 + blockmatrix-fixed 3/9 in survivors)
       crossover_attempts=4, crossover_successes=4, all produce 9/9
Gen 3: solved (9/9), regression_rate=0.0, llm_calls_to_solution=8
```

## Running

```bash
# single verification run (seed 0, tdes_full only)
python -m openevolve.tdes.repair.experiments.run_repair \
    --tasks sympy_swe --conditions tdes_full --seeds 0 \
    --config openevolve/tdes/repair/configs/sympy_swe.yaml \
    --out results/repair_verify

# full ablation (4 conditions × 3 seeds)
python -m openevolve.tdes.repair.experiments.run_repair \
    --tasks sympy_swe \
    --conditions tdes_full tdes_no_crossover unconstrained_evo single_shot \
    --seeds 0 1 2 \
    --config openevolve/tdes/repair/configs/sympy_swe.yaml \
    --out results/repair_final
```

The Codex CLI must be authenticated (`codex` available on `PATH`, ChatGPT OAuth
session active). No `OPENAI_API_KEY` needed — the mutator calls `codex` as a
subprocess.

## Four ablation conditions

| Condition | Selection | Crossover | Purpose |
|---|---|---|---|
| `tdes_full` | Lexicase | Complementary-coverage | Primary method |
| `tdes_no_crossover` | Lexicase | Disabled | Isolates crossover contribution |
| `unconstrained_evo` | Lexicase | Random (unconditional) | Baseline B |
| `single_shot` | — | — | Single LLM call, no loop |

## Structure

```
repair/
  ablation.py          # RepairTDESController (lexicase selection, metrics)
  configs/
    sympy_swe.yaml     # pop_size=8, max_generations=6, window_size=3
  experiments/
    run_repair.py      # entry point; writes one JSON per (condition, task, seed)
  mutators/            # CodexMutator wrapping the Codex CLI
  tasks/
    sympy_task1/       # sympy_swe: point.py + blockmatrix.py + 9-test suite
    requests_swe/      # requests library SWE task
    pipeline/          # data-pipeline repair task
    api/               # REST API repair task
    cicd/              # CI/CD config repair task
```

**Do not modify base `tdes/*` files** — extend via subclass/composition, as this
layer does.
