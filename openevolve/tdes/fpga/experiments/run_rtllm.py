"""
Run TDES (and baselines/ablations) on RTLLM v2 designs.

    python -m openevolve.tdes.fpga.experiments.run_rtllm \
        --config openevolve/tdes/fpga/experiments/configs/tdes_full.yaml \
        --conditions tdes_full single_agent pass5 --seeds 0 1 2

Use ``--scripted`` to validate the harness offline (reference-injecting mutator;
baselines skipped). ``--designs`` overrides the default sample.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from openevolve.tdes.fpga import metrics
from openevolve.tdes.fpga.config import FPGAConfig
from openevolve.tdes.fpga.experiments import runner

try:  # tables use ✓/✗; force UTF-8 so Windows consoles don't choke
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# A default sample spanning RTLLM categories (override with --designs).
DEFAULT_DESIGNS = [
    "adder_8bit",
    "adder_16bit",
    "multi_16bit",
    "comparator_3bit",
    "accu",
]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="TDES on RTLLM v2")
    p.add_argument("--config")
    p.add_argument("--designs", nargs="*", default=None)
    p.add_argument("--conditions", nargs="*", default=["tdes_full"])
    p.add_argument("--seeds", nargs="*", type=int, default=[0])
    p.add_argument("--scripted", action="store_true")
    p.add_argument("--no-decompose", action="store_true")
    p.add_argument("--out", default="tdes_fpga_results/rtllm.json")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    config = FPGAConfig.from_yaml(args.config) if args.config else FPGAConfig()
    designs = args.designs or DEFAULT_DESIGNS

    results = runner.run_matrix(
        "rtllm",
        designs,
        args.conditions,
        config,
        seeds=args.seeds,
        scripted=args.scripted,
        decompose=not args.no_decompose,
    )

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    metrics.save_metrics(results, args.out)
    print("\n## Table 1: method comparison (RTLLM)\n")
    print(metrics.render_table1(results, args.conditions))
    print("\n## Table 2: crossover analysis\n")
    print(metrics.render_table2(results))
    print(f"\nraw metrics -> {os.path.abspath(args.out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
