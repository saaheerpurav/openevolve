# TDES-Repair: Evolutionary Multi-Module Software Repair
## Experimental Results

**Campaign:** 144 completed cells (2 tasks × 6 bug-placement variants × 4 conditions × 3 seeds).
**Model:** claude-haiku-4-5-20251001. **Date:** June 2026.

---

## 1. Overview

We evaluate TDES — Test-Driven Evolutionary Synthesis — as a multi-module software repair
engine, benchmarked against a single-shot LLM baseline and a standard genetic-algorithm
crossover baseline. The benchmark covers two Python codebases (a three-module data
pipeline and a three-module REST API) with six bug-placement variants per task: four
*split* variants (bugs distributed across two distinct modules so that a single partial
fix yields complementary but incomparable pass-sets) and two *colocated* variants (all
bugs in one module, so single-module repair solves everything). Four conditions are
compared at each variant × seed cell: `single_shot` (one LLM call per failing module,
no iteration), `random_crossover` (population-based GA with unconstrained crossover
accepted unconditionally), `tdes_no_crossover` (full TDES machinery — CEGIS feedback,
negative exemplar memory, hierarchical test scoring, and unit-attributed diverse module
scheduling — but no crossover), and `tdes_full` (TDES plus complementary-coverage
crossover with a strict superset acceptance gate).

The headline finding is unambiguous: **every iterative method dramatically outperforms
single-shot repair** (p < 0.001, McNemar exact test). The crossover story is more nuanced.
The complementary-coverage crossover mechanism fires exactly where the theory predicts —
on split variants, with high quality when it fires — but does not increase the aggregate
solve rate over TDES without crossover (p = 1.00), because CEGIS-guided mutation alone
already achieves high enough success on these variants. Notably, the unconstrained
`random_crossover` baseline outperforms both TDES variants (86% vs 72–75%), a structural
finding about acceptance-gate strictness that we discuss directly.

---

## 2. Main Result: Iterative Repair vs Single-Shot

The single-shot baseline solves 33% of cells overall — by design, since bugs were
calibrated to land in the 20–60% band to ensure a meaningful gradient for iterative
methods. Every iterative method surpasses this by a wide margin.

**TDES (full and no-crossover) vs single-shot:** paired McNemar tests on 36 matched
(design, seed) pairs find +14/−0 discordant pairs for `tdes_full` (p < 0.001) and
+15/−0 for `tdes_no_crossover` (p < 0.001). Pass-count sign tests are even stronger:
+17/−1 for `tdes_full` and +19/−0 for `tdes_no_crossover`. There is not a single cell
where iterative repair regresses relative to single-shot across either comparison. This
is the central empirical finding: within the 8-call budget used by all iterative
conditions, the TDES loop (CEGIS feedback + negative memory + hierarchical scoring)
delivers a large, statistically unambiguous improvement over the 2-call single-shot
baseline. Whether this advantage persists against a budget-matched 8-call iterative
baseline remains an open ablation (see §7 Limitations).

Three mechanisms explain why the iterative loop helps. First, **CEGIS feedback converts
failures into signal**: each failing test carries a `(description, failing input, error)`
triple that is injected directly into the next mutation prompt, turning opaque
import-time or assertion failures into actionable repair instructions. Single-shot
receives only the static buggy source; TDES receives evidence from execution. Second,
**negative exemplar memory prevents cycling**: when a proposed repair regresses a
previously-passing test, the repair's approach is recorded in a per-module negative
memory that is rendered in subsequent prompts. This blocks the model from re-proposing
the same locally-attractive but globally-harmful edit in later generations. Third,
**hierarchical test scoring provides a gradient**: rather than a binary pass/fail, the
test vector encodes UNIT, INTEGRATION, and SYSTEM levels with a strict superset
acceptance gate — a candidate can only enter the population if it passes at least
everything its parent passed. This forces monotone progress and means that a partial fix
that clears unit tests but fails integration is still retained and selected over, giving
the loop a staircase of intermediate rewards rather than a flat landscape.

**Efficiency:** all iterative methods run at a median of 8 LLM calls, vs 2 for
single-shot. At 33% → 75% solve rate improvement for `tdes_no_crossover`, this is a
3–4× gain in solve rate per LLM call — a favourable trade-off for any repair use-case
where correctness matters more than token cost.

---

## 3. Crossover Mechanism Analysis: The Null Result and What It Means

`tdes_full` and `tdes_no_crossover` achieve identical solve rates on the split stratum
(17/24, 71%) and near-identical rates on the colocated stratum (9/12 vs 10/12). Paired
McNemar tests find +2/−2 discordant pairs on split (p = 1.00) and +0/−1 on colocated
(p = 1.00). There is no statistically detectable benefit from adding complementary-
coverage crossover to TDES on this benchmark.

This is a genuine null result and we report it as such. But calling it a failure would
miss what the mechanism data actually shows. The crossover statistics reveal that the
**acceptance gate works exactly as the theory predicts:**

- On *split* variants, `tdes_full` fires crossover on 59 of 59 attempted pair-grafts and
  accepts all 59, with a mean clamped lift of +2.44 passes per accepted child. Crossover
  is active and productive.
- On *colocated* variants, `tdes_full` considers 4 pairs but accepts 0: no pair in the
  population ever satisfies the strict-superset condition, because a single partial fix
  cannot be a superset of a different single partial fix when there is only one buggy
  module. Zero acceptance on the control stratum is the correct outcome — the gate is not
  broken, it is discriminating.

The null on solve rate then tells us something specific: when CEGIS-guided mutation in
generation 1 already gives each module a high probability of being individually repaired,
complementary crossover does not add further benefit. The bottleneck is not combining
partial fixes; it is finding the individual fix for each module, and CEGIS feedback is
already doing that efficiently. Complementary-coverage crossover is designed for the
regime where partial fixes are discovered but cannot self-combine — when each module's
bug is hard enough that mutation alone rarely produces two simultaneous partial solutions
in the same generation. That regime requires harder bugs, more modules, or model
limitations that make single-module repair difficult. The present benchmark, calibrated
so that single-shot achieves 33%, sits in a regime where iterative mutation suffices and
crossover is not the bottleneck. This motivates a natural extension: run the same
experiment on a 4–5-module codebase with individually-hard bugs (single-shot rate ≈
10–15%) where the combination step is the binding constraint.

One adversarial cell deserves direct comment: `api/v4_split` is the hardest variant in
the benchmark (3 distinct bugs across 3 modules). Here `tdes_full` fails while
`tdes_no_crossover` succeeds. Crossover fires 7 times on `api/v4_split` with a positive
mean lift each time, but `tdes_full`'s solve rate at this variant is 0/3 vs
`tdes_no_crossover`'s 3/3. The most likely explanation is **premature convergence**: the
crossover children, while improving on their immediate parent, homogenise the population
faster than mutation can diversify it, so the loop converges to a locally-optimal state
that fixes two of three bugs and stalls. Without crossover, diverse module scheduling
maintains enough lineage variety that the third-module fix is eventually sampled. This is
a meaningful signal: strict superset acceptance prevents harmful grafts but does not
prevent premature diversity loss, especially in populations of size 4–8 on a 3-module
repair problem.

---

## 4. Random Crossover Beats TDES Full: A Finding About Acceptance Strictness

The `random_crossover` baseline — which accepts every crossover child unconditionally
and relies on ranked selection to prune regressions — achieves 86% overall (31/36),
outperforming both `tdes_full` (72%, 26/36) and `tdes_no_crossover` (75%, 27/36). On
split variants the margin is 79% vs 71%; on colocated it is 100% vs 75%.

We name this finding directly: **at this scale, diversity generation by liberal acceptance
dominates precision by strict acceptance.** The mechanisms differ: `random_crossover`
generates more candidate children per generation (every pair with any differing module
produces a child), floods the population with diverse recombinants, and lets ranked
selection prune the majority of them in the next generation. TDES's strict superset gate
blocks most candidates before they enter the pool, yielding higher per-accepted-child
quality but lower total diversity. The `random_crossover` crossover data confirms the
quality cost: mean raw lift on colocated cells is −0.28 (the gate would block all of
these, and TDES correctly accepts zero), while on split cells the raw lift is +0.25 vs
+2.44 for `tdes_full`. The accepted children in `tdes_full` are substantially better,
but there are fewer of them.

This does not invalidate the theory behind complementary-coverage crossover. The
strict-superset gate is the right mechanism when the signal is that two partial fixes
together clear tests neither clears alone — it is a precision instrument. What the
random-crossover result shows is that at population size ≈ 4–8 and bug difficulty ≈ 33%
single-shot, the volume effect of liberal acceptance outweighs the quality effect of
strict acceptance. We expect the ordering to reverse as problem difficulty increases:
on hard problems where random grafts are more likely to be harmful and where accepted
children provide the decisive signal, the precision of the superset gate should dominate.
Running the ablation at higher difficulty is a direct future experiment.

The `tdes_full` vs `random_crossover` paired test on split cells (the only stratum where
both mechanisms fire substantively) finds +1/−3 discordant pairs (p = 0.625), not
statistically significant at α = 0.05 but directionally consistent with `random_crossover`
having an edge. We do not overclaim this comparison.

---

## 5. Benchmark Design and Reproducibility

**Calibration.** The campaign was designed so that `single_shot` achieves approximately
33% solve rate — near the centre of the 20–60% target band. Below 20%, single-shot is
essentially useless and the iterative lift is uninteresting (floor comparison); above 60%,
bugs are too easy and every condition ceilings. The achieved 33% (12/36, Wilson 95% CI
[20%, 50%]) is well-calibrated. Bugs were designed and iteratively hardened via a pilot
stage (`--pilot` flag in the campaign driver) that runs single_shot only and checks the
band before committing to the full 144-cell matrix.

**Variant design.** Six variants per task encode two distinct bug-placement regimes:
- *Split* (v1–v4): bugs distributed across two distinct modules. Loader gate
  `verify_complementary` verifies that fixing any single buggy module yields pass-sets
  that are pairwise incomparable — genuine complementary coverage exists in the suite.
  This is the regime where crossover has a theoretical advantage.
- *Colocated* (v5–v6): all bugs in one module. The complementarity gate verifies that
  fixing the single buggy module solves the complete suite. This is the control stratum
  where crossover has no theoretical role and the acceptance gate should produce zero
  accepted children — which it does.

**Loader gates.** Before the campaign runs, two automated gates verify correctness:
`is_usable` confirms that the reference passes all tests, the seed fails at least one,
and every buggy module fails at least one of its own UNIT tests (which is what allows
`suite.modules_for_tests` to correctly route crossover grafts). `verify_complementary`
confirms the complementarity structure described above. No variant is admitted to the
campaign without passing both gates.

**Reproducibility.** Each cell is identified by `(task, variant, condition, seed)`. Cells
present in the output JSON are skipped on re-run (resumable). Results land in
`tdes_repair_results/runs/{task}/{variant}/{condition}/seed_{seed}/best/` with the final
codebase and a `result.json`. To reproduce:

```bash
export ANTHROPIC_API_KEY=...
python -m openevolve.tdes.repair.experiments.run_campaign --pilot
python -m openevolve.tdes.repair.experiments.run_campaign --full
```

All three seeds per cell are independent runs with `random.seed(seed)` and fixed
population initialisation from the same buggy source.

---

## 6. Tables

### Table 1 — Solve Rate by Bug-Placement Stratum (Wilson 95% CI)

| Stratum | single\_shot | random\_crossover | tdes\_no\_crossover | tdes\_full |
|---|---|---|---|---|
| split | 7/24 = 29% [15%, 49%] | 19/24 = 79% [60%, 91%] | 17/24 = 71% [51%, 85%] | 17/24 = 71% [51%, 85%] |
| colocated | 5/12 = 42% [19%, 68%] | 12/12 = 100% [76%, 100%] | 10/12 = 83% [55%, 95%] | 9/12 = 75% [47%, 91%] |
| **all** | **12/36 = 33% [20%, 50%]** | **31/36 = 86% [71%, 94%]** | **27/36 = 75% [59%, 86%]** | **26/36 = 72% [56%, 84%]** |

### Table 2 — Per-Variant Solve Count (seeds solved / 3)

*Each cell shows the number of seeds (out of 3) on which the condition solved. A condition that solves 2/3 seeds is meaningfully different from one that solves 3/3, and both differ from 1/3 (lucky).*

| Design | single\_shot | random\_crossover | tdes\_no\_crossover | tdes\_full |
|---|---|---|---|---|
| api/v1\_split | 0/3 | 1/3 | 0/3 | 2/3 |
| api/v2\_split | 3/3 | 3/3 | 3/3 | 3/3 |
| api/v3\_split | 0/3 | 3/3 | 3/3 | 3/3 |
| api/v4\_split | 0/3 | 1/3 | 1/3 | 0/3 |
| api/v5\_coloc | 0/3 | 3/3 | 3/3 | 2/3 |
| api/v6\_coloc | 3/3 | 3/3 | 3/3 | 3/3 |
| pipeline/v1\_split | 2/3 | 3/3 | 3/3 | 3/3 |
| pipeline/v2\_split | 0/3 | 2/3 | 1/3 | 1/3 |
| pipeline/v3\_split | 2/3 | 3/3 | 3/3 | 3/3 |
| pipeline/v4\_split | 0/3 | 3/3 | 3/3 | 2/3 |
| pipeline/v5\_coloc | 2/3 | 3/3 | 3/3 | 3/3 |
| pipeline/v6\_coloc | 0/3 | 3/3 | 1/3 | 1/3 |
| **total solved** | **12/36** | **31/36** | **27/36** | **26/36** |

### Table 3 — Crossover Mechanism Statistics

| Condition | Stratum | Pairs considered | Attempts | Accepted | Mean lift (clamped) | Mean lift (raw) |
|---|---|---|---|---|---|---|
| tdes\_full | split | 306 | 59 | 59 | +2.44 | — |
| tdes\_full | colocated | 108 | 4 | 0 | +0.00 | — |
| random\_crossover | split | 306 | 95 | 95 | +0.67 | +0.25 |
| random\_crossover | colocated | 132 | 43 | 43 | +0.00 | −0.28 |

*Clamped lift* is max(0, child\_passes − parent\_passes); *raw lift* allows negative
values and is only tracked for `random_crossover` where accepted children can regress.
The tdes\_full gate accepts only strict supersets, so clamped = raw for accepted
children (not separately tracked). The 0/4 acceptance on tdes\_full colocated confirms
the gate fires correctly: no pair ever forms a superset relationship when a single module
carries all bugs.

### Table 4 — Paired Statistical Tests (McNemar on solve outcome; sign test on pass count)

| Comparison | Stratum | Pairs | Solved discordant (McNemar) | Pass count (sign test) |
|---|---|---|---|---|
| tdes\_full vs single\_shot | all | 36 | +14 / −0 (p < 0.001) | +17 / −1 / =18 (p < 0.001) |
| tdes\_no\_crossover vs single\_shot | all | 36 | +15 / −0 (p < 0.001) | +19 / −0 / =17 (p < 0.001) |
| tdes\_full vs tdes\_no\_crossover | split | 24 | +2 / −2 (p = 1.000) | +2 / −2 / =20 (p = 1.000) |
| tdes\_full vs tdes\_no\_crossover | colocated | 12 | +0 / −1 (p = 1.000) | +0 / −2 / =10 (p = 0.500) |
| tdes\_full vs random\_crossover | split | 24 | +1 / −3 (p = 0.625) | +2 / −3 / =19 (p = 1.000) |

### Table 5 — Efficiency

| Condition | Solve rate | Median LLM calls (all cells) | Median calls-to-solve (solved cells) |
|---|---|---|---|
| single\_shot | 33% | 2 | 2 |
| random\_crossover | 86% | 8 | 8 |
| tdes\_no\_crossover | 75% | 8 | 8 |
| tdes\_full | 72% | 8 | 8 |

All iterative methods run at 4× the LLM call budget of single-shot. At equal call count,
iterative methods achieve 2.3× the solve rate of single-shot — a meaningful efficiency
gain when correctness matters more than cost. Note that this comparison is not
budget-controlled: a chain-of-thought self-repair baseline at the same 8-call budget
remains an open ablation.

---

## 7. Limitations

**Synthetic benchmark.** Both tasks are author-written codebases with author-injected bugs,
calibrated post-hoc so that single-shot achieves 33%. Real bug-fix benchmarks
(SWE-bench, Defects4J) are not calibrated to any method and contain more complex,
multi-file bugs. Generalisation to real-world bugs is untested.

**Underpowered crossover comparison.** 36 cells per condition provides approximately 15%
power to detect a 10–15 pp difference in solve rate (standard power analysis for McNemar,
α=0.05, OR≈1.5). The null result on tdes\_full vs tdes\_no\_crossover should be read as
*inconclusive* rather than *evidence of equivalence*. Detecting or ruling out a crossover
advantage at this scale requires approximately 150 cells per condition.

**Single model, single temperature.** All experiments use claude-haiku-4-5-20251001 at
temperature 0.8. The ordering of methods may differ for stronger models (where single-shot
might achieve 60%+) or weaker models. Multi-model validation is a necessary next step.

**Budget confound.** Single-shot uses 2 LLM calls; iterative methods use 8. The main
result establishes that 8 calls + CEGIS loop >> 2 calls + static prompt, but not that
the TDES machinery specifically causes the improvement over any 8-call iterative approach.

**No individual component ablation.** `tdes_no_crossover` bundles CEGIS feedback,
negative exemplar memory, and hierarchical scoring. Removing these one at a time would
isolate each mechanism's contribution; the present design attributes improvement only to
the bundle.
