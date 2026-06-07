"""
Hierarchical decomposition of flat benchmark testbenches for TDES-FPGA.

Benchmark testbenches are monolithic (one ``initial`` block running all cases).
TDES wants unit / integration / system tiers. For **combinational** designs
whose testbench encodes a golden comparison (``out !== <expr>``), this module
reconstructs the DUT wiring and golden expression and *generates* a tiered suite
(directed edge cases → unit, boundary → integration, randomized → system), each
emitting the ``TDES_PASS/TDES_FAIL`` protocol.

When decomposition is not safely possible (clocked design, no extractable golden
expression), it returns ``[]`` and the caller falls back to running the native
testbench as a single system-level test — so every design remains runnable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from openevolve.tdes.fpga.verilog_suite import VerilogTest
from openevolve.tdes.types import TestLevel

_SIGNAL_DECL_RE = re.compile(
    r"\b(reg|wire)\b\s*(\[[^\]]+\])?\s*([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)\s*;",
)
_INST_RE = re.compile(
    r"^\s*([A-Za-z_]\w*)\s+([A-Za-z_]\w*)\s*\((.*?)\)\s*;", re.DOTALL | re.MULTILINE
)
_GOLDEN_RE = re.compile(r"([A-Za-z_]\w*)\s*!==?\s*\(?\s*([^;{}\)]+?)\s*\)?\s*\)", re.MULTILINE)
_CLOCK_RE = re.compile(r"\b(clk|clock|clk_i|i_clk)\b", re.IGNORECASE)


@dataclass
class _Signal:
    name: str
    width: int  # bit width (1 for scalar)
    is_reg: bool


def _parse_signals(text: str) -> Dict[str, _Signal]:
    signals: Dict[str, _Signal] = {}
    for m in _SIGNAL_DECL_RE.finditer(text):
        kind, rng, names = m.group(1), m.group(2), m.group(3)
        width = _range_width(rng)
        for name in (n.strip() for n in names.split(",")):
            if name:
                signals[name] = _Signal(name, width, kind == "reg")
    return signals


def _range_width(rng: Optional[str]) -> int:
    if not rng:
        return 1
    m = re.match(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]", rng)
    if not m:
        return 1
    hi, lo = int(m.group(1)), int(m.group(2))
    return abs(hi - lo) + 1


def _find_instantiation(tb: str, module_name: str) -> Optional[Tuple[str, str]]:
    """Return (instance_text, port_connection_text) for the DUT instantiation."""
    for m in _INST_RE.finditer(tb):
        if m.group(1) == module_name:
            return m.group(0), m.group(3)
    return None


def _extract_goldens(tb: str) -> List[Tuple[str, str]]:
    """Extract (output_signal, golden_rhs_expression) comparisons."""
    goldens = []
    for m in _GOLDEN_RE.finditer(tb):
        out, rhs = m.group(1).strip(), m.group(2).strip()
        rhs = rhs.rstrip(") ")
        if out and rhs and out != rhs:
            goldens.append((out, rhs))
    # de-dup keep order
    seen = set()
    uniq = []
    for g in goldens:
        if g not in seen:
            seen.add(g)
            uniq.append(g)
    return uniq


def _input_signals(signals: Dict[str, _Signal], port_text: str, goldens) -> List[_Signal]:
    """DUT input drivers: reg signals connected to the DUT (heuristic)."""
    connected = set(re.findall(r"\.\w+\s*\(\s*([A-Za-z_]\w*)\s*\)", port_text))
    golden_outs = {o for o, _ in goldens}
    return [
        s
        for name, s in signals.items()
        if s.is_reg and name in connected and name not in golden_outs
    ]


def _drive(value_kind: str, sig: _Signal) -> str:
    if value_kind == "zero":
        return f"{sig.name} = {sig.width}'b0;"
    if value_kind == "max":
        return f"{sig.name} = {{{sig.width}{{1'b1}}}};"
    if value_kind == "one":
        return f"{sig.name} = {sig.width}'d1;"
    return f"{sig.name} = $random;"


def _check_block(test_id: str, goldens, inputs, label: str) -> str:
    out, rhs = goldens[0]
    input_desc = ",".join(f"{s.name}=%0d" for s in inputs)
    input_args = ", ".join(s.name for s in inputs)
    args = f"{input_args}, ({rhs}), {out}" if input_args else f"({rhs}), {out}"
    fail = (
        f'$display("TDES_FAIL: test_id={test_id} | input={input_desc} | '
        f'expected=%0d | got=%0d", {args});'
    )
    return (
        f"    if ({out} !== ({rhs})) {fail}\n" f'    else $display("TDES_PASS: test_id={test_id}");'
    )


def _build_tb(test_id: str, preamble: str, body: str) -> str:
    return (
        "`timescale 1ns / 1ps\n"
        "module tb;\n"
        f"{preamble}\n"
        "  initial begin\n"
        f"{body}\n"
        "    $finish;\n"
        "  end\n"
        "endmodule\n"
    )


def _directed_body(test_id: str, inputs, goldens, kind: str) -> str:
    drives = "\n".join("    " + _drive(kind, s) for s in inputs)
    return f"{drives}\n    #10;\n{_check_block(test_id, goldens, inputs, kind)}"


def _random_body(test_id: str, inputs, goldens, n: int) -> str:
    drives = "\n".join("      " + _drive("rand", s) for s in inputs)
    out, rhs = goldens[0]
    input_desc = ",".join(f"{s.name}=%0d" for s in inputs)
    input_args = ", ".join(s.name for s in inputs)
    args = f"{input_args}, ({rhs}), {out}"
    return (
        "    integer _i; integer _fails = 0;\n"
        f"    for (_i = 0; _i < {n}; _i = _i + 1) begin\n"
        f"{drives}\n"
        "      #10;\n"
        f"      if ({out} !== ({rhs})) begin\n"
        f'        $display("TDES_FAIL: test_id={test_id} | input={input_desc} | '
        f'expected=%0d | got=%0d", {args});\n'
        "        _fails = _fails + 1;\n"
        "      end\n"
        "    end\n"
        f'    if (_fails == 0) $display("TDES_PASS: test_id={test_id}");'
    )


def decompose(testbench: str, module_name: str, description: str) -> List[VerilogTest]:
    """Return a hierarchical VerilogTest list, or [] to fall back to native."""
    if _CLOCK_RE.search(testbench):
        return []  # clocked/sequential design — golden-expr decomposition unsafe
    inst = _find_instantiation(testbench, module_name)
    if not inst:
        return []
    inst_text, port_text = inst
    goldens = _extract_goldens(testbench)
    if not goldens:
        return []
    signals = _parse_signals(testbench)
    inputs = _input_signals(signals, port_text, goldens)
    if not inputs:
        return []

    # Reconstruct a preamble: the DUT's reg/wire decls + the instantiation.
    decl_lines = []
    for s in signals.values():
        rng = f" [{s.width - 1}:0]" if s.width > 1 else ""
        decl_lines.append(f"  {'reg' if s.is_reg else 'wire'}{rng} {s.name};")
    preamble = "\n".join(decl_lines) + "\n  " + inst_text.strip()

    out, _ = goldens[0]
    tests: List[VerilogTest] = [
        VerilogTest(
            id=f"{module_name}_u_zeros",
            level=TestLevel.UNIT,
            module=module_name,
            description=f"{module_name}: all-zero inputs produce {out} == golden",
            testbench_source=_build_tb(
                f"{module_name}_u_zeros",
                preamble,
                _directed_body(f"{module_name}_u_zeros", inputs, goldens, "zero"),
            ),
        ),
        VerilogTest(
            id=f"{module_name}_u_max",
            level=TestLevel.UNIT,
            module=module_name,
            description=f"{module_name}: all-ones inputs produce {out} == golden",
            testbench_source=_build_tb(
                f"{module_name}_u_max",
                preamble,
                _directed_body(f"{module_name}_u_max", inputs, goldens, "max"),
            ),
        ),
        VerilogTest(
            id=f"{module_name}_i_ones",
            level=TestLevel.INTEGRATION,
            module=module_name,
            description=f"{module_name}: unit-valued inputs (boundary/carry behavior)",
            testbench_source=_build_tb(
                f"{module_name}_i_ones",
                preamble,
                _directed_body(f"{module_name}_i_ones", inputs, goldens, "one"),
            ),
        ),
        VerilogTest(
            id=f"{module_name}_s_random",
            level=TestLevel.SYSTEM,
            module=module_name,
            description=f"{module_name}: 100 randomized vectors verified against golden model",
            testbench_source=_build_tb(
                f"{module_name}_s_random",
                preamble,
                _random_body(f"{module_name}_s_random", inputs, goldens, 100),
            ),
        ),
    ]
    return tests
