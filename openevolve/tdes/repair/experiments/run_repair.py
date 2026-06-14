"""
Run TDES repair experiments across all four conditions and three benchmark tasks.

Usage:
    python -m openevolve.tdes.repair.experiments.run_repair \\
        --tasks pipeline api cicd \\
        --conditions tdes_full tdes_no_crossover unconstrained_evo single_shot \\
        --seeds 0 1 2 \\
        --config configs/claude_sonnet.yaml \\
        --out results/repair/

Each (condition, task, seed) triple writes one JSON file to --out.
Run with --dry-run to verify task/suite loading without making LLM calls.

Make-or-break check (run after all 36 runs):
    python -m openevolve.tdes.repair.experiments.run_repair --check --out results/repair/
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import time
from typing import List, Optional

from openevolve.tdes.config import TDESConfig
from openevolve.tdes.controller import load_seed_codebase
from openevolve.tdes.test_suite import TDESTestSuite
from openevolve.tdes.types import Candidate

from openevolve.tdes.repair.ablation import (
    CountingMutator,
    RepairNoCrossoverController,
    RepairRunMetrics,
    RepairTDESController,
    UnconstrainedCrossoverController,
)

logger = logging.getLogger(__name__)

_REPAIR_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SUITE_PATHS = {
    "pipeline":  os.path.join(_REPAIR_DIR, "tasks", "pipeline",    "suite.py"),
    "api":       os.path.join(_REPAIR_DIR, "tasks", "api",         "suite.py"),
    "cicd":      os.path.join(_REPAIR_DIR, "tasks", "cicd",        "suite.py"),
    "sympy_swe": os.path.join(_REPAIR_DIR, "tasks", "sympy_task1", "suite.py"),
}

BUGGY_DIRS = {
    "pipeline": os.path.join(_REPAIR_DIR, "tasks", "pipeline", "buggy"),
    "api":      os.path.join(_REPAIR_DIR, "tasks", "api",      "buggy"),
}

MODULE_NAMES = {
    "pipeline":  ["ingest", "transform", "aggregate"],
    "api":       ["auth", "router", "validator"],
    "cicd":      ["workflow"],
    "sympy_swe": ["point", "blockmatrix"],
}

CONDITIONS = ["tdes_full", "tdes_no_crossover", "unconstrained_evo", "single_shot"]


# ── Suite + seed loading ───────────────────────────────────────────────────────

def load_suite(task: str, cicd_sample: int = 0) -> TDESTestSuite:
    if task == "cicd":
        from openevolve.tdes.repair.tasks.cicd.suite import get_suite
        suite = get_suite(cicd_sample)
        # cicd suite is built in-process; sandboxed runs need source_path set.
        # We set it to the suite.py file so the subprocess runner can reload it.
        suite.source_path = SUITE_PATHS["cicd"]
        return suite
    if task == "sympy_swe":
        from openevolve.tdes.repair.tasks.sympy_task1.suite import get_suite as _get_sympy_suite
        suite = _get_sympy_suite()
        suite.source_path = SUITE_PATHS["sympy_swe"]
        return suite
    return TDESTestSuite.load_from_file(SUITE_PATHS[task])


def load_seed(task: str, cicd_sample: int = 0) -> Candidate:
    if task == "cicd":
        from openevolve.tdes.repair.tasks.cicd.suite import get_seed_source
        source = get_seed_source(cicd_sample)
        return Candidate(modules={"workflow": source}, generation=0, metadata={"origin": "seed"})
    if task == "sympy_swe":
        from openevolve.tdes.repair.tasks.sympy_task1.suite import get_seed as _get_sympy_seed
        return _get_sympy_seed()
    return load_seed_codebase(BUGGY_DIRS[task], MODULE_NAMES[task])


# ── Single-shot baseline (no evolutionary loop) ────────────────────────────────

async def run_single_shot(
    suite: TDESTestSuite,
    seed: Candidate,
    mutator,
    config: TDESConfig,
    condition: str,
    task: str,
    seed_idx: int,
    model: str,
) -> RepairRunMetrics:
    total = len(suite.tests)
    seed.vector = suite.run(seed, sandbox=config.sandbox, timeout=config.suite_timeout)
    initial_rate = round(seed.vector.total_passes / total, 4) if total else 0.0

    candidate = seed.clone(generation=1)
    candidate.vector = seed.vector
    counting = CountingMutator(mutator)

    start = time.perf_counter()
    for module in seed.vector.failing_modules():
        feedback = [
            r.feedback
            for r in seed.vector.results.values()
            if not r.passed and r.module == module and r.feedback is not None
        ]
        proposal = await counting.propose(
            candidate=candidate,
            module=module,
            feedback=feedback,
            memory_text="",
            generation=1,
        )
        if proposal is not None:
            candidate.modules[module] = proposal.new_source

    candidate.vector = suite.run(candidate, sandbox=config.sandbox, timeout=config.suite_timeout)
    elapsed = round(time.perf_counter() - start, 2)
    final_rate = round(candidate.vector.total_passes / total, 4) if total else 0.0
    solved = candidate.vector.total_passes == total

    return RepairRunMetrics(
        condition=condition,
        task=task,
        seed=seed_idx,
        test_pass_rate_per_generation=[initial_rate, final_rate],
        llm_calls_to_solution=counting.call_count,
        crossover_attempts=None,
        crossover_successes=None,
        regression_rate=None,
        stagnation_gen=None,
        wall_clock_seconds_per_gen=[elapsed],
        solved=solved,
        model=model,
    )


# ── Evolutionary conditions ───────────────────────────────────────────────────

CONTROLLER_MAP = {
    "tdes_full":         RepairTDESController,
    "tdes_no_crossover": RepairNoCrossoverController,
    "unconstrained_evo": UnconstrainedCrossoverController,
}


async def run_evolutionary(
    condition: str,
    suite: TDESTestSuite,
    seed: Candidate,
    mutator,
    config: TDESConfig,
    task: str,
    seed_idx: int,
    model: str,
) -> RepairRunMetrics:
    counting = CountingMutator(mutator)
    ctrl_cls = CONTROLLER_MAP[condition]
    ctrl = ctrl_cls(seed=seed, suite=suite, mutator=counting, config=config)
    await ctrl.run_async()
    metrics = ctrl.build_metrics(condition, task, seed_idx, model)
    metrics.llm_calls_to_solution = counting.call_count
    return metrics


# ── Top-level dispatch ─────────────────────────────────────────────────────────

async def run_one(
    condition: str,
    task: str,
    seed_idx: int,
    config: TDESConfig,
    model: str,
    out_dir: str,
    dry_run: bool = False,
    cicd_sample: int = 0,
) -> RepairRunMetrics:
    suite = load_suite(task, cicd_sample)
    seed = load_seed(task, cicd_sample)

    out_path = os.path.join(out_dir, f"{condition}_{task}_{seed_idx}.json")
    logger.info("Starting: condition=%s task=%s seed=%d -> %s", condition, task, seed_idx, out_path)

    if os.path.exists(out_path):
        logger.info("Skipping (already exists): %s", out_path)
        with open(out_path, encoding="utf-8") as f:
            return RepairRunMetrics(**json.load(f))

    if dry_run:
        seed.vector = suite.run(seed, sandbox=False, timeout=30)
        total = len(suite.tests)
        rate = round(seed.vector.total_passes / total, 4) if total else 0.0
        logger.info(
            "DRY RUN %s/%s: seed passes %d/%d (%.0f%%)",
            condition, task, seed.vector.total_passes, total, rate * 100,
        )
        return RepairRunMetrics(
            condition=condition, task=task, seed=seed_idx,
            test_pass_rate_per_generation=[rate],
            solved=seed.vector.total_passes == total, model=model,
        )

    from openevolve.tdes.repair.mutators.claude_mutator import ClaudeMutator
    mutator = ClaudeMutator(model=model)

    if condition == "single_shot":
        metrics = await run_single_shot(suite, seed, mutator, config, condition, task, seed_idx, model)
    else:
        metrics = await run_evolutionary(condition, suite, seed, mutator, config, task, seed_idx, model)

    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(metrics.as_dict(), f, indent=2)
    logger.info("Saved: %s (solved=%s)", out_path, metrics.solved)
    return metrics


# ── Make-or-break check ────────────────────────────────────────────────────────

def check_results(out_dir: str) -> None:
    """
    Evaluate whether the primary claim is supported by the results.

    tdes_full must beat tdes_no_crossover on >= 2/3 tasks on at least one metric.
    tdes_full must beat unconstrained_evo on >= 2/3 tasks on at least one metric.
    crossover_successes must be > 0 on all tdes_full runs.
    """
    results = {}
    for fname in os.listdir(out_dir):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(out_dir, fname), "r", encoding="utf-8") as f:
            data = json.load(f)
        key = (data["condition"], data["task"], data["seed"])
        results[key] = data

    tasks = sorted({k[1] for k in results}) or ["pipeline", "api", "cicd", "sympy_swe"]
    seeds = sorted({k[2] for k in results})

    print("\n=== MAKE-OR-BREAK CHECK ===\n")

    # 1. tdes_full vs tdes_no_crossover
    full_beats_ablation = 0
    for task in tasks:
        full_rates = [
            results.get(("tdes_full", task, s), {}).get("test_pass_rate_per_generation", [0])
            for s in seeds
        ]
        ablation_rates = [
            results.get(("tdes_no_crossover", task, s), {}).get("test_pass_rate_per_generation", [0])
            for s in seeds
        ]
        full_avg = sum(r[-1] if r else 0 for r in full_rates) / max(1, len(seeds))
        abl_avg = sum(r[-1] if r else 0 for r in ablation_rates) / max(1, len(seeds))
        beats = full_avg > abl_avg
        if beats:
            full_beats_ablation += 1
        print(f"  tdes_full vs tdes_no_crossover on {task}: {full_avg:.3f} vs {abl_avg:.3f} -> {'BEATS' if beats else 'loses'}")

    print(f"\n  tdes_full beats ablation on {full_beats_ablation}/3 tasks (need >= 2)")

    # 2. tdes_full vs unconstrained_evo
    full_beats_unconstrained = 0
    for task in tasks:
        full_rates = [
            results.get(("tdes_full", task, s), {}).get("test_pass_rate_per_generation", [0])
            for s in seeds
        ]
        unc_rates = [
            results.get(("unconstrained_evo", task, s), {}).get("test_pass_rate_per_generation", [0])
            for s in seeds
        ]
        full_avg = sum(r[-1] if r else 0 for r in full_rates) / max(1, len(seeds))
        unc_avg = sum(r[-1] if r else 0 for r in unc_rates) / max(1, len(seeds))
        beats = full_avg > unc_avg
        if beats:
            full_beats_unconstrained += 1
        print(f"  tdes_full vs unconstrained_evo on {task}: {full_avg:.3f} vs {unc_avg:.3f} -> {'BEATS' if beats else 'loses'}")

    print(f"\n  tdes_full beats unconstrained on {full_beats_unconstrained}/3 tasks (need >= 2)")

    # 3. crossover fires on all tdes_full runs
    all_fire = True
    for task in tasks:
        for s in seeds:
            data = results.get(("tdes_full", task, s), {})
            xo_succ = data.get("crossover_successes")
            if not xo_succ or xo_succ == 0:
                all_fire = False
                print(f"  WARNING: crossover_successes=0 on tdes_full/{task}/seed={s}")
    if all_fire:
        print("  crossover_successes > 0 on all tdes_full runs: YES")

    print()
    if full_beats_ablation >= 2 and full_beats_unconstrained >= 2 and all_fire:
        print("VERDICT: PRIMARY CLAIM SUPPORTED. Submit to AAAI 2027.")
    else:
        print("VERDICT: PRIMARY CLAIM NOT CLEARLY SUPPORTED. Investigate before submitting.")
    print()


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_config(args) -> TDESConfig:
    cfg = TDESConfig(
        pop_size=getattr(args, "pop_size", 5),
        max_generations=getattr(args, "max_gens", 5),
        window_size=3,
        sandbox=not getattr(args, "no_sandbox", False),
        suite_timeout=60,
        output_dir=os.path.join(args.out, "_tdes_output"),
    )
    if hasattr(args, "config") and args.config:
        try:
            cfg = TDESConfig.from_yaml(args.config)
            cfg.output_dir = os.path.join(args.out, "_tdes_output")
        except Exception as e:
            logger.warning("Could not load config %s (%s); using defaults.", args.config, e)
    return cfg


def main():
    parser = argparse.ArgumentParser(description="Run TDES repair experiments")
    parser.add_argument("--tasks",      nargs="+", default=["pipeline", "api"], choices=["pipeline", "api", "cicd", "sympy_swe"])
    parser.add_argument("--conditions", nargs="+", default=CONDITIONS, choices=CONDITIONS)
    parser.add_argument("--seeds",      nargs="+", type=int, default=[0, 1, 2])
    parser.add_argument("--model",      default="claude-sonnet-4-20250514")
    parser.add_argument("--config",     default=None, help="path to TDESConfig YAML")
    parser.add_argument("--out",        default="results/repair/")
    parser.add_argument("--no-sandbox", action="store_true")
    parser.add_argument("--pop-size",   type=int, default=5)
    parser.add_argument("--max-gens",   type=int, default=5)
    parser.add_argument("--dry-run",    action="store_true", help="load suites and score seeds only")
    parser.add_argument("--check",      action="store_true", help="run make-or-break check on saved results")
    parser.add_argument("--cicd-samples", nargs="+", type=int, default=[0, 1, 2])
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.check:
        check_results(args.out)
        return

    config = _build_config(args)
    os.makedirs(args.out, exist_ok=True)

    async def run_all():
        for condition in args.conditions:
            for task in args.tasks:
                for seed_idx in args.seeds:
                    cicd_sample = args.cicd_samples[seed_idx % len(args.cicd_samples)] if task == "cicd" else 0
                    await run_one(
                        condition=condition,
                        task=task,
                        seed_idx=seed_idx,
                        config=config,
                        model=args.model,
                        out_dir=args.out,
                        dry_run=args.dry_run,
                        cicd_sample=cicd_sample,
                    )

    asyncio.run(run_all())
    print(f"\nAll runs complete. Results in {args.out}")
    print(f"Run with --check to evaluate the make-or-break criterion.")


if __name__ == "__main__":
    main()
