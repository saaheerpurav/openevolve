"""
Yosys synthesis wrapper for TDES-FPGA.

Synthesis metrics (LUT / FF / cell counts) form the *system-level* tests in the
TDES hierarchy: a design that simulates correctly but blows its resource budget
is not a good solution. A system-level :class:`~openevolve.tdes.fpga.verilog_suite.VerilogTest`
with ``testbench_source = "__synthesis__ lut<500 ff<200"`` is dispatched here.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from openevolve.tdes.fpga.verilog_runner import TestOutcome, find_tool

logger = logging.getLogger(__name__)

_SYNTH_TARGETS = {
    "ice40": "synth_ice40",
    "ecp5": "synth_ecp5",
    "xilinx": "synth_xilinx",
    "generic": "synth",
}


@dataclass
class SynthesisResult:
    ok: bool
    luts: Optional[int] = None
    ffs: Optional[int] = None
    cells: Optional[int] = None
    error: str = ""
    raw: Dict = field(default_factory=dict)


def yosys_available() -> bool:
    return bool(find_tool(["yosys"]))


def synthesize(
    modules: Dict[str, str],
    *,
    top_module: Optional[str] = None,
    target: str = "ice40",
    timeout: int = 120,
    yosys_path: Optional[str] = None,
) -> SynthesisResult:
    """Run Yosys synthesis and extract resource counts."""
    yosys = yosys_path or find_tool(["yosys"])
    if not yosys:
        return SynthesisResult(False, error="yosys not found on PATH")

    synth_cmd = _SYNTH_TARGETS.get(target, "synth")
    top_arg = f" -top {top_module}" if top_module else ""

    with tempfile.TemporaryDirectory(prefix="tdes_synth_") as tmp:
        read_lines = []
        for name, source in modules.items():
            path = os.path.join(tmp, f"{name}.v")
            with open(path, "w", encoding="utf-8") as f:
                f.write(source)
            read_lines.append(f"read_verilog {name}.v")
        script = "\n".join(
            read_lines
            + [
                f"{synth_cmd}{top_arg}",
                "tee -o stats.txt stat -json",
                "write_json design.json",
            ]
        )
        script_path = os.path.join(tmp, "synth.ys")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script)

        try:
            proc = subprocess.run(
                [yosys, "-q", "-s", "synth.ys"],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmp,
            )
        except subprocess.TimeoutExpired:
            return SynthesisResult(False, error=f"synthesis exceeded {timeout}s")
        if proc.returncode != 0:
            return SynthesisResult(False, error=_first_error(proc.stderr or proc.stdout))

        return _parse_stats(proc.stdout, os.path.join(tmp, "stats.txt"))


def _first_error(text: str) -> str:
    for line in (text or "").splitlines():
        if "ERROR" in line.upper():
            return line.strip()[:400]
    return (text or "").strip()[-400:] or "unknown synthesis error"


def _parse_stats(stdout: str, stats_txt: str) -> SynthesisResult:
    """Parse the JSON emitted by Yosys' ``stat -json``."""
    blob = ""
    if os.path.exists(stats_txt):
        with open(stats_txt, "r", encoding="utf-8") as f:
            blob = f.read()
    if not blob.strip():
        blob = stdout

    data = _extract_json(blob)
    if data is None:
        return SynthesisResult(False, error="could not parse Yosys stat output")

    luts = ffs = cells = 0
    modules_stat = data.get("modules", {})
    for _name, mod in modules_stat.items():
        cells += int(mod.get("num_cells", 0))
        for cell_type, count in (mod.get("num_cells_by_type", {}) or {}).items():
            ct = cell_type.lower()
            if "lut" in ct or "lc" in ct:
                luts += int(count)
            if "dff" in ct or "ff" in ct or cell_type.startswith("$_DFF"):
                ffs += int(count)
    return SynthesisResult(True, luts=luts, ffs=ffs, cells=cells, raw=data)


def _extract_json(text: str) -> Optional[dict]:
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start : i + 1])
                        if isinstance(obj, dict) and "modules" in obj:
                            return obj
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    return None


def evaluate_synthesis_test(
    modules: Dict[str, str],
    *,
    top_module: Optional[str],
    spec: Dict[str, int],
    config: Optional[dict] = None,
) -> "TestOutcome":
    """Synthesize and check resource budgets; return a TestOutcome.

    ``spec`` maps a resource key (``lut``/``ff``/``cells``) to its upper bound.
    """
    config = config or {}
    target = config.get("target", "ice40")
    result = synthesize(modules, top_module=top_module, target=target)
    if not result.ok:
        return TestOutcome(False, "synthesis", f"synthesis failed: {result.error}")

    measured = {"lut": result.luts, "ff": result.ffs, "cells": result.cells}
    violations = []
    for key, budget in spec.items():
        got = measured.get(key)
        if got is not None and got > budget:
            violations.append(f"expected < {budget} {key.upper()}s, got {got}")
    if violations:
        return TestOutcome(False, f"top={top_module}", "; ".join(violations))
    return TestOutcome(True, "n/a", "")
