"""
Ablation sweep for TDES-FPGA.

Runs the four TDES ablation conditions (full / no-crossover / no-memory /
scalar) plus the single-agent and Pass@5 baselines across a design set and
multiple seeds, then renders the paper's Table 1 + Table 2.

    python -m openevolve.tdes.fpga.experiments.ablation \
        --benchmark rtllm --config .../configs/tdes_full.yaml \
        --designs adder_8bit multi_16bit --seeds 0 1 2
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

ABLATION_CONDITIONS = [
    "tdes_full",
    "tdes_no_crossover",
    "tdes_no_memory",
    "tdes_scalar",
    "single_agent",
    "pass5",
]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="TDES-FPGA ablation study")
    p.add_argument("--benchmark", default="rtllm", choices=["rtllm", "archxbench", "resbench"])
    p.add_argument("--config")
    p.add_argument("--designs", nargs="*", required=True)
    p.add_argument("--conditions", nargs="*", default=ABLATION_CONDITIONS)
    p.add_argument("--seeds", nargs="*", type=int, default=[0, 1, 2])
    p.add_argument("--scripted", action="store_true")
    p.add_argument("--out", default="tdes_fpga_results/ablation.json")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    config = FPGAConfig.from_yaml(args.config) if args.config else FPGAConfig()

    results = runner.run_matrix(
        args.benchmark,
        args.designs,
        args.conditions,
        config,
        seeds=args.seeds,
        scripted=args.scripted,
        decompose=(args.benchmark == "rtllm"),
    )

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    metrics.save_metrics(results, args.out)

    print("\n## Table 1: TDES vs baselines (✓ = all tests pass)\n")
    print(metrics.render_table1(results, args.conditions))
    print("\n## Table 2: complementary-coverage crossover analysis\n")
    print(metrics.render_table2(results))
    print("\n## Per-condition solve rate\n")
    for c in args.conditions:
        print(f"  {c:20s} {metrics.solve_rate(results, c):.0%}")
    print(f"\nraw metrics -> {os.path.abspath(args.out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
