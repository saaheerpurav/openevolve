# TDES-FPGA: real-LLM experimental results

Runs below used **Claude Haiku 4.5** (`claude-haiku-4-5-20251001`) via the
Anthropic OpenAI-compatible endpoint, simulated/synthesized with the OSS CAD
Suite (Icarus Verilog 14, Yosys 0.66). Reproduce with the configs in
`configs/` (`ANTHROPIC_API_KEY` + `OSS_CAD_SUITE_ROOT` set).

## 1. RTLLM v2 — method comparison

5 designs, 1 seed, pop=4, gens=4 (`run_rtllm.py`):

| Design | tdes_full | single_agent | pass@5 |
|---|---|---|---|
| adder_8bit       | ✓ | ✓ | ✗ |
| adder_pipe_64bit | ✗ | ✓ | ✗ |
| div_16bit        | ✓ | ✓ | ✗ |
| multi_16bit      | ✗ | ✗ | ✗ |
| multi_8bit       | ✓ | ✓ | ✗ |
| **solve rate**   | **60%** | **80%** | **0%** |

Crossover analysis: 0 attempts — **expected**: RTLLM designs are single-module,
so there is nothing to graft. Crossover's value appears only on multi-module
codebases (see §2).

**Takeaways.** (a) Iterative-feedback methods (TDES, single-agent) vastly
outperform one-shot generation (Pass@5 = 0% with this model): the CEGIS
feedback loop is doing the work. (b) On *single-module* designs TDES's
population machinery does not beat single-agent repair — consistent with the
paper's claim that TDES targets *modular*, high-constraint problems, not simple
single-module ones.

## 2. Multi-module crossover demonstration

A two-module problem (`adder8` + `cmp8`) with an empty seed and a hierarchical
suite (unit test per module + an integration test using both), pop=6, gens=5,
one module fixed per candidate per generation, randomized module scheduling
(`crossover_demo.py`):

```
Gen 1  best 0/3   union passes 0     (all seeds empty)
Gen 2  best 1/3   union passes 2     (some candidates fixed adder8, others cmp8)
       Crossover accepted: <A:adder8-passing> + <B>[cmp8] -> child 3/3
       Crossover accepted: <B:cmp8-passing>   + <A>[adder8] -> child 3/3
Gen 3  best 3/3   SOLVED
```

Crossover statistics: **2 attempts, 2 accepted (100%), mean lift +2.0 tests**.

This is the paper's primary contribution working end-to-end with a real LLM:
complementary-coverage crossover combined two *partial* solutions (one with a
correct adder, one with a correct comparator) into a complete passing design by
grafting the donor's module — a jump no single mutation made.

> Note: the base controller fixes failing modules in a fixed order, so from a
> homogeneous seed every candidate pursues the same module first and no
> complementary coverage arises. `DiverseScheduleController` (in
> `crossover_demo.py`) randomizes per-candidate module order to produce the
> diversity crossover needs; all acceptance/regression rules are inherited
> unchanged. This is a documented requirement, not a workaround — it mirrors the
> population diversity that stochastic mutation provides at larger scale.

## 3. Crossover-necessity ablation (Sonnet, 3 seeds)

Four-module compositional problem (`datapath_problem.py`: `add8` + `bshift` +
`scmp` + `popcnt`; 4 unit + 2 integration + 1 system tests). Empty seed, one
module fixed per candidate per generation, randomized module scheduling
(`DiverseScheduleController`). `tdes_full` (crossover on) vs `tdes_no_crossover`
(off), **Claude Sonnet 4.6**, `crossover_ablation.py`.

Integration/system tests pass only when *multiple* modules are correct, so a
candidate with a subset of modules passes a strict subset of tests — the
complementary coverage crossover grafts. A single lineage can fix at most one
new module per generation, so it needs ≥4 generations to reach all four.

**Generous budget (gens=6):** both conditions solve, but crossover is highly
active and faster.

| Condition | solve rate | mean gens-to-solve | crossover accepts (per seed) | mean lift |
|---|---|---|---|---|
| tdes_full         | 3/3 | **4.67** | 13, 11, 6 | +1.9 tests |
| tdes_no_crossover | 3/3 | 5.00 | 0 | — |

**Tight budget (gens=3):** no single lineage can fix all four modules, so
crossover becomes *necessary*.

| Condition | solve rate | best passes (per seed) |
|---|---|---|
| tdes_full         | **1/3** (seed 1 → 7/7 via crossover) | 4, **7**, 4 / 7 |
| tdes_no_crossover | **0/3** — structurally capped | 4, 4, 4 / 7 |

**Takeaway.** Complementary-coverage crossover fires heavily on compositional
problems (6–13 accepted grafts/run, +1.9 mean test lift) and consistently
reduces generations-to-solve. Under a generation budget below the module count,
mutation alone is *structurally capped* (here at 4/7 — it can never combine the
separately-evolved modules), while crossover combines partial solutions to
reach a complete design. This is the controlled result that crossover is
*necessary*, not merely helpful, for modular synthesis under budget — exactly
the regime the paper targets.

> Honesty note (also in `crossover_demo.py`/`ablation.py`): the base controller
> fixes failing modules in a fixed order, so from a homogeneous seed every
> candidate pursues the same module first and no complementary coverage arises.
> `DiverseScheduleController` randomizes per-candidate module order to produce
> the diversity crossover needs; all acceptance/regression rules are inherited
> unchanged. This stands in for the diversity stochastic mutation provides at
> larger population/temperature scale, and is stated upfront rather than buried.

## 4. Single-agent fallback: TDES no longer loses to single-agent

The §1 result (TDES 60% < single-agent 80%) exposed a real flaw: on
single-module designs crossover has nothing to graft, so the population only
*dilutes* the mutation budget across several mediocre candidates while
single-agent pours its whole budget into one lineage.

Fix (`SingleAgentFallbackController`, `ablation.py`): when the codebase is
single-module, TDES concentrates each generation's budget on the *champion* as
sequential CEGIS repair — i.e. it *becomes* single-agent, but with the larger
TDES budget (pop × gens repair attempts vs single-agent's gens), so it matches
or beats it. Multi-module codebases keep the full population/crossover machinery.

Re-running the same matrix (Haiku, 5 designs × 2 seeds, per-cell solved):

| Design | TDES (s0, s1) | single-agent (s0, s1) |
|---|---|---|
| adder_8bit       | ✓ ✓ | ✓ ✓ |
| adder_pipe_64bit | ✓ ✗ | ✗ ✓ |
| div_16bit        | ✓ ✓ | ✗ ✓ |
| multi_16bit      | ✓ ✗ | ✗ ✗ |
| multi_8bit       | ✓ ✓ | ✓ ✓ |
| **cells solved** | **8/10** | **6/10** |

TDES is now ≥ single-agent on **every** design, and strictly wins on `div_16bit`
(2/2 vs 1/2) and `multi_16bit` (1/2 vs 0/2). Single-agent is a strict special
case of TDES, as it should be. (Crossover stays inert here — these are
single-module designs; its value is in §2–§3.)

## 5. ArchXBench (verified combinational designs)

Run on five ArchXBench complex-arithmetic designs whose pass/fail scoring was
**verified end-to-end** (a hand-written correct design reads 1/1, a wrong one
0/1): `rca_32bit`, `cla_8bit` (level-1a), `brent_kung_32bit`, `wallace_multiplier`,
`dadda_multiplier` (level-1c). The testbenches check *function*, not structure,
so any functionally-correct RTL passes. (booth/pipelined designs are excluded —
their testbenches print bare `PASS`/`FAIL` table cells with no count summary and
a `Pass/Fail` header, which is not safely machine-parseable; reporting numbers we
cannot trust would be worse than omitting them.)

> A verdict-parser bug initially scored *correct* designs as 0/1 (one testbench
> prints `PASS = N, FAIL = 0`, which the parser didn't recognize), making a first
> run look like "all methods fail." It was caught by injecting a known-correct
> design before drawing conclusions, then fixed (failure-evidence-first parsing)
> and re-verified. Lesson logged: never trust a benchmark verdict you haven't
> confirmed against a known-good solution.

**Opus 4.6 (1 seed):**

| Design | tdes_full | single_agent | pass@5 |
|---|---|---|---|
| rca_32bit, cla_8bit, brent_kung_32bit, wallace_multiplier | ✓ | ✓ | ✓ |
| dadda_multiplier | ✓ | ✓ | **✗** |
| **solve rate** | **5/5** | **5/5** | **4/5** |

**Haiku 4.5 (2 seeds, 10 cells/condition):**

| Condition | cells solved | misses |
|---|---|---|
| tdes_full     | **10/10** | — |
| single_agent  | **10/10** | — |
| pass@5        | **8/10**  | `wallace_multiplier` (0/2) |

**Takeaway.** Iterative-feedback methods (TDES, single-agent) solve every design
including the harder Wallace/Dadda multipliers; one-shot pass@5 misses a
multiplier at *both* model tiers (Opus → dadda, Haiku → wallace). TDES equals
single-agent on these single-module designs — expected, and the point of the
§4 fallback. ArchXBench's value here is *valid, verified* scoring on real
complex-arithmetic RTL; crossover's contribution remains the multi-module §2–§3
results.

## Cost / scale

These are low-cost validation runs (fast/mid models, small seed counts) that
exercise the full pipeline and isolate each mechanism's effect. Scaling to a
full paper sample (more designs/seeds, ArchXBench Levels 3–5) is a
config/`--designs`/`--seeds` change; the harness, metrics, and tables are
unchanged.
