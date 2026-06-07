"""
FPGA controller for TDES-FPGA.

``TDESController`` is language-agnostic above the test runner, so a
``VerilogTestSuite`` (which duck-types ``TDESTestSuite``) drives it directly.
``FPGAController`` is a thin convenience wrapper that supplies Verilog defaults
(``FPGAConfig``) and a Verilog seed loader.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

from openevolve.tdes.controller import TDESController, TDESResult
from openevolve.tdes.fpga.config import FPGAConfig
from openevolve.tdes.fpga.verilog_suite import VerilogTestSuite
from openevolve.tdes.mutation import Mutator
from openevolve.tdes.types import Candidate


def load_verilog_seed(seed_dir: str, module_names: List[str]) -> Candidate:
    """Load a seed Candidate from a directory of ``<module>.v`` files."""
    modules: Dict[str, str] = {}
    for name in module_names:
        path = os.path.join(seed_dir, f"{name}.v")
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"seed module '{name}' not found at {path} "
                f"(suite declares modules: {module_names})"
            )
        with open(path, "r", encoding="utf-8") as f:
            modules[name] = f.read()
    return Candidate(modules=modules, generation=0, metadata={"origin": "seed"})


class FPGAController:
    """Wraps TDESController for Verilog evolution with FPGA defaults."""

    def __init__(
        self,
        seed: Candidate,
        suite: VerilogTestSuite,
        mutator: Mutator,
        config: Optional[FPGAConfig] = None,
    ):
        self.config = config or FPGAConfig()
        self._inner = TDESController(seed, suite, mutator, self.config)
        # expose memory/history for experiment harnesses
        self.memory = self._inner.memory
        self.suite = suite

    def run(self) -> TDESResult:
        return self._inner.run()

    async def run_async(self) -> TDESResult:
        return await self._inner.run_async()

    @property
    def history(self):
        return self._inner.history
