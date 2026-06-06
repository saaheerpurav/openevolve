# TDES example: orders pipeline

A self-contained demonstration of **Test-Driven Evolutionary Synthesis (TDES)**
on a small modular codebase. It runs **fully offline** (no API key) via a
deterministic scripted mutator, and the same suite can drive a real LLM.

## The problem

A three-module codebase under `seed/`:

| module        | role                                   | seed status                          |
|---------------|----------------------------------------|--------------------------------------|
| `stats.py`    | `mean`, `median`                       | `median` doesn't sort its input (bug)|
| `pricing.py`  | `apply_discount`, `line_total`         | `apply_discount` subtracts `pct` instead of scaling (bug) |
| `pipeline.py` | `summarize` (end-to-end order summary) | correct, but depends on the two above |

`suite.py` defines a **hierarchical** test suite:

- **unit** tests for `stats` and `pricing`,
- an **integration** test for `pipeline` total (depends on `pricing`),
- a **system** test for the full summary (depends on `pricing` *and* `stats`).

Fixing the unit-level bugs cascades up to make the integration and system tests
pass — which is exactly the hierarchy TDES exploits.

## Run it (offline)

```bash
python tdes-run.py examples/tdes_example/seed examples/tdes_example/suite.py \
    --scripted --no-sandbox --gens 5
```

You'll see the population's hierarchical test-pass vector improve generation by
generation until all tests pass. The final best codebase and a `result.json`
are written under `examples/tdes_example/tdes_output/best/`.

## What this example exercises

- **Hierarchical test-pass vector + selection** (§3.1) — candidates are ranked
  system > integration > unit.
- **CEGIS-style feedback** (§3.2) — the mutator receives each failing test's
  description, concrete failing input, and error (never the test source).
- **Modular scope isolation** (§3.5) — one module is evolved at a time and
  reintegrated, accepted only if no test regresses.
- **Negative exemplar memory** (§3.4) — the scripted `stats` fix first proposes
  a change that regresses `mean`; that failure is recorded, and the corrected
  fix is proposed once the failure is in memory.

**Complementary-coverage crossover** (§3.3) and **stagnation → escalation**
(§3.6) require population diversity / unsolvable bugs and are demonstrated
deterministically in `tests/test_tdes.py`.

## Run it with a real LLM

Set `OPENAI_API_KEY` and drop `--scripted`:

```bash
python tdes-run.py examples/tdes_example/seed examples/tdes_example/suite.py \
    --config examples/tdes_example/config.yaml --gens 5
```

The LLM mutator (`openevolve/tdes/mutation.py::LLMMutator`) receives the same
CEGIS feedback and negative memory and proposes diffs to the failing module.
