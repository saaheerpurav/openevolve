"""
CLI for TDES-FPGA.

    python tdes-fpga-run.py --benchmark rtllm --design adder_8bit \
        [--config cfg.yaml] [--gens 5] [--pop 5] [--scripted]

Loads a benchmark design into a (seed, VerilogTestSuite) pair, builds a mutator
(LLM by default; ``--scripted`` requires the design's loader to provide one),
and runs the TDES generational loop via ``FPGAController``.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Optional

from openevolve.tdes.fpga import benchmark_loader
from openevolve.tdes.fpga.config import FPGAConfig
from openevolve.tdes.fpga.fpga_controller import FPGAController
from openevolve.tdes.fpga.mutation import VerilogLLMMutator
from openevolve.tdes.fpga.verilog_runner import tools_available

_LOADERS = {
    "rtllm": benchmark_loader.load_rtllm,
    "archxbench": benchmark_loader.load_archxbench,
    "resbench": benchmark_loader.load_resbench,
}


def _build_mutator(args, config: FPGAConfig):
    if config.llm is None or not config.llm.llm.models:
        raise SystemExit("LLM mode requires a config with an `llm:` section (or use --scripted).")
    from openevolve.llm.ensemble import LLMEnsemble

    ensemble = LLMEnsemble(config.llm.llm.models)
    return VerilogLLMMutator(ensemble, diff_based=config.diff_based)


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(prog="tdes-fpga-run", description="TDES for Verilog RTL")
    parser.add_argument("--benchmark", required=True, choices=list(_LOADERS))
    parser.add_argument("--design", required=True, help="Design name within the benchmark")
    parser.add_argument("--bench-dir", help="Override benchmark root directory")
    parser.add_argument("--config", help="YAML config (tdes: and llm: sections)")
    parser.add_argument("--gens", type=int)
    parser.add_argument("--pop", type=int)
    parser.add_argument("--scripted", action="store_true", help="Use the design's scripted mutator")
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    config = FPGAConfig.from_yaml(args.config) if args.config else FPGAConfig()
    if args.gens is not None:
        config.max_generations = args.gens
    if args.pop is not None:
        config.pop_size = args.pop
    if args.output:
        config.output_dir = args.output

    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if not tools_available():
        print(
            "WARNING: iverilog/vvp not found on PATH; Verilog simulation will fail. "
            "Install the OSS CAD Suite and add its bin/ to PATH.",
            file=sys.stderr,
        )

    loader = _LOADERS[args.benchmark]
    seed, suite, scripted_mutator = loader(args.design, bench_dir=args.bench_dir, with_mutator=True)

    if args.scripted:
        if scripted_mutator is None:
            raise SystemExit(f"design '{args.design}' has no scripted mutator")
        mutator = scripted_mutator
    else:
        mutator = _build_mutator(args, config)

    controller = FPGAController(seed, suite, mutator, config)
    result = controller.run()

    print("\n=== TDES-FPGA result ===")
    print(f"benchmark/design : {args.benchmark}/{args.design}")
    print(f"generations run  : {result.generations_run}")
    print(f"escalated        : {result.escalated}")
    print(f"best             : {result.best.vector.summary()}")
    print(f"output           : {os.path.abspath(config.output_dir)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
