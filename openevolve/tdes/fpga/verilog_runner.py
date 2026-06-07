"""
EDA simulation engine for TDES-FPGA.

Replaces the Python import/exec path of ``openevolve.tdes.test_suite`` with an
open-source EDA pipeline: write candidate ``.v`` files + a testbench to a temp
dir, compile with **Icarus Verilog** (``iverilog``), simulate with ``vvp``, and
interpret the output into a per-test (passed, failing_input, error) outcome that
maps onto the existing :class:`~openevolve.tdes.types.FeedbackTuple`.

The interpreter understands three testbench output conventions:

1. **TDES protocol** (emitted by our decomposer) — the most informative::

       TDES_PASS: test_id=<id>
       TDES_FAIL: test_id=<id> | input=<...> | expected=<...> | got=<...>

2. **RTLLM native** — a single global verdict::

       ===========Your Design Passed===========
       ===========Test completed with  N /M failures===========

3. **ArchXBench native** — per-case lines plus a summary::

       [FAIL] Input: <h>, Expected: <h>, Got: <h>
       TEST SUMMARY: <p> PASS, <f> FAILED

Compilation errors, elaboration errors, simulation timeouts, and crashes
(missing PASS markers) all degrade to a failed outcome with a meaningful
``error`` string so the LLM mutator gets directed CEGIS feedback.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_MAX_ERR = 600


def _trunc(text: str, n: int = _MAX_ERR) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 3] + "..."


def find_tool(names: List[str]) -> Optional[str]:
    """Return the path to the first available tool in ``names`` (or None).

    On Windows the explicit ``.exe`` is preferred: package managers like the
    OSS CAD Suite ship extensionless shell wrappers alongside the real ``.exe``,
    and ``subprocess`` cannot exec the wrappers directly.
    """
    for name in names:
        if os.name == "nt" and not name.lower().endswith(".exe"):
            path = shutil.which(name + ".exe")
            if path:
                return path
        path = shutil.which(name)
        if path:
            return path
    return None


def activate_toolchain(root: str) -> bool:
    """Prepend an OSS CAD Suite install's ``bin`` and ``lib`` to PATH.

    The Windows OSS CAD Suite keeps its DLLs in ``lib``; both ``bin`` and ``lib``
    must be on PATH or the binaries fail with a missing-DLL error. Returns True
    if the layout looked valid.
    """
    bin_dir = os.path.join(root, "bin")
    lib_dir = os.path.join(root, "lib")
    if not os.path.isdir(bin_dir):
        return False
    parts = [bin_dir]
    if os.path.isdir(lib_dir):
        parts.append(lib_dir)
    os.environ["PATH"] = os.pathsep.join(parts + [os.environ.get("PATH", "")])
    cacert = os.path.join(root, "etc", "cacert.pem")
    if os.path.exists(cacert):
        os.environ.setdefault("SSL_CERT_FILE", cacert)
    return True


# Auto-activate from OSS_CAD_SUITE_ROOT if set (opt-in; no effect otherwise).
_root = os.environ.get("OSS_CAD_SUITE_ROOT")
if _root:
    activate_toolchain(_root)


def tools_available() -> bool:
    """True if at least iverilog + vvp are on PATH (minimum for simulation)."""
    return bool(find_tool(["iverilog"]) and find_tool(["vvp"]))


# ---------------------------------------------------------------------------
# Low-level compile + simulate
# ---------------------------------------------------------------------------


@dataclass
class SimResult:
    compiled: bool
    stdout: str
    stderr: str
    returncode: int
    timed_out: bool
    compile_error: Optional[str] = None


def _kill_tree(proc: "subprocess.Popen") -> None:
    """Kill a process and all of its descendants.

    ``subprocess.run(timeout=...)`` only kills the immediate child; on Windows a
    surviving grandchild (e.g. an ``ivlpp``/codegen helper) can keep the stdout
    pipe open and block ``communicate()`` forever. Killing the whole tree avoids
    that hang.
    """
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                timeout=15,
            )
        else:
            import signal

            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _run(cmd: List[str], cwd: str, timeout: int):
    """Run a command with a hard timeout that kills the whole process tree.

    Returns ``(returncode, stdout, stderr, timed_out)``.
    """
    popen_kwargs = {}
    if os.name != "nt":
        popen_kwargs["start_new_session"] = True  # own process group for killpg
    proc = subprocess.Popen(
        cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **popen_kwargs
    )
    try:
        out, err = proc.communicate(timeout=timeout)
        return proc.returncode, out, err, False
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        try:
            out, err = proc.communicate(timeout=10)
        except Exception:
            out, err = "", ""
        return -1, out, err, True


def _write_sources(modules: Dict[str, str], testbench: str, dest: str) -> List[str]:
    src_files = []
    for name, source in modules.items():
        path = os.path.join(dest, f"{name}.v")
        with open(path, "w", encoding="utf-8") as f:
            f.write(source)
        src_files.append(path)
    tb_path = os.path.join(dest, "tb.v")
    with open(tb_path, "w", encoding="utf-8") as f:
        f.write(testbench)
    src_files.append(tb_path)
    return src_files


def simulate(
    modules: Dict[str, str],
    testbench: str,
    *,
    timeout: int = 60,
    verilog_std: str = "2012",
    iverilog_path: Optional[str] = None,
    vvp_path: Optional[str] = None,
) -> SimResult:
    """Compile + simulate a candidate against one testbench."""
    iverilog = iverilog_path or find_tool(["iverilog"])
    vvp = vvp_path or find_tool(["vvp"])
    if not iverilog or not vvp:
        raise RuntimeError(
            "Icarus Verilog (iverilog/vvp) not found on PATH. Install the OSS CAD "
            "Suite or set iverilog_path/vvp_path."
        )

    with tempfile.TemporaryDirectory(prefix="tdes_fpga_") as tmp:
        src_files = _write_sources(modules, testbench, tmp)
        sim_out = os.path.join(tmp, "sim.vvp")
        compile_cmd = [iverilog, f"-g{verilog_std}", "-o", sim_out] + src_files
        rc, c_out, c_err, c_timeout = _run(compile_cmd, tmp, timeout)
        if c_timeout:
            return SimResult(False, "", "", -1, True, f"compilation exceeded {timeout}s")
        if rc != 0 or not os.path.exists(sim_out):
            return SimResult(False, c_out, c_err, rc, False, _trunc(c_err))

        r_rc, r_out, r_err, r_timeout = _run([vvp, sim_out], tmp, timeout)
        if r_timeout:
            return SimResult(True, "", "", -1, True, None)
        return SimResult(True, r_out, r_err, r_rc, False, None)


# ---------------------------------------------------------------------------
# Output interpretation -> per-test outcome
# ---------------------------------------------------------------------------


@dataclass
class TestOutcome:
    passed: bool
    failing_input: str
    error: str


_TDES_PASS_RE = re.compile(r"TDES_PASS:\s*test_id=(\S+)")
_TDES_FAIL_RE = re.compile(
    r"TDES_FAIL:\s*test_id=(\S+?)\s*\|\s*input=(.*?)\s*\|\s*expected=(.*?)\s*\|\s*got=(.*?)\s*$",
    re.MULTILINE,
)
_RTLLM_PASS_RE = re.compile(r"Your Design Passed", re.IGNORECASE)
_RTLLM_FAIL_RE = re.compile(
    r"Test completed with\s*([0-9]+)\s*/\s*([0-9]+)\s*failures", re.IGNORECASE
)
_RTLLM_ERROR_RE = re.compile(r"={3,}\s*Error\s*={3,}", re.IGNORECASE)
_ARCHX_FAILLINE_RE = re.compile(
    r"\[FAIL\][^\n]*?Input:\s*(.*?)(?:,|\s)\s*Expected:\s*(.*?)(?:,|\s)\s*Got:\s*([^\n]+)",
    re.IGNORECASE,
)
_ARCHX_SUMMARY_RE = re.compile(
    r"TEST SUMMARY:\s*([0-9]+)\s*PASS\w*,\s*([0-9]+)\s*FAIL", re.IGNORECASE
)
_GENERIC_PASS_RE = re.compile(r"\ball tests passed\b", re.IGNORECASE)


def interpret(test_id: str, sim: SimResult, *, timeout: int) -> TestOutcome:
    """Turn a SimResult into a pass/fail + CEGIS feedback for one test."""
    if not sim.compiled:
        return TestOutcome(False, "compile-time", f"compilation failed: {sim.compile_error}")
    if sim.timed_out:
        return TestOutcome(False, "n/a", f"simulation exceeded {timeout}s budget")

    out = sim.stdout or ""

    # 1) Explicit TDES protocol (per-test) ---------------------------------
    for m in _TDES_FAIL_RE.finditer(out):
        if m.group(1) == test_id:
            return TestOutcome(
                False,
                _trunc(m.group(2)),
                f"expected {_trunc(m.group(3), 200)}, got {_trunc(m.group(4), 200)}",
            )
    if any(m.group(1) == test_id for m in _TDES_PASS_RE.finditer(out)):
        return TestOutcome(True, "n/a", "")
    # Generic (test-id-agnostic) TDES markers when only one test per bench.
    if "TDES_FAIL:" in out:
        m = _TDES_FAIL_RE.search(out)
        if m:
            return TestOutcome(
                False,
                _trunc(m.group(2)),
                f"expected {_trunc(m.group(3), 200)}, got {_trunc(m.group(4), 200)}",
            )
    if "TDES_PASS:" in out:
        return TestOutcome(True, "n/a", "")

    # 2) ArchXBench native --------------------------------------------------
    summ = _ARCHX_SUMMARY_RE.search(out)
    if summ:
        failed = int(summ.group(2))
        if failed == 0:
            return TestOutcome(True, "n/a", "")
        fail = _ARCHX_FAILLINE_RE.search(out)
        if fail:
            return TestOutcome(
                False,
                _trunc(fail.group(1)),
                f"expected {_trunc(fail.group(2), 200)}, got {_trunc(fail.group(3), 200)}",
            )
        return TestOutcome(False, "n/a", f"{failed} case(s) failed")

    # 3) RTLLM native -------------------------------------------------------
    fail = _RTLLM_FAIL_RE.search(out)
    if fail:
        return TestOutcome(
            False, "random stimulus", f"{fail.group(1)}/{fail.group(2)} cases failed"
        )
    if _RTLLM_ERROR_RE.search(out):
        return TestOutcome(False, "n/a", _trunc(out[-300:]) or "design reported Error")
    if _RTLLM_PASS_RE.search(out) or _GENERIC_PASS_RE.search(out):
        return TestOutcome(True, "n/a", "")

    # 4) Ambiguous: simulation ran but emitted no recognizable verdict ------
    tail = _trunc((out or sim.stderr or "")[-300:])
    return TestOutcome(False, "n/a", f"no pass marker found; output tail: {tail}")


def run_single_test(
    test_id: str,
    modules: Dict[str, str],
    testbench: str,
    *,
    timeout: int = 60,
    verilog_std: str = "2012",
) -> TestOutcome:
    """Convenience: simulate one testbench and interpret it for ``test_id``."""
    sim = simulate(modules, testbench, timeout=timeout, verilog_std=verilog_std)
    return interpret(test_id, sim, timeout=timeout)
