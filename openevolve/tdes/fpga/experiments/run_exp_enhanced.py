"""
Experiment: Enhanced TDES-FPGA — four mechanisms vs ablations on hier designs.

Runs the headline comparison table from the ICML workshop paper:

    Conditions (8):
      best_of_30              — Best-of-30 independent LLM samples (budget-matched baseline)
      single_agent            — Single-agent iterative repair, 30 LLM rounds (budget-matched)
      tdes_full               — Existing TDES (DiverseScheduleController, existing ablation.py)
      tdes_enhanced           — All four enhancements: diverse seed + semantic XO + priority mut + pos mem
      tdes_no_diverse_seed    — Enhanced minus diverse seeding
      tdes_no_semantic_xo     — Enhanced minus semantic crossover fallback
      tdes_no_priority_mut    — Enhanced minus priority-ordered mutation
      tdes_no_positive_mem    — Enhanced minus positive memory

    Benchmarks: hier (5 ArchXBench hierarchical designs via hierarchical_archx.py)

    Seeds: 0, 1, 2  (each run uses a different random seed for population shuffling)

    Budget target: ~30 LLM calls per cell (pop=5, gens=5, 1 module/candidate/gen
    + occasional crossover calls). best_of_30 and single_agent also use 30 calls.

Output:
    tdes_fpga_enhanced_results/metrics_exp_enhanced.json  (incremental, resumable)
    tdes_fpga_enhanced_results/results.md                 (summary tables)

Usage:
    # Scripted smoke test (no API key, no EDA tools needed):
    python -m openevolve.tdes.fpga.experiments.run_exp_enhanced --scripted

    # Full LLM run (requires ANTHROPIC_API_KEY + OSS CAD Suite):
    python -m openevolve.tdes.fpga.experiments.run_exp_enhanced \\
        --config path/to/anthropic_sonnet.yaml \\
        --seeds 0 1 2

    # Resume a partial run:
    python -m openevolve.tdes.fpga.experiments.run_exp_enhanced \\
        --config path/to/anthropic_sonnet.yaml \\
        --resume tdes_fpga_enhanced_results/metrics_exp_enhanced.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import List, Optional

from openevolve.tdes.fpga import metrics
from openevolve.tdes.fpga.config import FPGAConfig
from openevolve.tdes.fpga.experiments import hierarchical_archx, runner, _explib
from openevolve.tdes.fpga.enhanced import ENHANCED_CONDITIONS

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

logger = logging.getLogger(__name__)

# All conditions for the enhanced experiment
ALL_CONDITIONS = [
    "best_of_30",
    "single_agent",
    "tdes_full",
] + list(ENHANCED_CONDITIONS.keys())

_DEFAULT_OUT = "tdes_fpga_enhanced_results"


class _ResumableWriter:
    """Skip already-completed (design, condition, seed) cells on resume."""

    def __init__(self, out_path: str):
        self.out_path = out_path
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        self.results: List[metrics.RunMetrics] = (
            metrics.load_metrics(out_path) if os.path.exists(out_path) else []
        )
        already = {(m.design, m.condition, m.seed) for m in self.results}
        if already:
            logger.info("Resume: skipping %d completed cells", len(already))

    def done(self, design: str, condition: str, seed: int) -> bool:
        return any(
            m.design == design and m.condition == condition and m.seed == seed
            for m in self.results
        )

    def __call__(self, rm: metrics.RunMetrics) -> None:
        self.results.append(rm)
        metrics.save_metrics(self.results, self.out_path)


def _load_config(path: Optional[str], *, gens: int, pop: int) -> FPGAConfig:
    cfg = FPGAConfig.from_yaml(path) if path else FPGAConfig()
    cfg.max_generations = gens
    cfg.pop_size = pop
    cfg.mutate_modules_per_candidate = 1
    return cfg


def _render_results(results: List[metrics.RunMetrics], designs: List[str]) -> str:
    lines = [
        "# Enhanced TDES-FPGA Experiment Results",
        "",
        "## Solve Rate by Condition",
        "",
    ]
    # Compute solve rates
    lines.append("| Condition | solve rate | median LLM calls | semantic_xo accepted |")
    lines.append("|---|---|---|---|")
    for cond in ALL_CONDITIONS:
        rows = [m for m in results if m.condition == cond]
        if not rows:
            continue
        sr = sum(1 for m in rows if m.solved) / len(rows)
        calls = [m.llm_calls for m in rows]
        med_calls = sorted(calls)[len(calls) // 2] if calls else 0
        sem_accepted = sum(
            (m.crossover or {}).get("semantic_accepted", 0) for m in rows
        )
        lines.append(f"| {cond} | {sr:.0%} ({sum(1 for m in rows if m.solved)}/{len(rows)}) "
                     f"| {med_calls} | {sem_accepted} |")

    lines.extend([
        "",
        "## Per-Design Breakdown",
        "",
        "| Design | Condition | seed 0 | seed 1 | seed 2 | passes (best) |",
        "|---|---|---|---|---|---|",
    ])
    for d in sorted(designs):
        for cond in ALL_CONDITIONS:
            row_cells = []
            best_passes = 0
            total_tests = 0
            for s in [0, 1, 2]:
                match = next(
                    (m for m in results if m.design == d and m.condition == cond and m.seed == s),
                    None
                )
                if match:
                    row_cells.append("✓" if match.solved else f"{match.total_passes}/{match.total_tests}")
                    best_passes = max(best_passes, match.total_passes)
                    total_tests = match.total_tests
                else:
                    row_cells.append("—")
            if any(c != "—" for c in row_cells):
                lines.append(
                    f"| {d} | {cond} | {row_cells[0]} | {row_cells[1]} | {row_cells[2]} "
                    f"| {best_passes}/{total_tests} |"
                )

    lines.extend([
        "",
        "## Crossover Statistics (enhanced conditions only)",
        "",
        "| Condition | xo_attempts | xo_accepted | semantic_attempts | semantic_accepted |",
        "|---|---|---|---|---|",
    ])
    for cond in list(ENHANCED_CONDITIONS.keys()) + ["tdes_full"]:
        rows = [m for m in results if m.condition == cond and m.crossover]
        if not rows:
            continue
        attempts = sum((m.crossover or {}).get("attempts", 0) for m in rows)
        accepted = sum((m.crossover or {}).get("accepted", 0) for m in rows)
        sem_att = sum((m.crossover or {}).get("semantic_attempts", 0) for m in rows)
        sem_acc = sum((m.crossover or {}).get("semantic_accepted", 0) for m in rows)
        lines.append(f"| {cond} | {attempts} | {accepted} | {sem_att} | {sem_acc} |")

    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> None:
    _explib.setup_logging()
    p = argparse.ArgumentParser(description="Enhanced TDES-FPGA experiment")
    p.add_argument("--config", help="Path to YAML config (llm + tdes sections)")
    p.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    p.add_argument("--gens", type=int, default=5, help="Max generations per cell")
    p.add_argument("--pop", type=int, default=5, help="Population size")
    p.add_argument("--out", default=_DEFAULT_OUT, help="Output directory")
    p.add_argument("--scripted", action="store_true", help="Use reference mutator (no API key)")
    p.add_argument("--resume", help="Path to existing metrics JSON to resume from")
    p.add_argument(
        "--conditions", nargs="+", default=ALL_CONDITIONS,
        help="Subset of conditions to run"
    )
    p.add_argument(
        "--designs", nargs="+", default=hierarchical_archx.DESIGNS,
        help="Subset of hier designs to run"
    )
    args = p.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)
    metrics_path = args.resume or os.path.join(args.out, "metrics_exp_enhanced.json")
    results_path = os.path.join(args.out, "results.md")

    cfg = _load_config(args.config, gens=args.gens, pop=args.pop)

    writer = _ResumableWriter(metrics_path)
    ensemble = None if args.scripted else runner.build_ensemble(cfg)

    designs = args.designs
    conditions = args.conditions
    seeds = args.seeds

    total = len(designs) * len(conditions) * len(seeds)
    done = 0

    for design in designs:
        for condition in conditions:
            for seed in seeds:
                if writer.done(design, condition, seed):
                    done += 1
                    logger.info("skip completed: %s/%s seed=%d", design, condition, seed)
                    continue
                logger.info(
                    "Running [%d/%d]: %s / %s / seed=%d",
                    done + 1, total, design, condition, seed
                )
                try:
                    rm = runner.run_cell(
                        "hier",
                        design,
                        condition,
                        cfg,
                        seed=seed,
                        ensemble=ensemble,
                        scripted=args.scripted,
                        controller="diverse",
                    )
                except Exception as e:
                    logger.warning("cell failed: %s/%s seed=%d: %s", design, condition, seed, e)
                    rm = None
                if rm is not None:
                    writer(rm)
                    logger.info(
                        "  %s [%s] seed=%d -> %d/%d %s (calls=%d)",
                        design, condition, seed,
                        rm.total_passes, rm.total_tests,
                        "SOLVED" if rm.solved else "",
                        rm.llm_calls,
                    )
                done += 1

    # Render final tables
    md = _render_results(writer.results, designs)
    with open(results_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(md)
    logger.info("Results written to %s", results_path)


if __name__ == "__main__":
    main()
