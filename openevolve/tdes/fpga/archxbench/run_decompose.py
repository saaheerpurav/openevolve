"""
Decompose-then-Evolve experiment: does decomposing a Level-4 pipelined FP
multiplier into 5 independently-evolvable sub-modules unlock TDES crossover?

The thesis (Wolf et al. 2024): monolithic generation has exponential complexity
in the number of sub-components.  Decomposition reduces it to linear.  TDES
crossover further reduces it by combining partial solutions from different
candidates — but only fires when candidates have *complementary module-level
coverage* (Goldilocks finding).  Five sub-modules create exactly the right
granularity: P(all 5 correct in one shot) is low, but P(each solved by at
least one candidate in the population) is high → crossover combines them.

Design: fp_mult_pipeline — Level-4 pipelined FP multiplier decomposed into:
  fpm_unpack, fpm_multiply, fpm_normalize, fpm_round_pack, fpm_special

Conditions:
  single_agent_30     — iterative CEGIS baseline (no population)
  tdes_full           — TDES with crossover + memory
  tdes_no_crossover   — TDES without crossover (ablation)

Baselines (from previous experiments on monolithic fp_multiplier):
  Haiku monolithic TDES: 0/3 coarse, 2/3 fine (crossover never fired)
  Sonnet monolithic:     3/3 single-agent, 0-2/3 TDES (crossover never fired)

Usage:
    python -m openevolve.tdes.fpga.archxbench.run_decompose \\
        --config openevolve/tdes/fpga/experiments/configs/anthropic_haiku.yaml \\
        --seeds 0 1 2 --out tdes_fpga_decompose_results

    # Offline validation (scripted mutations):
    python -m openevolve.tdes.fpga.archxbench.run_decompose --scripted --seeds 0
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
from openevolve.tdes.fpga.archxbench.loader import _FPM_PIPE_MODULES
from openevolve.tdes.fpga.config import FPGAConfig
from openevolve.tdes.fpga.mutation import VerilogLLMMutator
from openevolve.tdes.fpga.experiments._explib import IncrementalWriter, setup_logging

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

logger = logging.getLogger(__name__)

ALL_CONDITIONS = ["single_agent_30", "tdes_full", "tdes_no_crossover"]
ALL_DESIGNS = ["fp_mult_pipeline"]

_ABLATION_MAP = {
    "tdes_full": dict(enable_crossover=True, enable_memory=True),
    "tdes_no_crossover": dict(enable_crossover=False, enable_memory=True),
}

_DEFAULT_OUT = "tdes_fpga_decompose_results"


class _CountingEnsemble:
    _COUNTED = {
        "generate",
        "generate_with_context",
        "generate_multiple",
        "generate_all_with_context",
    }

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
        mutator = (
            ref_mutator if scripted else VerilogLLMMutator(counter, diff_based=cell_cfg.diff_based)
        )
        ctrl = _InstrumentedDiverse(seed_cand, suite, mutator, cell_cfg, **kwargs)
        ctrl._counter = counter
        result = ctrl.run()
        return metrics.from_result(
            design,
            condition,
            seed_idx,
            result,
            total_tests=len(suite.tests),
            crossover=ctrl.crossover_stats.as_dict(),
            llm_calls=getattr(counter, "calls", 0),
            calls_trajectory=ctrl.calls_trajectory,
            module_first_solved=ctrl.module_first_solved,
        )

    if condition == "single_agent_30":
        if scripted or ensemble is None:
            logger.info("skip baseline %s (needs LLM)", condition)
            return None
        br = baselines.single_agent_repair(
            seed_cand,
            suite,
            counter,
            rounds=cell_cfg.max_generations,
            timeout=cell_cfg.suite_timeout,
        )
        return metrics.RunMetrics(
            design=design,
            condition=condition,
            seed=seed_idx,
            solved=br.solved,
            total_passes=br.total_passes,
            total_tests=br.total_tests,
            generations_run=br.rounds_used,
            escalated=False,
            trajectory=br.trajectory,
            crossover=None,
            llm_calls=getattr(counter, "calls", 0),
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
                    rm = run_cell(
                        design, cond, cfg, seed_idx=s, ensemble=ensemble, scripted=scripted
                    )
                except Exception as e:
                    logger.warning("cell %s failed: %s", key, e)
                    rm = None
                if rm is not None:
                    results.append(rm)
                    if writer:
                        writer(rm)
                    xo = rm.crossover or {}
                    logger.info(
                        "%s -> %d/%d %s (calls=%d, xo_attempts=%s, xo_accepted=%s)",
                        key,
                        rm.total_passes,
                        rm.total_tests,
                        "SOLVED" if rm.solved else "",
                        rm.llm_calls,
                        xo.get("attempts", "—"),
                        xo.get("accepted", "—"),
                    )
    return results


def _render_table(results: List[metrics.RunMetrics], designs: List[str]) -> str:
    lines = [
        "# TDES-FPGA Decompose-Then-Evolve Experiment",
        "",
        "**Thesis**: decomposing a Level-4 pipelined FP multiplier into 5",
        "independently-evolvable sub-modules enables TDES crossover.",
        "",
        "## Solve Rate",
        "",
    ]
    header = "| Condition | " + " | ".join(designs) + " | Total |"
    sep = "|---|" + "---|" * len(designs) + "---|"
    lines += [header, sep]
    for cond in ALL_CONDITIONS:
        cells = []
        total_s = total_n = 0
        for d in designs:
            rows = [m for m in results if m.design == d and m.condition == cond]
            s = sum(1 for m in rows if m.solved)
            n = len(rows)
            cells.append(f"{s}/{n}")
            total_s += s
            total_n += n
        lines.append(f"| {cond} | " + " | ".join(cells) + f" | {total_s}/{total_n} |")

    lines += ["", "## Crossover Activity (tdes_full only)", ""]
    lines += ["| Design | seed | attempts | accepted | total_passes |", "|---|---|---|---|---|"]
    for d in designs:
        rows = [m for m in results if m.design == d and m.condition == "tdes_full"]
        for m in sorted(rows, key=lambda x: x.seed):
            xo = m.crossover or {}
            lines.append(
                f"| {d} | {m.seed} | {xo.get('attempts','—')} | "
                f"{xo.get('accepted','—')} | {m.total_passes}/{m.total_tests} |"
            )

    lines += ["", "## Module First-Solved Generation", ""]
    lines += [
        "| Design | Condition | seed | " + " | ".join(_FPM_PIPE_MODULES) + " |",
        "|---|---|---|" + "---|" * len(_FPM_PIPE_MODULES),
    ]
    for d in designs:
        for cond in [c for c in ALL_CONDITIONS if c != "single_agent_30"]:
            for m in sorted(
                [x for x in results if x.design == d and x.condition == cond],
                key=lambda x: x.seed,
            ):
                mfs = getattr(m, "extra", {}).get("module_first_solved", {})
                if not mfs and hasattr(m, "module_first_solved"):
                    mfs = m.module_first_solved
                cells = [str(mfs.get(mod, "—")) for mod in _FPM_PIPE_MODULES]
                lines.append(f"| {d} | {cond} | {m.seed} | " + " | ".join(cells) + " |")

    lines += ["", "## Per-Cell Detail", ""]
    seeds_present = sorted(set(m.seed for m in results))
    seed_headers = " | ".join(f"seed {s}" for s in seeds_present)
    lines += [
        f"| Design | Condition | {seed_headers} | calls (med) |",
        "|---|---|" + "---|" * len(seeds_present) + "---|",
    ]
    for d in sorted(designs):
        for cond in ALL_CONDITIONS:
            row = []
            calls = []
            for s in seeds_present:
                m = next(
                    (x for x in results if x.design == d and x.condition == cond and x.seed == s),
                    None,
                )
                if m:
                    row.append("SOLVED" if m.solved else f"{m.total_passes}/{m.total_tests}")
                    calls.append(m.llm_calls)
                else:
                    row.append("—")
            med = sorted(calls)[len(calls) // 2] if calls else "—"
            if any(c != "—" for c in row):
                lines.append(f"| {d} | {cond} | " + " | ".join(row) + f" | {med} |")

    return "\n".join(lines)


def main(argv=None):
    setup_logging()
    p = argparse.ArgumentParser(description="TDES decompose-then-evolve experiment")
    p.add_argument("--config", help="YAML config (llm+tdes sections)")
    p.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    p.add_argument("--gens", type=int, default=8)
    p.add_argument("--pop", type=int, default=5)
    p.add_argument("--out", default=_DEFAULT_OUT)
    p.add_argument("--scripted", action="store_true")
    p.add_argument("--designs", nargs="+", default=ALL_DESIGNS)
    p.add_argument("--conditions", nargs="+", default=ALL_CONDITIONS)
    p.add_argument("--skip-gates", action="store_true")
    args = p.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)
    metrics_path = os.path.join(args.out, "metrics_decompose.json")
    results_path = os.path.join(args.out, "results.md")

    cfg = FPGAConfig.from_yaml(args.config) if args.config else FPGAConfig()
    cfg.max_generations = args.gens
    cfg.pop_size = args.pop
    cfg.output_dir = os.path.join(args.out, "runs")

    if not args.skip_gates and not args.scripted:
        skip = []
        for design in args.designs:
            seed_cand, suite, _ = archx_loader.load(design, with_mutator=False)
            if not archx_loader.is_usable(seed_cand, suite):
                logger.warning("Gate FAILED for '%s' — skip", design)
                skip.append(design)
        args.designs = [d for d in args.designs if d not in skip]

    writer = IncrementalWriter(metrics_path)
    if os.path.exists(metrics_path):
        writer.results = metrics.load_metrics(metrics_path)

    run_matrix(
        args.designs,
        args.conditions,
        cfg,
        args.seeds,
        scripted=args.scripted,
        writer=writer,
    )

    all_results = writer.results
    md = _render_table(all_results, args.designs)
    with open(results_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(md)
    logger.info("Results written to %s", results_path)


if __name__ == "__main__":
    main()
