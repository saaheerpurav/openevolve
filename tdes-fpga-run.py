#!/usr/bin/env python3
"""
Entry point for TDES-FPGA (Verilog RTL evolution).

Usage:
    python tdes-fpga-run.py --benchmark rtllm --design adder_8bit [--gens 5]

Requires the open-source EDA toolchain (iverilog/vvp, optionally yosys) on PATH.
See openevolve/tdes/fpga/benchmarks/README.md for setup.
"""

import sys

from openevolve.tdes.fpga.cli import main

if __name__ == "__main__":
    sys.exit(main())
