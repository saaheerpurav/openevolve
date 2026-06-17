"""
Core experiment driver for TDES-FPGA.

Runs one (benchmark, design, condition, seed) cell and returns a
:class:`~openevolve.tdes.fpga.metrics.RunMetrics`. Conditions cover the TDES
ablation variants (via ``AblationController``) plus the ``single_agent`` and
``pass5`` baselines.

Two mutation modes:
  * **llm** — build an ``LLMEnsemble`` from the config (real experiments).
  * **scripted** — use each design's reference-injecting mutator (offline; for
    validating the harness mechanics without an API key). Baselines require an
    LLM and are skipped in scripted mode.
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional

from openevolve.tdes import selection
from openevolve.tdes.fpga import ablation, baselines, benchmark_loader, metrics
from openevolve.tdes.fpga.config import FPGAConfig
from openevolve.tdes.fpga.enhanced import ENHANCED_CONDITIONS, EnhancedFPGAController
from openevolve.tdes.fpga.mutation import VerilogLLMMutator
from openevolve.tdes.fpga.experiments import hierarchical_archx

logger = logging.getLogger(__name__)

_LOADERS = {
    "rtllm": benchmark_loader.load_rtllm,
    "archxbench": benchmark_loader.load_archxbench,
    "resbench": benchmark_loader.load_resbench,
    "hier": hierarchical_archx.load_hierarchical,
}


class _CountingEnsemble:
    """Transparent proxy that counts LLM generate calls (Exp 5 efficiency metric).

    Wraps a real ``LLMEnsemble`` and increments ``calls`` on each generation
    method. One wrapper is created per experiment cell so its count is per-run.
    """

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
    """Records per-generation (calls, best-passes) and per-module solve timeline.

    Mixed in front of a concrete controller so its ``_record_history`` override
    runs first (the base hook is called once per generation by the controller).
    ``_counter`` is attached by the runner after construction.
    """

    _counter = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls_trajectory = []  # (generation, cumulative_calls, best_total_passes)
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


class _InstrumentedFallback(_InstrumentedMixin, ablation.SingleAgentFallbackController):
    pass


def _instrumented_enhanced(*args, **kwargs):
    """Factory: _InstrumentedMixin + EnhancedFPGAController, constructed with given args."""

    class _InstrumentedEnhanced(_InstrumentedMixin, EnhancedFPGAController):
        pass

    return _InstrumentedEnhanced(*args, **kwargs)


class _NoCegisMutator:
    """Strips CEGIS feedback before delegating (the ``tdes_no_cegis`` ablation).

    The controller still accepts/rejects edits by the test vector, but the LLM
    no longer receives the structured ``(description, failing input, error)``
    feedback — isolating the contribution of CEGIS. Memory is left intact (that
    is a separate ablation).
    """

    def __init__(self, inner):
        self._inner = inner

    async def propose(self, *, candidate, module, feedback, memory_text, generation):
        return await self._inner.propose(
            candidate=candidate,
            module=module,
            feedback=[],
            memory_text=memory_text,
            generation=generation,
        )


# Extra (non-base) ablation conditions handled by this runner. ``tdes_no_cegis``
# reuses the full-TDES controller kwargs but wraps the mutator to drop feedback.
_EXTRA_CONDITIONS = {"tdes_no_cegis": (dict(enable_crossover=True, enable_memory=True), None)}

TDES_CONDITIONS = list(ablation.CONDITIONS)
ENHANCED_COND_NAMES = list(ENHANCED_CONDITIONS)
BASELINE_CONDITIONS = ["single_agent", "pass5", "best_of_30"]
ALL_CONDITIONS = TDES_CONDITIONS + ENHANCED_COND_NAMES + BASELINE_CONDITIONS


def build_ensemble(config: FPGAConfig):
    if config.llm is None or not config.llm.llm.models:
        raise ValueError("LLM mode requires a config with an `llm:` section")
    from openevolve.llm.ensemble import LLMEnsemble

    return LLMEnsemble(config.llm.llm.models)


def run_cell(
    benchmark: str,
    design: str,
    condition: str,
    config: FPGAConfig,
    *,
    seed: int = 0,
    ensemble=None,
    scripted: bool = False,
    decompose: bool = True,
    require_usable: bool = True,
    controller: str = "auto",
) -> Optional[metrics.RunMetrics]:
    """Run a single experiment cell; returns None if the design is unusable/skipped.

    ``controller``:
      * ``"auto"``    — ``SingleAgentFallbackController`` (degrades to single-agent
        on single-module designs; full population/crossover on multi-module).
      * ``"diverse"`` — ``DiverseScheduleController`` (randomized per-candidate
        module order; the diversity complementary-coverage crossover needs on
        multi-module problems). Use for the hierarchical/crossover experiments.
    """
    loader = _LOADERS[benchmark]
    seed_cand, suite, ref_mutator = loader(design, with_mutator=True, decompose=decompose)

    if require_usable and not benchmark_loader.is_usable(seed_cand, suite):
        logger.info("skip %s/%s: not a usable evolution target", benchmark, design)
        return None

    cfg = _clone_config(config, seed)
    # Per-cell call counter (wraps the shared ensemble; None in scripted mode).
    counter = _CountingEnsemble(ensemble) if ensemble is not None else None

    if condition in ablation.CONDITIONS or condition in _EXTRA_CONDITIONS:
        kwargs, transform = (
            ablation.CONDITIONS[condition]
            if condition in ablation.CONDITIONS
            else _EXTRA_CONDITIONS[condition]
        )
        run_suite = transform(suite) if transform else suite
        mutator = ref_mutator if scripted else VerilogLLMMutator(counter, diff_based=cfg.diff_based)
        if mutator is None:
            return None
        if condition == "tdes_no_cegis" and not scripted:
            mutator = _NoCegisMutator(mutator)
        controller_cls = _InstrumentedDiverse if controller == "diverse" else _InstrumentedFallback
        ctrl = controller_cls(seed_cand, run_suite, mutator, cfg, **kwargs)
        ctrl._counter = counter
        result = ctrl.run()
        return metrics.from_result(
            design,
            condition,
            seed,
            result,
            total_tests=len(run_suite.tests),
            crossover=ctrl.crossover_stats.as_dict(),
            llm_calls=getattr(counter, "calls", 0),
            calls_trajectory=ctrl.calls_trajectory,
            module_first_solved=ctrl.module_first_solved,
        )

    if condition in ENHANCED_CONDITIONS:
        enhanced_kwargs = ENHANCED_CONDITIONS[condition]
        mutator = ref_mutator if scripted else VerilogLLMMutator(counter, diff_based=cfg.diff_based)
        if mutator is None:
            return None
        ctrl = _instrumented_enhanced(seed_cand, suite, mutator, cfg,
                                       ensemble=counter, **enhanced_kwargs)
        ctrl._counter = counter
        result = ctrl.run()
        return metrics.from_result(
            design,
            condition,
            seed,
            result,
            total_tests=len(suite.tests),
            crossover=ctrl.crossover_stats_as_dict(),
            llm_calls=getattr(counter, "calls", 0),
            calls_trajectory=ctrl.calls_trajectory,
            module_first_solved=ctrl.module_first_solved,
        )

    if condition in BASELINE_CONDITIONS:
        if scripted or ensemble is None:
            logger.info("skip baseline %s for %s (needs LLM)", condition, design)
            return None
        if condition == "single_agent":
            br = baselines.single_agent_repair(
                seed_cand, suite, counter, rounds=cfg.max_generations, timeout=cfg.suite_timeout
            )
        elif condition == "best_of_30":
            br = baselines.pass_at_k(
                list(seed_cand.modules)[0],
                _description(suite),
                suite,
                counter,
                k=30,
                timeout=cfg.suite_timeout,
            )
        else:  # pass5
            br = baselines.pass_at_k(
                list(seed_cand.modules)[0],
                _description(suite),
                suite,
                counter,
                k=5,
                timeout=cfg.suite_timeout,
            )
        return _baseline_metrics(
            design, condition, seed, br, llm_calls=getattr(counter, "calls", 0)
        )

    raise ValueError(f"unknown condition: {condition}")


def run_matrix(
    benchmark: str,
    designs: List[str],
    conditions: List[str],
    config: FPGAConfig,
    *,
    seeds: List[int],
    scripted: bool = False,
    decompose: bool = True,
    require_usable: bool = True,
    controller: str = "auto",
    on_result=None,
) -> List[metrics.RunMetrics]:
    """Run the full (design x condition x seed) matrix.

    ``on_result(rm)`` is invoked after each completed cell (e.g. to persist
    metrics incrementally so a long EDA-gated sweep is partial-safe).
    """
    # In LLM mode every condition needs an ensemble; in scripted mode none do.
    ensemble = None if scripted else build_ensemble(config)

    results: List[metrics.RunMetrics] = []
    for design in designs:
        for condition in conditions:
            for seed in seeds:
                try:
                    rm = run_cell(
                        benchmark,
                        design,
                        condition,
                        config,
                        seed=seed,
                        ensemble=ensemble,
                        scripted=scripted,
                        decompose=decompose,
                        require_usable=require_usable,
                        controller=controller,
                    )
                except Exception as e:  # keep the sweep alive
                    logger.warning(
                        "cell %s/%s/%s seed=%s failed: %s", benchmark, design, condition, seed, e
                    )
                    rm = None
                if rm is not None:
                    results.append(rm)
                    if on_result is not None:
                        on_result(rm)
                    logger.info(
                        "%s/%s [%s] seed=%s -> %d/%d %s (calls=%d, to_solve=%s)",
                        benchmark,
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


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _clone_config(config: FPGAConfig, seed: int) -> FPGAConfig:
    import copy

    cfg = copy.copy(config)
    cfg.random_seed = (config.random_seed or 0) + seed
    cfg.output_dir = os.path.join(config.output_dir, f"seed_{seed}")
    return cfg


def _description(suite) -> str:
    return suite.tests[0].description if suite.tests else ""


def _baseline_metrics(design, condition, seed, br, *, llm_calls=0) -> metrics.RunMetrics:
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
        llm_calls=llm_calls,
        calls_to_solve=llm_calls if br.solved else None,
    )
