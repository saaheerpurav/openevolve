"""
Sympy SWE-bench Task 1: composed two-module repair benchmark.

Module "point"       = sympy/physics/vector/point.py
  Bug: vel() raises ValueError when velocity not explicitly set (BFS missing)
  SWE-bench instance: sympy__sympy-20049

Module "blockmatrix" = sympy/matrices/expressions/blockmatrix.py
  Bug: _entry() uses (i < numrows) != False, failing for symbolic indices
  SWE-bench instance: sympy__sympy-19007

Test hierarchy:
  UNIT (7)       — fail-to-pass tests, per module
  INTEGRATION (1)— all 7 unit tests must pass (requires BOTH modules fixed)
  SYSTEM (1)     — unit tests + regression coverage across both files

Complementary-coverage structure:
  A candidate that fixes only "point" passes 4 unit tests but fails 3.
  A candidate that fixes only "blockmatrix" passes 3 unit tests but fails 4.
  These have non-overlapping pass sets -> crossover fires.

Stub design:
  LLMs see ONLY the focal method (vel / _entry) plus a minimal class header,
  not the full 566-line or 697-line file. This reduces prompt tokens by ~90%
  and cuts CLI response time from ~200s to ~15s. run() patches the modified
  method back into the full file before invoking pytest.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from openevolve.tdes.test_suite import TDESTestSuite, TDESTest
from openevolve.tdes.types import (
    Candidate,
    FeedbackTuple,
    TestLevel,
    TestResult,
    TestVector,
)

_TASK_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.join(_TASK_DIR, "repo")

_VENV_PY_WIN = os.path.join(_TASK_DIR, "venv", "Scripts", "python.exe")
_VENV_PY_UNIX = os.path.join(_TASK_DIR, "venv", "bin", "python")
_VENV_PYTHON = _VENV_PY_WIN if os.path.exists(_VENV_PY_WIN) else _VENV_PY_UNIX

_MODULE_PATHS = {
    "point":       "sympy/physics/vector/point.py",
    "blockmatrix": "sympy/matrices/expressions/blockmatrix.py",
}

# Focal method for each module — LLMs see only this method + a stub header.
_METHOD_NAMES = {
    "point":       "vel",
    "blockmatrix": "_entry",
}

# Minimal class header prepended to the focal method in the stub.
_STUB_HEADERS = {
    "point": (
        "from __future__ import print_function, division\n"
        "from .vector import Vector, _check_vector\n"
        "from .frame import _check_frame\n"
        "\n"
        "__all__ = ['Point']\n"
        "\n"
        "\n"
        "class Point(object):\n"
        '    """A point in a dynamic system with position, velocity, and acceleration.\n'
        "\n"
        "    Relevant attributes:\n"
        "      _pos_dict (dict[Point, Vector]): maps neighbor point -> position vector\n"
        "          of self relative to that neighbor (i.e. self._pos_dict[other] ==\n"
        "          self.pos_from(other)).  Doubles as the BFS adjacency list.\n"
        "      _vel_dict (dict[Frame, Vector]): explicitly-set velocities\n"
        "\n"
        "    Relevant methods:\n"
        "      self.pos_from(other: Point) -> Vector   # position of self relative to other\n"
        "      self.set_vel(frame, vel)                # cache a computed velocity\n"
        "      vector.dt(frame) -> Vector              # time-derivative of a Vector in frame\n"
        "\n"
        "    CORRECT FIX for vel(): the buggy implementation raises ValueError whenever\n"
        "    velocity is not in _vel_dict, even when it can be derived from position\n"
        "    relations.  The fix is to auto-compute it via BFS over _pos_dict and then\n"
        "    accumulate the kinematic chain rule along the found path.\n"
        "\n"
        "    Pattern (replace the body of vel() with this logic):\n"
        "          _check_frame(frame)\n"
        "          if frame in self._vel_dict:\n"
        "              return self._vel_dict[frame]\n"
        "          from collections import deque\n"
        "          visited = {self: None}   # point -> BFS parent\n"
        "          queue = deque([self])\n"
        "          found = None\n"
        "          while queue:\n"
        "              pt = queue.popleft()\n"
        "              if frame in pt._vel_dict:\n"
        "                  found = pt\n"
        "                  break\n"
        "              for neighbor in pt._pos_dict:\n"
        "                  if neighbor not in visited:\n"
        "                      visited[neighbor] = pt\n"
        "                      queue.append(neighbor)\n"
        "          if found is None:\n"
        "              raise ValueError('Velocity of point ' + self.name + ' has not been'\n"
        "                               ' defined in ReferenceFrame ' + frame.name)\n"
        "          path = []\n"
        "          node = found\n"
        "          while node is not None:\n"
        "              path.append(node)\n"
        "              node = visited[node]\n"
        "          path.reverse()   # path[0] = self, path[-1] = found\n"
        "          vel = found._vel_dict[frame]\n"
        "          for k in range(len(path) - 1):\n"
        "              vel = vel + path[k].pos_from(path[k + 1]).dt(frame)\n"
        "          self.set_vel(frame, vel)\n"
        "          return vel\n"
        "\n"
        "    No new imports beyond collections.deque needed.\n"
        '    """\n'
        "\n"
    ),
    "blockmatrix": (
        "from sympy.matrices.expressions.matexpr import MatrixExpr, MatrixElement\n"
        "from sympy import ask, Q\n"
        "\n"
        "\n"
        "class BlockMatrix(MatrixExpr):\n"
        '    """A BlockMatrix made up of sub-matrix blocks.\n'
        "\n"
        "    Properties: blocks, blockshape, rowblocksizes, colblocksizes.\n"
        "\n"
        "    CRITICAL SymPy pitfall: `i < numrows` for symbolic i returns a SymPy\n"
        "    StrictLessThan Relational, NOT a Python bool.  The buggy check\n"
        "    `(i < numrows) != False` is ALWAYS True for any SymPy object, so the\n"
        "    loop always breaks on the first block regardless of i.\n"
        "\n"
        "    CORRECT FIX: call `.simplify()` on the comparison.  SymPy can resolve\n"
        "    many arithmetic inequalities (e.g. `n-1 < n` → True, `n < n` → False)\n"
        "    while leaving an unevaluated Relational for truly ambiguous cases\n"
        "    (e.g. `i < n` with an unconstrained symbol `i`).  When the simplified\n"
        "    result is neither True nor False, return `MatrixElement(self, i, j)`\n"
        "    (SymPy's standard unevaluated fallback for unresolvable symbolic indexing).\n"
        "    For the LAST block in each axis, break unconditionally — a valid index\n"
        "    must land in the last block if it wasn't caught earlier.\n"
        "\n"
        "    Use separate row_offset and col_offset accumulators, iterate over\n"
        "    rowblocksizes / colblocksizes with enumerate, apply the .simplify() check\n"
        "    described above, and finally return\n"
        "        self.blocks[row_block, col_block][i - row_offset, j - col_offset].\n"
        "\n"
        "    No new imports needed: MatrixElement and ask/Q are already in scope.\n"
        '    """\n'
        "\n"
    ),
}

# ── Pytest node IDs (relative to repo root) ──────────────────────────────────

_POINT_UNIT = [
    "sympy/physics/vector/tests/test_point.py::test_auto_point_vel",
    "sympy/physics/vector/tests/test_point.py::test_auto_point_vel_multiple_point_path",
    "sympy/physics/vector/tests/test_point.py::test_auto_vel_dont_overwrite",
    "sympy/physics/vector/tests/test_point.py::test_auto_point_vel_shortest_path",
]

_BLOCKMATRIX_UNIT = [
    "sympy/matrices/expressions/tests/test_indexing.py::test_block_index_symbolic",
    "sympy/matrices/expressions/tests/test_indexing.py::test_block_index_symbolic_nonzero",
    "sympy/matrices/expressions/tests/test_indexing.py::test_block_index_large",
]

_SYSTEM_IDS = (
    [
        "sympy/physics/vector/tests/test_point.py::test_point_v1pt_theorys",
        "sympy/physics/vector/tests/test_point.py::test_point_a1pt_theorys",
        "sympy/physics/vector/tests/test_point.py::test_point_v2pt_theorys",
        "sympy/physics/vector/tests/test_point.py::test_point_a2pt_theorys",
        "sympy/physics/vector/tests/test_point.py::test_point_funcs",
        "sympy/physics/vector/tests/test_point.py::test_point_pos",
        "sympy/physics/vector/tests/test_point.py::test_point_partial_velocity",
        "sympy/matrices/expressions/tests/test_indexing.py::test_symbolic_indexing",
        "sympy/matrices/expressions/tests/test_indexing.py::test_add_index",
        "sympy/matrices/expressions/tests/test_indexing.py::test_mul_index",
        "sympy/matrices/expressions/tests/test_indexing.py::test_block_index",
    ]
    + _POINT_UNIT
    + _BLOCKMATRIX_UNIT
)


# ── Stub helpers ──────────────────────────────────────────────────────────────

def _method_body(source: str, method_name: str) -> str:
    """Extract the full method definition (def ... : body) from Python source."""
    lines = source.split("\n")
    start = None
    method_indent = 0
    for i, line in enumerate(lines):
        if re.match(rf"\s+def {re.escape(method_name)}\s*\(", line):
            start = i
            method_indent = len(line) - len(line.lstrip())
            break
    if start is None:
        return ""
    end = len(lines)
    for i in range(start + 1, len(lines)):
        stripped = lines[i].strip()
        if stripped and len(lines[i]) - len(lines[i].lstrip()) <= method_indent:
            end = i
            break
    body_lines = lines[start:end]
    while body_lines and not body_lines[-1].strip():
        body_lines.pop()
    return "\n".join(body_lines)


def _patch_method(full_source: str, new_method: str, orig_method: str) -> str:
    """Replace orig_method in full_source with new_method (first occurrence).

    Both new_method and orig_method are matched/inserted stripped of trailing
    blanks so that stubs (extra trailing \n) and full files (method followed
    by next def) produce consistent anchors.
    """
    orig_stripped = orig_method.rstrip()
    new_stripped = new_method.rstrip()
    if not orig_stripped or orig_stripped not in full_source:
        return full_source
    return full_source.replace(orig_stripped, new_stripped, 1)


def _build_stub(full_source: str, mod_name: str) -> str:
    """Build the LLM-facing stub: stub_header + focal method."""
    method = _method_body(full_source, _METHOD_NAMES[mod_name])
    if not method:
        return full_source  # fallback: full file if method not found
    return _STUB_HEADERS[mod_name] + method + "\n"


# ── SWEBenchSuite ─────────────────────────────────────────────────────────────

class SWEBenchSuite(TDESTestSuite):
    """
    TDESTestSuite that evaluates candidates against a real source repo via pytest.

    Candidates store STUBS (focal method + minimal header) rather than full
    files. run() patches each stub's modified method back into the real repo
    file, runs pytest once with all required test IDs, then restores originals.

    The `sandbox` parameter is accepted for API compatibility but ignored;
    candidate code runs inside the repo's own venv via subprocess (equivalent
    sandboxing without needing the _runner.py machinery).
    """

    def __init__(
        self,
        modules: list[str],
        repo_root: str,
        venv_python: str,
        module_file_paths: dict[str, str],
        method_names: dict[str, str],
    ):
        super().__init__(modules)
        self.repo_root = Path(repo_root)
        self.venv_python = str(venv_python)
        self.module_file_paths = module_file_paths
        self.method_names = method_names        # mod_name -> method name
        self._orig_methods: dict[str, str] = {} # mod_name -> original method body
        self._test_pytest_ids: dict[str, list[str]] = {}

    def _add_pytest(self, test: TDESTest, pytest_ids: list[str]) -> None:
        self.add(test)
        self._test_pytest_ids[test.id] = list(pytest_ids)

    def _cache_orig_methods(self) -> None:
        """Cache original method bodies so patch can always diff from baseline."""
        for mod_name, rel in self.module_file_paths.items():
            path = self.repo_root / rel
            with open(path, "r", encoding="utf-8") as f:
                full = f.read()
            self._orig_methods[mod_name] = _method_body(full, self.method_names[mod_name])

    # -- execution override --------------------------------------------------

    def run(self, candidate: Candidate, *, sandbox: bool = True, timeout: int = 120) -> TestVector:
        if not self._orig_methods:
            self._cache_orig_methods()

        originals: dict[Path, str] = {}
        try:
            for mod_name, stub_src in candidate.modules.items():
                rel = self.module_file_paths.get(mod_name)
                if rel is None:
                    continue
                path = self.repo_root / rel
                with open(path, "r", encoding="utf-8") as f:
                    full_src = f.read()
                originals[path] = full_src

                # Extract new method from stub; patch into full file
                new_method = _method_body(stub_src, self.method_names[mod_name])
                orig_method = _method_body(full_src, self.method_names[mod_name])
                if new_method and new_method != orig_method:
                    full_src = _patch_method(full_src, new_method, orig_method)

                with open(path, "w", encoding="utf-8") as f:
                    f.write(full_src)

            unique_ids = self._unique_pytest_ids()
            pytest_results = self._run_pytest(unique_ids, timeout)
            return self._build_vector(pytest_results)

        finally:
            for path, content in originals.items():
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)

    # -- pytest helpers ------------------------------------------------------

    def _unique_pytest_ids(self) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for t in self.tests:
            for pid in self._test_pytest_ids.get(t.id, []):
                if pid not in seen:
                    seen.add(pid)
                    out.append(pid)
        return out

    def _run_pytest(self, test_ids: list[str], timeout: int) -> dict[str, tuple[bool, str]]:
        if not test_ids:
            return {}
        cmd = [
            self.venv_python, "-m", "pytest",
            "--tb=short", "-v", "--no-header",
            "-p", "no:cacheprovider", "-W", "ignore",
        ] + test_ids
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.repo_root),
            )
            output = proc.stdout + "\n" + proc.stderr
        except subprocess.TimeoutExpired:
            return {tid: (False, "timeout") for tid in test_ids}
        return _parse_pytest_output(output, test_ids)

    def _build_vector(self, pytest_results: dict[str, tuple[bool, str]]) -> TestVector:
        vector = TestVector()
        for test in self.tests:
            pids = self._test_pytest_ids.get(test.id, [])
            failures = [
                (pid, pytest_results.get(pid, (False, "not run")))
                for pid in pids
                if not pytest_results.get(pid, (False, ""))[0]
            ]
            passed = len(pids) > 0 and len(failures) == 0
            feedback = None
            if not passed:
                names = [pid.split("::")[-1] for pid, _ in failures[:3]]
                errs = [f"{pid.split('::')[-1]}: {err}" for pid, (_, err) in failures[:3]]
                feedback = FeedbackTuple(
                    description=test.description,
                    failing_input=", ".join(names),
                    error="; ".join(errs) or "test(s) did not run",
                )
            vector.results[test.id] = TestResult(
                test_id=test.id,
                level=test.level,
                module=test.module,
                passed=passed,
                description=test.description,
                feedback=feedback,
            )
        return vector


# ── Pytest output parser ──────────────────────────────────────────────────────

def _parse_pytest_output(output: str, test_ids: list[str]) -> dict[str, tuple[bool, str]]:
    """Parse `pytest -v --tb=short` output into {pytest_id: (passed, error_msg)}.

    First records pass/fail status from the per-test PASSED/FAILED lines, then
    enriches failure entries with the actual exception message from the short
    test summary section ("FAILED path::name - ExcType: msg").  This gives the
    LLM meaningful feedback rather than the bare word "FAILED".
    """
    results: dict[str, tuple[bool, str]] = {tid: (False, "not run") for tid in test_ids}

    name_to_ids: dict[str, list[str]] = {}
    for tid in test_ids:
        name = tid.split("::")[-1]
        name_to_ids.setdefault(name, []).append(tid)

    # ── Pass 1: status lines ("path::name PASSED/FAILED [xx%]") ──────────────
    line_re = re.compile(
        r"^([\w/.\\-]+::[\w]+)\s+(PASSED|FAILED|ERROR|SKIPPED)\s*(?:\[[\d ]+%\])?\s*$",
        re.MULTILINE,
    )
    for m in line_re.finditer(output):
        raw, status = m.group(1), m.group(2)
        raw_norm = raw.replace("\\", "/")
        passed = status == "PASSED"
        err = "" if passed else status

        matched = False
        for tid in test_ids:
            tid_norm = tid.replace("\\", "/")
            if raw_norm == tid_norm or raw_norm.endswith("/" + tid_norm):
                results[tid] = (passed, err)
                matched = True
                break
        if not matched:
            func_name = raw_norm.split("::")[-1]
            for tid in name_to_ids.get(func_name, []):
                results[tid] = (passed, err)

    # ── Pass 2: FAILURES section ("___ test_name ___" blocks) ───────────────
    # pytest --tb=short writes one block per failed test with `E   Exc: msg`
    # error lines. We extract the last E-line per block as the error message.
    failure_block_re = re.compile(
        r"_{3,}\s+([\w]+)\s+_{3,}\n(.*?)(?=(?:_{3,}|\Z))",
        re.DOTALL,
    )
    e_line_re = re.compile(r"^E\s+(.+)$", re.MULTILINE)
    for bm in failure_block_re.finditer(output):
        func_name = bm.group(1).strip()
        block = bm.group(2)
        e_lines = e_line_re.findall(block)
        if not e_lines:
            continue
        exc_msg = e_lines[-1].strip()[:200]
        for tid in name_to_ids.get(func_name, []):
            prev_passed, _ = results[tid]
            if not prev_passed:
                results[tid] = (False, exc_msg)

    return results


# ── Suite factory ─────────────────────────────────────────────────────────────

def get_suite() -> SWEBenchSuite:
    suite = SWEBenchSuite(
        modules=["point", "blockmatrix"],
        repo_root=_REPO_ROOT,
        venv_python=_VENV_PYTHON,
        module_file_paths=_MODULE_PATHS,
        method_names=_METHOD_NAMES,
    )

    # -- UNIT: point (4 tests, fail on buggy vel(), pass on BFS fix) ----------
    _point_descs = [
        "vel() auto-computes velocity via BFS from position relations",
        "vel() traverses multi-hop point chain to reach a point with known velocity",
        "vel() does not overwrite a velocity already explicitly set",
        "vel() uses shortest BFS path when multiple ancestors have known velocities",
    ]
    for pid, desc in zip(_POINT_UNIT, _point_descs):
        suite._add_pytest(
            TDESTest(
                id=pid.split("::")[-1],
                level=TestLevel.UNIT,
                module="point",
                description=desc,
                fn=lambda env: None,
            ),
            [pid],
        )

    # -- UNIT: blockmatrix (3 tests, fail on != False bug, pass on fix) -------
    _bm_descs = [
        "_entry() returns correct element for symbolic row/col index",
        "_entry() handles symbolic index with non-zero cumulative offset",
        "_entry() handles large BlockMatrix with fully symbolic indices",
    ]
    for pid, desc in zip(_BLOCKMATRIX_UNIT, _bm_descs):
        suite._add_pytest(
            TDESTest(
                id=pid.split("::")[-1],
                level=TestLevel.UNIT,
                module="blockmatrix",
                description=desc,
                fn=lambda env: None,
            ),
            [pid],
        )

    # -- INTEGRATION: all 7 unit tests (requires BOTH modules fixed) ----------
    suite._add_pytest(
        TDESTest(
            id="integ_both_modules_fixed",
            level=TestLevel.INTEGRATION,
            module="point",
            description="all fail-to-pass tests pass: both vel() BFS and _entry() symbolic indexing fixed",
            fn=lambda env: None,
            modules=["point", "blockmatrix"],
        ),
        _POINT_UNIT + _BLOCKMATRIX_UNIT,
    )

    # -- SYSTEM: unit tests + regression coverage from both files -------------
    suite._add_pytest(
        TDESTest(
            id="system_full_regression",
            level=TestLevel.SYSTEM,
            module="point",
            description="all 7 fix tests pass and no regressions in either test file",
            fn=lambda env: None,
            modules=["point", "blockmatrix"],
        ),
        _SYSTEM_IDS,
    )

    return suite


# ── Seed factory ──────────────────────────────────────────────────────────────

def get_seed() -> Candidate:
    """Return a Candidate loaded as method stubs from the current (buggy) repo files."""
    modules: dict[str, str] = {}
    for mod_name, rel_path in _MODULE_PATHS.items():
        abs_path = os.path.join(_REPO_ROOT, rel_path)
        with open(abs_path, "r", encoding="utf-8") as f:
            full_src = f.read()
        modules[mod_name] = _build_stub(full_src, mod_name)
    return Candidate(
        modules=modules,
        generation=0,
        metadata={"origin": "swe_bench_buggy", "instances": ["sympy__sympy-20049", "sympy__sympy-19007"]},
    )
