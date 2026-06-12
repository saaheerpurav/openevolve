"""
TDES-Repair: multi-module Python software-repair benchmarks for TDES.

An additive layer (no base ``tdes/*`` file is modified) that evaluates the
complementary-coverage crossover claim on repair tasks where bug *placement*
is the experimental variable: each task ships 6 variants — 4 with bugs split
across modules (crossover-favorable) and 2 co-located controls (crossover
should be neutral). Conditions: ``single_shot`` (LLM baseline),
``random_crossover`` (unconstrained GA baseline), ``tdes_no_crossover``
(ablation), ``tdes_full``.

Tasks:
  * ``pipeline`` — ingest / transform / aggregate over delimited records.
  * ``api``      — auth / router / validator, framework-free request handling.

Entry point: ``python -m openevolve.tdes.repair.experiments.run_campaign``.
"""

from openevolve.tdes.repair.loader import (
    TASKS,
    is_usable,
    list_variants,
    load_variant,
    reference_modules,
    reference_mutator,
    verify_complementary,
)

__all__ = [
    "TASKS",
    "is_usable",
    "list_variants",
    "load_variant",
    "reference_modules",
    "reference_mutator",
    "verify_complementary",
]
