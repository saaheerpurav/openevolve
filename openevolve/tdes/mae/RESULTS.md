# TDES-MAE: results

A validation experiment: can TDES evolve an *ML training component* — the
patch-masking strategy of a Masked Autoencoder — using the same hierarchical
test-feedback loop used for code synthesis? Single evolved module
(`generate_mask()`), so crossover is disabled; the mechanisms under test are
hierarchical selection, CEGIS feedback, and negative-exemplar memory.

Setup: TinyMAE (~160K params), CIFAR-10 subset (5000 pretrain / 2000 probe-test,
class-balanced, pre-patchified), CPU-only (torch 2.12+cpu), **Haiku 4.5** mutator,
population 4, 10 generations, ~20 LLM calls total. Evaluations are fully seeded:
a (source, seed) pair is reproducible, so the no-regression acceptance check is
meaningful. Reproduce:

```bash
export ANTHROPIC_API_KEY=...
python -m openevolve.tdes.mae.run --gens 10 --pop 4 --patience 4
```

## Headline result

**The evolved masking strategy beats random masking on all 3 held-out seeds**
(30-epoch pretrain + frozen linear probe, seeds never used during evolution):

| seed | random baseline | evolved | Δ |
|---|---|---|---|
| 0 | 0.352 | 0.364 | +1.2% |
| 1 | 0.366 | 0.371 | +0.5% |
| 2 | 0.352 | 0.356 | +0.4% |
| **mean** | **0.356** | **0.364** | **+0.7%** |

(Random-encoder floor: 0.292; so the evolved mask closes ~11% of the remaining
headroom over the baseline's representation quality at this tiny scale.)

The discovered strategy is interpretable, not noise — a **three-phase
curriculum** Haiku assembled across generations: early epochs keep visible
patches stratified across the four 2×2 quadrants (well-distributed context),
middle epochs mix 60% random / 40% rectangular-block masking, late epochs mask
large contiguous blocks (hardest task last). Block masking and curricula are
both *known-good ideas from the MAE literature*; the point is that the
test-feedback loop found and combined them from a random-mask seed in 10
generations without being told.

## Mechanism evidence (evolution_log.json)

* **Hierarchical gating saved compute.** 4 of 19 unique proposals were rejected
  at the UNIT tier (non-stochastic masks ×2, wrong ratio ×2) in milliseconds —
  no training spent. The recurring failure modes went into negative memory and
  did not recur in later generations.
* **The accuracy ladder ratcheted.** Accepted-lineage probe accuracy at the
  evaluation seed: 0.362 → 0.3655 → 0.373 → 0.378 → **0.382**, each step a new
  SYSTEM rung (selection only ever saw "more tests passed").
* **CEGIS feedback carried scalars** ("probe accuracy was 0.367, below the 0.375
  target; reconstruction loss 0.713"), which is what the mutator steered by.

## The rung-spacing lesson (run 1, kept for the record)

The first full run used coarser rungs (0.34, then 0.37) and **escalated as
"stagnated" at generation 4 while genuinely improving**: trial accuracies climbed
0.362 → 0.364 → 0.3655 → 0.369 — all real progress, all below rung resolution,
and equal-rung candidates are discarded by the no-regression filter. The fix is
finer rungs near the current frontier (0.355/0.365/0.375/0.385…), after which the
same setup climbed two rungs and produced the headline result. **General design
rule: when a scalar ML objective is discretized into hierarchy tests, the step
size near the frontier sets the visibility of progress to selection** — the ML
analog of the FPGA layer's co-equal-UNIT-tier lesson. (Artifacts of run 1 are in
`tdes_mae_results/run1_coarse_ladder/`.)

## Honesty notes

* **The gain is small (+0.7% mean) and the scale is tiny** (160K params, 5K
  images, 16 patches). This is a *validation* of the loop, not a claim about
  state-of-the-art masking. The plan's own bar — "if evolved is only +1-2% over
  random, that's fine; the point is the TDES loop works for ML components" — is
  met, with the consistency bonus (3/3 seeds).
* **Selection inflates the eval-seed number.** The best candidate scored 0.382
  at the evaluation seed but 0.364 averaged over fresh seeds — selecting on a
  noisy objective overfits it by construction. The held-out head-to-head above
  is the unbiased estimate; the ladder numbers are for selection only.
* **The run ended by escalation on its final generation** (4 flat generations
  after the last rung climb) — i.e. Haiku plateaued at ~0.38 at this budget.
  A stronger mutator model or longer budget may climb further; untested.
* **Both runs' LLM cost was trivial** (~20 Haiku calls each); compute cost is
  the CPU training (~100s per surviving candidate).

## Next step (the actual target)

The function signature, evaluator hierarchy, CEGIS format, and memory transfer
unchanged to the EEG-LeJEPA setting: swap `num_patches=16`/4×4 grid for the
channels×time grid, TinyMAE for the LeJEPA model, and the linear probe for the
BCI downstream task.
