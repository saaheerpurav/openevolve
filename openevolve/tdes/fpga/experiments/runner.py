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

from openevolve.tdes.fpga import ablation, baselines, benchmark_loader, metrics
from openevolve.tdes.fpga.config import FPGAConfig
from openevolve.tdes.fpga.mutation import VerilogLLMMutator

logger = logging.getLogger(__name__)

_LOADERS = {
    "rtllm": benchmark_loader.load_rtllm,
    "archxbench": benchmark_loader.load_archxbench,
    "resbench": benchmark_loader.load_resbench,
}

TDES_CONDITIONS = list(ablation.CONDITIONS)
BASELINE_CONDITIONS = ["single_agent", "pass5"]
ALL_CONDITIONS = TDES_CONDITIONS + BASELINE_CONDITIONS


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
) -> Optional[metrics.RunMetrics]:
    """Run a single experiment cell; returns None if the design is unusable/skipped."""
    loader = _LOADERS[benchmark]
    seed_cand, suite, ref_mutator = loader(design, with_mutator=True, decompose=decompose)

    if require_usable and not benchmark_loader.is_usable(seed_cand, suite):
        logger.info("skip %s/%s: not a usable evolution target", benchmark, design)
        return None

    cfg = _clone_config(config, seed)

    if condition in ablation.CONDITIONS:
        kwargs, transform = ablation.CONDITIONS[condition]
        run_suite = transform(suite) if transform else suite
        mutator = (
            ref_mutator if scripted else VerilogLLMMutator(ensemble, diff_based=cfg.diff_based)
        )
        if mutator is None:
            return None
        controller = ablation.AblationController(seed_cand, run_suite, mutator, cfg, **kwargs)
        result = controller.run()
        return metrics.from_result(
            design,
            condition,
            seed,
            result,
            total_tests=len(run_suite.tests),
            crossover=controller.crossover_stats.as_dict(),
        )

    if condition in BASELINE_CONDITIONS:
        if scripted or ensemble is None:
            logger.info("skip baseline %s for %s (needs LLM)", condition, design)
            return None
        if condition == "single_agent":
            br = baselines.single_agent_repair(
                seed_cand, suite, ensemble, rounds=cfg.max_generations, timeout=cfg.suite_timeout
            )
        else:  # pass5
            desc = str(seed_cand.metadata.get("design", design))
            br = baselines.pass_at_k(
                list(seed_cand.modules)[0],
                _description(suite),
                suite,
                ensemble,
                k=5,
                timeout=cfg.suite_timeout,
            )
        return _baseline_metrics(design, condition, seed, br)

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
) -> List[metrics.RunMetrics]:
    """Run the full (design x condition x seed) matrix."""
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
                    )
                except Exception as e:  # keep the sweep alive
                    logger.warning(
                        "cell %s/%s/%s seed=%s failed: %s", benchmark, design, condition, seed, e
                    )
                    rm = None
                if rm is not None:
                    results.append(rm)
                    logger.info(
                        "%s/%s [%s] seed=%s -> %d/%d %s",
                        benchmark,
                        design,
                        condition,
                        seed,
                        rm.total_passes,
                        rm.total_tests,
                        "SOLVED" if rm.solved else "",
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


def _baseline_metrics(design, condition, seed, br) -> metrics.RunMetrics:
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
    )
