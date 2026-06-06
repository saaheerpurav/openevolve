"""
Command-line interface for TDES.

    python tdes-run.py <seed_dir> <suite.py> [--config cfg.yaml] [--gens N]
                       [--pop N] [--scripted] [--output DIR]

``--scripted`` runs fully offline using a deterministic mutator that the suite
file must expose via ``get_scripted_mutator()``; otherwise an LLM ensemble is
built from the ``llm:`` section of the config.
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import os
import sys
from typing import Optional

from openevolve.tdes.config import TDESConfig
from openevolve.tdes.controller import TDESController, load_seed_codebase
from openevolve.tdes.mutation import LLMMutator, Mutator
from openevolve.tdes.test_suite import TDESTestSuite


def _import_suite_module(path: str):
    spec = importlib.util.spec_from_file_location("_tdes_suite_module_cli", os.path.abspath(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_mutator(args, config: TDESConfig, suite_module) -> Mutator:
    if args.scripted:
        if not hasattr(suite_module, "get_scripted_mutator"):
            raise SystemExit("--scripted requires the suite file to define get_scripted_mutator()")
        return suite_module.get_scripted_mutator()

    if config.llm is None or not config.llm.llm.models:
        raise SystemExit("LLM mode requires a config with an `llm:` section (or pass --scripted).")
    from openevolve.llm.ensemble import LLMEnsemble

    ensemble = LLMEnsemble(config.llm.llm.models)
    return LLMMutator(ensemble, diff_based=config.diff_based)


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tdes-run", description="Run Test-Driven Evolutionary Synthesis"
    )
    parser.add_argument("seed_dir", help="Directory of seed <module>.py files")
    parser.add_argument("suite_file", help="Python file defining the TDES test suite")
    parser.add_argument("--config", help="YAML config (tdes: and llm: sections)")
    parser.add_argument("--gens", type=int, help="Override max generations")
    parser.add_argument("--pop", type=int, help="Override population size")
    parser.add_argument("--scripted", action="store_true", help="Use offline scripted mutator")
    parser.add_argument("--output", help="Output directory")
    parser.add_argument("--no-sandbox", action="store_true", help="Run candidate code in-process")
    args = parser.parse_args(argv)

    config = TDESConfig.from_yaml(args.config) if args.config else TDESConfig()
    if args.gens is not None:
        config.max_generations = args.gens
    if args.pop is not None:
        config.pop_size = args.pop
    if args.output:
        config.output_dir = args.output
    if args.no_sandbox:
        config.sandbox = False

    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    suite = TDESTestSuite.load_from_file(args.suite_file)
    suite_module = _import_suite_module(args.suite_file)
    seed = load_seed_codebase(args.seed_dir, suite.module_names)
    mutator = _build_mutator(args, config, suite_module)

    controller = TDESController(seed, suite, mutator, config)
    result = controller.run()

    print("\n=== TDES result ===")
    print(f"generations run : {result.generations_run}")
    print(f"escalated       : {result.escalated}")
    print(f"best            : {result.best.vector.summary()}")
    print(f"output          : {os.path.abspath(config.output_dir)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
