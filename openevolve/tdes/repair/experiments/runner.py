"""
Experiment driver for TDES-Repair.

Runs one ``(task, variant, condition, seed)`` cell and returns a
:class:`~openevolve.tdes.fpga.metrics.RunMetrics` (the suite-agnostic metrics
module the combopt layer also reuses). Evolutionary conditions come from
``repair.controllers.CONDITIONS``; ``single_shot`` is the non-evolutionary
baseline. Scripted mode swaps the LLM for each variant's reference-injecting
mutator so the harness mechanics validate offline.
"""

from __future__ import annotations

import copy
import logging
import os
from typing import List, Optional, Sequence, Tuple

from openevolve.tdes import selection
from openevolve.tdes.config import TDESConfig
from openevolve.tdes.fpga import metrics
from openevolve.tdes.repair import baselines, controllers, loader
from openevolve.tdes.repair.mutation import RepairLLMMutator

logger = logging.getLogger(__name__)

TDES_CONDITIONS = list(controllers.CONDITIONS)
BASELINE_CONDITIONS = ["single_shot"]
ALL_CONDITIONS = ["single_shot", "random_crossover", "tdes_no_crossover", "tdes_full"]


class _CountingEnsemble:
    """Transparent proxy that counts LLM generate calls (per-cell efficiency metric)."""

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
    """Records per-generation (calls, best-passes) and per-module solve timeline."""

    _counter = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls_trajectory = []  # (generation, cumulative_calls, best_total_passes)
        self.module_first_solved = {}

    def _record_history(self, gen, population, *, stagnated=False, solved=False):
        super()._record_history(gen, population, stagnated=stagnated, solved=solved)
        calls = getattr(self._counter, "calls", 0)
        best = selection.best(population)
        best_passes = best.vector.total_passes if best and best.vector else 0
        self.calls_trajectory.append((gen, calls, best_passes))
        for cand in population:
            if cand.vector is None:
                continue
            for res in cand.vector.results.values():
                if res.passed:
                    self.module_first_solved.setdefault(res.module, gen)


_INSTRUMENTED_CACHE = {}


def _instrumented(cls):
    if cls not in _INSTRUMENTED_CACHE:
        _INSTRUMENTED_CACHE[cls] = type(
            f"_Instrumented{cls.__name__}", (_InstrumentedMixin, cls), {}
        )
    return _INSTRUMENTED_CACHE[cls]


def build_ensemble(config: TDESConfig):
    if config.llm is None or not config.llm.llm.models:
        raise ValueError("LLM mode requires a config with an `llm:` section")
    from openevolve.llm.ensemble import LLMEnsemble

    return LLMEnsemble(config.llm.llm.models)


def run_cell(
    task: str,
    variant: str,
    condition: str,
    config: TDESConfig,
    *,
    seed: int = 0,
    ensemble=None,
    scripted: bool = False,
) -> Optional[metrics.RunMetrics]:
    seed_cand, suite, ref_mutator = loader.load_variant(task, variant, with_mutator=True)
    design = f"{task}/{variant}"
    cfg = _clone_config(config, task, variant, condition, seed)
    counter = _CountingEnsemble(ensemble) if ensemble is not None else None

    if condition in controllers.CONDITIONS:
        cls, kwargs = controllers.CONDITIONS[condition]
        mutator = ref_mutator if scripted else RepairLLMMutator(counter)
        ctrl = _instrumented(cls)(seed_cand, suite, mutator, cfg, **kwargs)
        ctrl._counter = counter
        result = ctrl.run()
        crossover = ctrl.crossover_stats.as_dict()
        if hasattr(ctrl, "raw_lift_total"):
            crossover["raw_lift_total"] = ctrl.raw_lift_total
        return metrics.from_result(
            design,
            condition,
            seed,
            result,
            total_tests=len(suite.tests),
            crossover=crossover,
            llm_calls=getattr(counter, "calls", 0),
            calls_trajectory=ctrl.calls_trajectory,
            module_first_solved=ctrl.module_first_solved,
        )

    if condition in BASELINE_CONDITIONS:
        if scripted:
            br = baselines.single_shot(
                seed_cand,
                suite,
                mutator=ref_mutator,
                sandbox=cfg.sandbox,
                timeout=cfg.suite_timeout,
            )
        else:
            if ensemble is None:
                raise ValueError("single_shot requires an LLM ensemble (or scripted=True)")
            br = baselines.single_shot(
                seed_cand,
                suite,
                counter,
                sandbox=cfg.sandbox,
                timeout=cfg.suite_timeout,
            )
        calls = getattr(counter, "calls", 0)
        return metrics.RunMetrics(
            design=design,
            condition=condition,
            seed=seed,
            solved=br.solved,
            total_passes=br.total_passes,
            total_tests=br.total_tests,
            generations_run=br.rounds_used,
            escalated=False,
            trajectory=br.trajectory,
            crossover=None,
            llm_calls=calls,
            calls_to_solve=calls if br.solved else None,
        )

    raise ValueError(f"unknown condition: {condition}")


class ResumableWriter:
    """Incremental metrics persistence that skips already-completed cells on resume."""

    def __init__(self, out_path: str):
        self.out_path = out_path
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        self.results: List[metrics.RunMetrics] = (
            metrics.load_metrics(out_path) if os.path.exists(out_path) else []
        )

    def done(self, design: str, condition: str, seed: int) -> bool:
        return any(
            m.design == design and m.condition == condition and m.seed == seed for m in self.results
        )

    def __call__(self, rm: metrics.RunMetrics) -> None:
        self.results.append(rm)
        metrics.save_metrics(self.results, self.out_path)


def run_matrix(
    cells: Sequence[Tuple[str, str]],
    conditions: Sequence[str],
    config: TDESConfig,
    *,
    seeds: Sequence[int],
    scripted: bool = False,
    writer: Optional[ResumableWriter] = None,
    on_result=None,
) -> List[metrics.RunMetrics]:
    """Run the full (task/variant x condition x seed) matrix, skipping cells the
    writer has already persisted (resumable sweeps)."""
    ensemble = None if scripted else build_ensemble(config)

    results: List[metrics.RunMetrics] = []
    for task, variant in cells:
        design = f"{task}/{variant}"
        for condition in conditions:
            for seed in seeds:
                if writer is not None and writer.done(design, condition, seed):
                    logger.info("skip completed cell %s [%s] seed=%s", design, condition, seed)
                    continue
                try:
                    rm = run_cell(
                        task,
                        variant,
                        condition,
                        config,
                        seed=seed,
                        ensemble=ensemble,
                        scripted=scripted,
                    )
                except Exception as e:  # keep the sweep alive
                    logger.warning("cell %s [%s] seed=%s failed: %s", design, condition, seed, e)
                    rm = None
                if rm is not None:
                    results.append(rm)
                    if writer is not None:
                        writer(rm)
                    if on_result is not None:
                        on_result(rm)
                    logger.info(
                        "%s [%s] seed=%s -> %d/%d %s (calls=%d, to_solve=%s)",
                        design,
                        condition,
                        seed,
                        rm.total_passes,
                        rm.total_tests,
                        "SOLVED" if rm.solved else "",
                        rm.llm_calls,
                        rm.calls_to_solve,
                    )
    return results


def _clone_config(
    config: TDESConfig, task: str, variant: str, condition: str, seed: int
) -> TDESConfig:
    cfg = copy.copy(config)
    cfg.random_seed = (config.random_seed or 0) + seed
    cfg.output_dir = os.path.join(config.output_dir, task, variant, condition, f"seed_{seed}")
    return cfg
