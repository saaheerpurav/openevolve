"""
TDES-FPGA Level 3-4 Experiment Runner.

Runs the full condition matrix on fp_adder and fp_multiplier from ArchXBench,
plus budget-matched baselines (best_of_30, single_agent_30).

Conditions:
  - best_of_30:         30 independent zero-shot LLM samples, pick best
  - single_agent_30:    Single candidate, 30 rounds of iterative CEGIS repair
  - tdes_full:          Full TDES (crossover + memory, DiverseSchedule)
  - tdes_no_crossover:  Ablation: CEGIS + memory, no crossover
  - tdes_no_memory:     Ablation: CEGIS + crossover, no negative memory
  - tdes_scalar:        Ablation: scalar (total pass count) fitness instead of hierarchical

Budget target: pop=5, gens=6 → ~30 LLM calls per cell (same as baselines).

Usage:
    python -m openevolve.tdes.fpga.archxbench.run_l3_l4 \\
        --config openevolve/tdes/fpga/experiments/configs/anthropic_haiku.yaml \\
        --seeds 0 1 2 --out tdes_fpga_l3l4_results

    # Scripted offline validation:
    python -m openevolve.tdes.fpga.archxbench.run_l3_l4 --scripted --seeds 0
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import List, Optional

from openevolve.tdes import selection
from openevolve.tdes.fpga import ablation, baselines, metrics
from openevolve.tdes.fpga.archxbench import loader as archx_loader
from openevolve.tdes.fpga.config import FPGAConfig
from openevolve.tdes.fpga.mutation import VerilogLLMMutator
from openevolve.tdes.fpga.experiments._explib import IncrementalWriter, setup_logging

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

logger = logging.getLogger(__name__)

ALL_CONDITIONS = [
    "best_of_30",
    "single_agent_30",
    "tdes_full",
    "tdes_no_crossover",
    "tdes_no_memory",
    "tdes_scalar",
]

ALL_DESIGNS = list(archx_loader.DESIGNS)

_ABLATION_MAP = {
    "tdes_full":          dict(enable_crossover=True,  enable_memory=True),
    "tdes_no_crossover":  dict(enable_crossover=False, enable_memory=True),
    "tdes_no_memory":     dict(enable_crossover=True,  enable_memory=False),
}

_DEFAULT_OUT = "tdes_fpga_l3l4_results"


class _CountingEnsemble:
    _COUNTED = {"generate", "generate_with_context", "generate_multiple",
                "generate_all_with_context"}

    def __init__(self, inner):
        self._inner = inner
        self.calls = 0

    def __getattr__(self, name):
        attr = getattr(self._inner, name)
        if name in self._COUNTED and callable(attr):
            async def _wrapped(*args, **kwargs):
                self.calls += 1
                return await attr(*args, **kwargs)
            return _wrapped
        return attr


class _InstrumentedMixin:
    _counter = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls_trajectory = []
        self.module_first_solved = {}

    def _record_history(self, gen, population, *, stagnated=False, solved=False):
        super()._record_history(gen, population, stagnated=stagnated, solved=solved)
        calls = getattr(self._counter, "calls", 0)
        best = selection.best(population)
        bp = best.vector.total_passes if best and best.vector else 0
        self.calls_trajectory.append((gen, calls, bp))
        for cand in population:
            if cand.vector is None:
                continue
            for res in cand.vector.results.values():
                if res.passed:
                    self.module_first_solved.setdefault(res.module, gen)


class _InstrumentedDiverse(_InstrumentedMixin, ablation.DiverseScheduleController):
    pass


def build_ensemble(cfg: FPGAConfig):
    if cfg.llm is None or not cfg.llm.llm.models:
        raise ValueError("LLM config missing")
    from openevolve.llm.ensemble import LLMEnsemble
    return LLMEnsemble(cfg.llm.llm.models)


def run_cell(
    design: str,
    condition: str,
    cfg: FPGAConfig,
    *,
    seed_idx: int,
    ensemble=None,
    scripted: bool,
) -> Optional[metrics.RunMetrics]:
    import copy

    seed_cand, suite, ref_mutator = archx_loader.load(design, with_mutator=True)

    cell_cfg = copy.copy(cfg)
    cell_cfg.random_seed = (cfg.random_seed or 0) + seed_idx
    cell_cfg.output_dir = os.path.join(cfg.output_dir, design, condition, f"seed_{seed_idx}")

    counter = _CountingEnsemble(ensemble) if ensemble is not None else None

    if condition in _ABLATION_MAP:
        kwargs = _ABLATION_MAP[condition]
        suite_run = suite
        if condition == "tdes_scalar":
            from openevolve.tdes.fpga.ablation import flatten_levels
            suite_run = flatten_levels(suite)
        mutator = ref_mutator if scripted else VerilogLLMMutator(counter, diff_based=cell_cfg.diff_based)
        ctrl = _InstrumentedDiverse(seed_cand, suite_run, mutator, cell_cfg, **kwargs)
        ctrl._counter = counter
        result = ctrl.run()
        return metrics.from_result(
            design, condition, seed_idx, result,
            total_tests=len(suite_run.tests),
            crossover=ctrl.crossover_stats.as_dict(),
            llm_calls=getattr(counter, "calls", 0),
            calls_trajectory=ctrl.calls_trajectory,
            module_first_solved=ctrl.module_first_solved,
        )

    if condition == "tdes_scalar":
        from openevolve.tdes.fpga.ablation import flatten_levels
        suite_flat = flatten_levels(suite)
        mutator = ref_mutator if scripted else VerilogLLMMutator(counter, diff_based=cell_cfg.diff_based)
        ctrl = _InstrumentedDiverse(
            seed_cand, suite_flat, mutator, cell_cfg,
            enable_crossover=True, enable_memory=True,
        )
        ctrl._counter = counter
        result = ctrl.run()
        return metrics.from_result(
            design, condition, seed_idx, result,
            total_tests=len(suite_flat.tests),
            crossover=ctrl.crossover_stats.as_dict(),
            llm_calls=getattr(counter, "calls", 0),
            calls_trajectory=ctrl.calls_trajectory,
            module_first_solved=ctrl.module_first_solved,
        )

    if condition in ("best_of_30", "single_agent_30"):
        if scripted or ensemble is None:
            logger.info("skip baseline %s (needs LLM)", condition)
            return None
        if condition == "single_agent_30":
            br = baselines.single_agent_repair(
                seed_cand, suite, counter,
                rounds=cell_cfg.max_generations,
                timeout=cell_cfg.suite_timeout,
            )
        else:  # best_of_30
            module_name = list(seed_cand.modules)[0]
            spec = "; ".join(t.description for t in suite.tests[:2])
            br = baselines.pass_at_k(
                module_name, spec, suite, counter,
                k=30, timeout=cell_cfg.suite_timeout,
            )
        return metrics.RunMetrics(
            design=design, condition=condition, seed=seed_idx,
            solved=br.solved, total_passes=br.total_passes,
            total_tests=br.total_tests, generations_run=br.rounds_used,
            escalated=False, trajectory=br.trajectory,
            crossover=None, llm_calls=getattr(counter, "calls", 0),
            calls_to_solve=getattr(counter, "calls", 0) if br.solved else None,
        )

    raise ValueError(f"unknown condition: {condition}")


def run_matrix(
    designs: List[str],
    conditions: List[str],
    cfg: FPGAConfig,
    seeds: List[int],
    scripted: bool,
    writer: Optional[IncrementalWriter],
) -> List[metrics.RunMetrics]:
    ensemble = None if scripted else build_ensemble(cfg)
    results = []
    for design in designs:
        for cond in conditions:
            for s in seeds:
                key = f"{design}/{cond}/seed={s}"
                if writer and any(
                    m.design == design and m.condition == cond and m.seed == s
                    for m in writer.results
                ):
                    logger.info("skip completed: %s", key)
                    continue
                logger.info("running: %s", key)
                try:
                    rm = run_cell(design, cond, cfg, seed_idx=s,
                                  ensemble=ensemble, scripted=scripted)
                except Exception as e:
                    logger.warning("cell %s failed: %s", key, e)
                    rm = None
                if rm is not None:
                    results.append(rm)
                    if writer:
                        writer(rm)
                    logger.info(
                        "%s -> %d/%d %s (calls=%d)",
                        key, rm.total_passes, rm.total_tests,
                        "SOLVED" if rm.solved else "",
                        rm.llm_calls,
                    )
    return results


def _render_table(results: List[metrics.RunMetrics], designs: List[str]) -> str:
    lines = ["# TDES-FPGA Level 3-4 Results", "",
             "## Solve Rate by Condition", ""]
    header = "| Condition | " + " | ".join(designs) + " | Total |"
    sep    = "|---|" + "---|" * len(designs) + "---|"
    lines += [header, sep]
    for cond in ALL_CONDITIONS:
        cells = []
        total_s = total_n = 0
        for d in designs:
            rows = [m for m in results if m.design == d and m.condition == cond]
            s = sum(1 for m in rows if m.solved)
            n = len(rows)
            cells.append(f"{s}/{n}")
            total_s += s; total_n += n
        lines.append(f"| {cond} | " + " | ".join(cells) + f" | {total_s}/{total_n} |")
    lines += ["", "## Per-Cell Results", ""]
    lines += ["| Design | Condition | seed 0 | seed 1 | seed 2 | calls (med) |",
              "|---|---|---|---|---|---|"]
    for d in sorted(designs):
        for cond in ALL_CONDITIONS:
            row = []
            calls = []
            for s in [0, 1, 2]:
                m = next((x for x in results if x.design == d and x.condition == cond and x.seed == s), None)
                if m:
                    row.append("✓" if m.solved else f"{m.total_passes}/{m.total_tests}")
                    calls.append(m.llm_calls)
                else:
                    row.append("—")
            med = sorted(calls)[len(calls)//2] if calls else "—"
            if any(c != "—" for c in row):
                lines.append(f"| {d} | {cond} | {row[0]} | {row[1]} | {row[2]} | {med} |")
    return "\n".join(lines)


def main(argv=None):
    setup_logging()
    p = argparse.ArgumentParser(description="TDES-FPGA Level 3-4 experiments")
    p.add_argument("--config", help="YAML config (llm+tdes sections)")
    p.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    p.add_argument("--gens", type=int, default=6)
    p.add_argument("--pop",  type=int, default=5)
    p.add_argument("--out",  default=_DEFAULT_OUT)
    p.add_argument("--scripted", action="store_true")
    p.add_argument("--designs",    nargs="+", default=ALL_DESIGNS)
    p.add_argument("--conditions", nargs="+", default=ALL_CONDITIONS)
    p.add_argument("--skip-gates", action="store_true")
    args = p.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)
    metrics_path = os.path.join(args.out, "metrics_l3l4.json")
    results_path = os.path.join(args.out, "results.md")

    cfg = FPGAConfig.from_yaml(args.config) if args.config else FPGAConfig()
    cfg.max_generations = args.gens
    cfg.pop_size        = args.pop
    cfg.mutate_modules_per_candidate = 1
    cfg.output_dir = os.path.join(args.out, "runs")

    # Gate check: reference passes all, seed fails some
    if not args.skip_gates and not args.scripted:
        for design in args.designs:
            seed_cand, suite, _ = archx_loader.load(design, with_mutator=False)
            if not archx_loader.is_usable(seed_cand, suite):
                logger.warning("Gate FAILED for design '%s' — skip", design)
                args.designs = [d for d in args.designs if d != design]

    writer = IncrementalWriter(metrics_path)
    # Load existing results for resumability
    if os.path.exists(metrics_path):
        writer.results = metrics.load_metrics(metrics_path)

    results = run_matrix(
        args.designs, args.conditions, cfg, args.seeds,
        scripted=args.scripted, writer=writer,
    )

    # Merge new results with any pre-existing
    all_results = writer.results

    md = _render_table(all_results, args.designs)
    with open(results_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(md)
    logger.info("Results written to %s", results_path)


if __name__ == "__main__":
    main()
