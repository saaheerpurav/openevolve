"""
Run TDES (and baselines/ablations) on ArchXBench designs.

    python -m openevolve.tdes.fpga.experiments.run_archxbench \
        --config .../configs/tdes_full.yaml --conditions tdes_full single_agent \
        --designs aes_sbox cla_8bit --seeds 0 1 2

ArchXBench ships no reference RTL, so usability gating and the offline scripted
mutator are unavailable; runs use the LLM and the native testbench as a
(rich ``[PASS]/[FAIL]``) system-level test.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from openevolve.tdes.fpga import metrics
from openevolve.tdes.fpga.config import FPGAConfig
from openevolve.tdes.fpga.experiments import runner

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Verified combinational designs (correct->1/1, wrong->0/1 confirmed). Their
# testbenches use machine-parseable pass/fail tallies. booth/pipelined designs
# print bare PASS/FAIL table cells and are excluded. Override with --designs.
DEFAULT_DESIGNS = [
    "rca_32bit",  # level-1a ripple-carry adder
    "cla_8bit",  # level-1a carry-lookahead adder
    "brent_kung_32bit",  # level-1c parallel-prefix adder
    "wallace_multiplier",  # level-1c Wallace-tree multiplier
    "dadda_multiplier",  # level-1c Dadda multiplier
]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="TDES on ArchXBench")
    p.add_argument("--config")
    p.add_argument("--designs", nargs="*", default=None)
    p.add_argument("--conditions", nargs="*", default=["tdes_full"])
    p.add_argument("--seeds", nargs="*", type=int, default=[0])
    p.add_argument("--out", default="tdes_fpga_results/archxbench.json")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    config = FPGAConfig.from_yaml(args.config) if args.config else FPGAConfig()
    designs = args.designs or DEFAULT_DESIGNS

    results = runner.run_matrix(
        "archxbench",
        designs,
        args.conditions,
        config,
        seeds=args.seeds,
        scripted=False,
        decompose=False,  # ArchXBench tbs are not golden-expr decomposable
        require_usable=False,  # ArchXBench ships no reference RTL to validate against
    )

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    metrics.save_metrics(results, args.out)
    print("\n## Table 1: method comparison (ArchXBench)\n")
    print(metrics.render_table1(results, args.conditions))
    print(f"\nraw metrics -> {os.path.abspath(args.out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
