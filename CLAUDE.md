# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

OpenEvolve is an open-source implementation of Google DeepMind's AlphaEvolve system - an evolutionary coding agent that uses LLMs to optimize code through iterative evolution. The framework can evolve code in multiple languages (Python, R, Rust, etc.) for tasks like scientific computing, optimization, and algorithm discovery.

## Essential Commands

### Development Setup
```bash
# Install in development mode with all dependencies
pip install -e ".[dev]"

# Or use Makefile
make install
```

### Running Tests
```bash
# Run all tests
python -m unittest discover tests

# Or use Makefile
make test
```

### Code Formatting
```bash
# Format with Black
python -m black openevolve examples tests scripts

# Or use Makefile
make lint
```

### Running OpenEvolve
```bash
# Basic evolution run
python openevolve-run.py path/to/initial_program.py path/to/evaluator.py --config path/to/config.yaml --iterations 1000

# Resume from checkpoint
python openevolve-run.py path/to/initial_program.py path/to/evaluator.py \
  --config path/to/config.yaml \
  --checkpoint path/to/checkpoint_directory \
  --iterations 50
```

### Visualization
```bash
# View evolution tree
python scripts/visualizer.py --path examples/function_minimization/openevolve_output/checkpoints/checkpoint_100/
```

## High-Level Architecture

### Core Components

1. **Controller (`openevolve/controller.py`)**: Main orchestrator that manages the evolution process using ProcessPoolExecutor for parallel iteration execution.

2. **Database (`openevolve/database.py`)**: Implements MAP-Elites algorithm with island-based evolution:
   - Programs mapped to multi-dimensional feature grid
   - Multiple isolated populations (islands) evolve independently
   - Periodic migration between islands prevents convergence
   - Tracks absolute best program separately

3. **Evaluator (`openevolve/evaluator.py`)**: Cascade evaluation pattern:
   - Stage 1: Quick validation
   - Stage 2: Basic performance testing  
   - Stage 3: Comprehensive evaluation
   - Programs must pass thresholds at each stage

4. **LLM Integration (`openevolve/llm/`)**: Ensemble approach with multiple models, configurable weights, and async generation with retry logic.

5. **Iteration (`openevolve/iteration.py`)**: Worker process that samples from islands, generates mutations via LLM, evaluates programs, and stores artifacts.

### Key Architectural Patterns

- **Island-Based Evolution**: Multiple populations evolve separately with periodic migration
- **MAP-Elites**: Maintains diversity by mapping programs to feature grid cells
- **Artifact System**: Side-channel for programs to return debugging data, stored as JSON or files
- **Process Worker Pattern**: Each iteration runs in fresh process with database snapshot
- **Double-Selection**: Programs for inspiration differ from those shown to LLM
- **Lazy Migration**: Islands migrate based on generation counts, not iterations

### Code Evolution Markers

Mark code sections to evolve using:
```python
# EVOLVE-BLOCK-START
# Code to evolve goes here
# EVOLVE-BLOCK-END
```

### Configuration

YAML-based configuration with hierarchical structure:
- LLM models and parameters
- Evolution strategies (diff-based vs full rewrites)
- Database and island settings
- Evaluation parameters

### Important Patterns

1. **Checkpoint/Resume**: Automatic saving of entire system state with seamless resume capability
2. **Parallel Evaluation**: Multiple programs evaluated concurrently via TaskPool
3. **Error Resilience**: Individual failures don't crash system - extensive retry logic and timeout protection
4. **Prompt Engineering**: Template-based system with context-aware building and evolution history

### TDES Mode (`openevolve/tdes/`)

An **additive** evolutionary mode that is independent of the MAP-Elites/island
controller above. TDES (Test-Driven Evolutionary Synthesis) replaces the scalar
fitness with a **hierarchical test-pass vector** and runs a *generational* loop
(see `tdes/controller.py`, mirroring the paper's Appendix A) rather than the
continuous async iteration loop. Key modules:

- `tdes/types.py` — `TestVector` (hierarchical `score_key`, superset checks),
  `Candidate` (a codebase as `{module: source}`).
- `tdes/test_suite.py` — `TDESTestSuite` + sandboxed subprocess runner that
  captures CEGIS feedback `(description, failing input, error)` without exposing
  test source.
- `tdes/crossover.py` — complementary-coverage crossover (the paper's primary
  contribution); `tdes/memory.py` — negative exemplar memory; `tdes/mutation.py`
  — `LLMMutator` (reuses `LLMEnsemble` + `code_utils`) and offline
  `ScriptedMutator`.

Entry point: `tdes-run.py`; example under `examples/tdes_example/`; tests in
`tests/test_tdes.py` (offline, no API key). TDES reuses `config.Config` for LLM
settings but adds `tdes/config.py::TDESConfig` for evolutionary parameters.

#### TDES-FPGA (`openevolve/tdes/fpga/`)

Additive Verilog-RTL layer that reuses the TDES controller/selection/crossover/
memory **unchanged** (they are duck-typed: the controller only needs
`suite.run()`, `suite.tests`, `suite.modules_for_tests()`). It swaps the test
runner for an EDA pipeline:

- `fpga/verilog_runner.py` — iverilog/vvp compile+simulate; interprets the
  `TDES_PASS/TDES_FAIL` protocol *and* native RTLLM/ArchXBench verdicts into
  CEGIS feedback. `fpga/synthesis.py` — Yosys LUT/FF extraction (`__synthesis__`
  sentinel tests). `fpga/verilog_suite.py::VerilogTestSuite` is the drop-in suite.
- `fpga/benchmark_loader.py` — RTLLM/ArchXBench/ResBench → `(seed, suite,
  reference-mutator)`; `fpga/testbench_decomposer.py` builds hierarchical suites
  (reference-gated: only used if the known-good reference passes them).
- `fpga/ablation.py::AblationController` (subclass) toggles crossover/memory and
  instruments crossover; `fpga/experiments/` runs the matrix + Table 1/2.

*Paper experiments* (`fpga/experiments/`) — the 5-experiment campaign
(`run_exp1_baseline.py` RTLLM baseline / `run_exp2_crossover.py` crossover
showcase / `run_exp3_scaling.py` ArchXBench L2–3 / `run_exp4_ablation.py`
mechanism ablation / `convergence.py` efficiency analysis; `run_all.py`
orchestrates). The headline **Exp 2** turns *published* hierarchical ArchXBench
designs into genuine multi-module `{TOP, SUB}` problems via
`hierarchical_archx.py` — a 3-tier suite (SUB unit, TOP wiring vs an inline golden
SUB, native testbench as SYSTEM) over `VerilogTestSuite(isolate_modules=True)`, so
complementary-coverage crossover fires on real benchmarks (the authored
sub/top-wiring tiers are reference-gated). `runner.py` adds a counting ensemble
(LLM-call metrics), instrumented controllers (per-module solve timeline +
calls-to-solve), a `"diverse"` controller choice, and the `tdes_no_cegis` ablation.
`metrics_exp*.json` are written incrementally (resumable sweeps).

Toolchain: set `OSS_CAD_SUITE_ROOT` (auto-activates bin+lib on import). EDA-gated
tests live in `fpga/tests/` (skipped when tools absent). Entry point
`tdes-fpga-run.py`. **Do not modify base `tdes/*` files** — extend via subclass/
composition as this layer does.

*Efficiency demo* (`fpga/efficiency_demo/`) — the AlphaEvolve-TPU analog: evolve
an *already-correct* arithmetic circuit into a **provably-equivalent, smaller**
one (complex multiplier, 4→3 multipliers / Gauss-Karatsuba). Unlike the rest of
the layer it verifies by **formal equivalence** (`fpga/equivalence.py`, Yosys
miter+SAT) not simulation, and optimizes **area** (`synthesis.py::rtl_cell_counts`
→ `$mul` count). `efficiency_demo/efficiency_suite.py::EfficiencySuite` is a
drop-in suite whose hierarchy makes equivalence the UNIT invariant and
area-under-budget the SYSTEM goal, with **area gated on equivalence** (a
smaller-but-wrong design must never outrank a correct one). `_validate.py` proves
the mechanism offline; `run_demo.py` is the LLM run (Sonnet found the Gauss
algorithm in 2 gens, SAT-verified — see `efficiency_demo/RESULTS.md`).

#### TDES-CombOpt (`openevolve/tdes/combopt/`)

Additive layer that evolves *heuristics* for NP-hard problems (Maximum
Independent Set, Max-Cut) and composes them with a downstream **exact solver**
(OR-Tools CP-SAT) — the FunSearch/AlphaEvolve pattern (evolve the priority
function, never the solution; a deterministic harness owns correctness). Reuses
the base controller/selection/crossover/memory unchanged (duck-typed suite) and
the FPGA layer's suite-agnostic `AblationController` family.

- A candidate is a **portfolio** `{instance_class: priority_source}` (classes:
  sparse/dense/clustered). `combopt/problems.py` holds the fixed greedy/local-
  search harnesses (feasibility guaranteed, objective recomputed exactly);
  `combopt/exact.py` is the CP-SAT warm-start solver (deterministic budget for
  reproducible warm-vs-cold). `combopt/heuristic_runner.py` sandboxes candidate
  code in a subprocess; `combopt/combopt_suite.py` is the drop-in suite.
- Hierarchy: UNIT (per class-instance vs classical baseline) → INTEGRATION (per-
  class held-out batch) → SYSTEM (the headline: the portfolio warm-starts CP-SAT
  and the hybrid beats the **cold** solver under the same budget).
- `combopt/benchmark_loader.py::load_problem` builds `(seed, suite, reference-
  mutator)`; `combopt/experiments/` has the method comparison, crossover ablation,
  configs, and `RESULTS.md`. Needs `pip install ortools`. Entry point
  `tdes-combopt-run.py`; tests in `combopt/tests/` (gated on ortools, no API key).
  **Do not modify base `tdes/*` files.**

#### TDES-MAE (`openevolve/tdes/mae/`)

Additive layer that evolves an *ML training component*: the patch-masking
strategy (`masking.py::generate_mask()`) of a tiny Masked Autoencoder
(`model.py`, ~160K params) pretrained on a cached CIFAR-10 subset
(`data.py`, gitignored under `mae/data/`). A validation experiment for
applying TDES beyond code synthesis (pilot for EEG-LeJEPA); single-module
candidate, so **crossover is disabled** — this layer exercises hierarchical
selection, CEGIS feedback, and negative memory.

- `evaluator.py::MAESuite` — duck-typed 3-tier suite: 8 UNIT checks on the
  mask itself (no training compute until all pass) → INTEGRATION
  (10-epoch reconstruction-loss gate) → SYSTEM (30-epoch pretrain + frozen
  linear probe, with the scalar probe accuracy expressed as a **ladder of
  SYSTEM tests** so selection sees an accuracy gradient). Candidate code runs
  in a persistent worker subprocess (timeout → kill+respawn); evals are
  memoized by source hash. CEGIS feedback carries the measured scalars.
- `controller.py::MAEEvolutionController` — base loop plus *stagnation
  patience* (a flat generation is routine with a noisy ML objective) and a
  no-op crossover phase. `trainer.py` seeds everything so a (source, seed)
  pair is reproducible. Tier thresholds in `config.py` are calibrated against
  the measured random-mask baseline (30-epoch probe 0.360±0.007 on CPU).

Entry point: `python -m openevolve.tdes.mae.run` (CPU default, `--scripted`
for offline smoke, `--compare-only` for head-to-head). Offline tests in
`mae/tests/`. Results land in `tdes_mae_results/` (gitignored). **Do not
modify base `tdes/*` files.**

### Development Notes

- Python >=3.10 required
- Uses OpenAI-compatible APIs for LLM integration
- Tests use unittest framework
- Black for code formatting
- Artifacts threshold: Small (<10KB) stored in DB, large saved to disk
- Process workers load database snapshots for true parallelism