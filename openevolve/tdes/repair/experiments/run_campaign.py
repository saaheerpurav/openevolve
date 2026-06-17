"""
TDES-Repair campaign driver.

Stages:
  * ``--pilot`` — calibration: ``single_shot`` only, across every variant.
    Target band: 20–60% solve rate. Above it, the bugs are too easy for the
    model and every condition will ceiling (the FPGA Exp 4 lesson); harden
    them before paying for the full matrix.
  * ``--full``  — all 4 conditions x every variant x seeds (the 144-cell
    matrix at the default 2 tasks x 6 variants x 4 conditions x 3 seeds).

Cells already present in ``--out`` are skipped, so both stages are resumable
and the pilot's cells are reused by the full run. Loader gates (reference
passes all tests, seed fails, complementarity holds) run first and abort the
campaign if any variant is misconfigured.

    set ANTHROPIC_API_KEY=...
    python -m openevolve.tdes.repair.experiments.run_campaign --pilot
    python -m openevolve.tdes.repair.experiments.run_campaign --full
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from openevolve.tdes.config import TDESConfig
from openevolve.tdes.repair import loader
from openevolve.tdes.repair.experiments import analysis, runner

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = os.path.join(os.path.dirname(__file__), "configs", "anthropic_haiku.yaml")


def _load_config(path: str, scripted: bool) -> TDESConfig:
    """Load the campaign config; in scripted mode only the ``tdes:`` section.

    The ``llm:`` section resolves ``${ANTHROPIC_API_KEY}`` at parse time, which
    must not be required for offline scripted validation.
    """
    if not scripted:
        return TDESConfig.from_yaml(path)
    import yaml

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    tdes_section = dict(raw.get("tdes", {}) or {})
    valid = {f for f in TDESConfig.__dataclass_fields__ if f != "llm"}
    return TDESConfig(**{k: v for k, v in tdes_section.items() if k in valid})


def _check_gates(cells) -> bool:
    ok = True
    for task, variant in cells:
        if not loader.is_usable(task, variant):
            logger.error("gate failed: %s/%s is not a usable evolution target", task, variant)
            ok = False
        if not loader.verify_complementary(task, variant):
            logger.error("gate failed: %s/%s complementarity check", task, variant)
            ok = False
    return ok


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    stage = parser.add_mutually_exclusive_group(required=True)
    stage.add_argument("--pilot", action="store_true", help="single_shot calibration stage")
    stage.add_argument("--full", action="store_true", help="all 4 conditions")
    parser.add_argument("--config", default=_DEFAULT_CONFIG)
    parser.add_argument("--tasks", nargs="+", default=list(loader.TASKS), choices=loader.TASKS)
    parser.add_argument("--variants", nargs="+", default=None, help="restrict to these variants")
    parser.add_argument(
        "--conditions",
        nargs="+",
        default=None,
        choices=runner.ALL_CONDITIONS,
        help="override the stage's condition set",
    )
    parser.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    parser.add_argument("--out", default="tdes_repair_results/metrics_repair.json")
    parser.add_argument("--gens", type=int, default=None)
    parser.add_argument("--pop", type=int, default=None)
    parser.add_argument("--scripted", action="store_true", help="offline harness validation")
    parser.add_argument("--skip-gates", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    config = _load_config(args.config, args.scripted)
    if args.gens is not None:
        config.max_generations = args.gens
    if args.pop is not None:
        config.pop_size = args.pop

    conditions = args.conditions or (["single_shot"] if args.pilot else runner.ALL_CONDITIONS)
    cells = [
        (task, variant)
        for task in args.tasks
        for variant in loader.list_variants(task)
        if args.variants is None or variant in args.variants
    ]
    logger.info(
        "campaign: %d cells x %d conditions x %d seeds",
        len(cells),
        len(conditions),
        len(args.seeds),
    )

    if not args.skip_gates and not _check_gates(cells):
        logger.error("aborting: loader gates failed")
        return 1

    writer = runner.ResumableWriter(args.out)
    runner.run_matrix(
        cells, conditions, config, seeds=args.seeds, scripted=args.scripted, writer=writer
    )

    print()
    print(analysis.render_report(writer.results))
    if args.pilot:
        rows = [m for m in writer.results if m.condition == "single_shot"]
        if rows:
            rate = sum(1 for m in rows if m.solved) / len(rows)
            print(
                f"\nPilot single_shot solve rate: {rate:.0%} "
                f"(target band 20-60%; above it, harden the bugs before --full)"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
