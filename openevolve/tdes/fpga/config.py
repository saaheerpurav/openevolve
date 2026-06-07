"""
FPGA-specific configuration for TDES-FPGA.

Extends :class:`~openevolve.tdes.config.TDESConfig` with EDA tool paths and
synthesis targets. Reuses the base ``from_yaml`` loader; FPGA-only keys live in
the same ``tdes:`` section.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from openevolve.tdes.config import TDESConfig


@dataclass
class FPGAConfig(TDESConfig):
    """TDES config with EDA tool settings and synthesis targets."""

    # EDA tools (None -> resolve from PATH)
    iverilog_path: Optional[str] = None
    vvp_path: Optional[str] = None
    verilator_path: Optional[str] = None
    yosys_path: Optional[str] = None

    # Simulation
    simulator: str = "iverilog"  # "iverilog" (default) or "verilator"
    verilog_std: str = "2012"  # iverilog -g2012 (SystemVerilog constructs)

    # Synthesis
    synth_target: str = "ice40"  # "ice40" | "ecp5" | "xilinx" | "generic"
    lut_budget: Optional[int] = None
    ff_budget: Optional[int] = None
    timing_budget_ns: Optional[float] = None

    # FPGA runs need a longer per-candidate budget (compile + simulate).
    suite_timeout: int = 120
    output_dir: str = "tdes_fpga_output"
