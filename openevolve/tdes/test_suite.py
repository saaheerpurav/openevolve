"""
Hierarchical test suite and runner for TDES.

A TDES "problem" is specified as a :class:`TDESTestSuite`: a list of tests,
each tagged with a level (unit/integration/system), the module(s) it
exercises, and a natural-language description. Running a candidate codebase
against the suite produces a :class:`TestVector` and, for every failing test,
a :class:`FeedbackTuple` (description + concrete failing input + error) for
CEGIS-style mutation (section 3.2).

Tests are authored as plain Python functions that receive a :class:`TestEnv`
exposing the candidate's modules plus assertion helpers. On a mismatch the
helpers raise :class:`TDESAssertionError` carrying the concrete failing input,
so the runner can surface it without ever exposing the test source.

Candidate code is executed in an isolated subprocess with a timeout by default
(``sandbox=True``) so that crashing or hanging candidates cannot take down the
controller, mirroring the temp-file/timeout pattern in ``evaluator.py``.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import os
import subprocess
import sys
import tempfile
import traceback
from dataclasses import dataclass
from types import ModuleType
from typing import Callable, Dict, List, Optional, Sequence

from openevolve.tdes.types import (
    Candidate,
    FeedbackTuple,
    TestLevel,
    TestResult,
    TestVector,
)

logger = logging.getLogger(__name__)

# Maximum length of a repr'd failing input / error before truncation.
_MAX_REPR = 600


class TDESAssertionError(AssertionError):
    """Raised by TestEnv assertion helpers to carry a concrete counterexample."""

    def __init__(self, failing_input, expected, got, message: Optional[str] = None):
        self.failing_input = failing_input
        self.expected = expected
        self.got = got
        self.message = message
        super().__init__(message or f"expected {expected!r}, got {got!r}")


def _trunc(text: str) -> str:
    text = str(text)
    return text if len(text) <= _MAX_REPR else text[: _MAX_REPR - 3] + "..."


class TestEnv:
    """Execution environment handed to each test function.

    Candidate modules are reachable as attributes (e.g. ``env.stats``) or via
    :meth:`module`. ``env.case(x)`` records the concrete input currently under
    test so it can be reported even if the candidate *crashes* before an
    assertion runs. The ``check_*`` helpers raise :class:`TDESAssertionError`
    with that input attached.
    """

    def __init__(self, modules: Dict[str, ModuleType]):
        # Use __dict__ directly so __getattr__ only fires for module lookups.
        self.__dict__["_modules"] = modules
        self.__dict__["current_input"] = None

    def module(self, name: str) -> ModuleType:
        return self._modules[name]

    def __getattr__(self, name: str) -> ModuleType:
        modules = self.__dict__.get("_modules", {})
        if name in modules:
            return modules[name]
        raise AttributeError(name)

    def case(self, value):
        """Record (and return) the concrete input currently being tested."""
        self.__dict__["current_input"] = value
        return value

    def check(self, condition, message: Optional[str] = None):
        if not condition:
            raise TDESAssertionError(self.current_input, True, condition, message)

    def check_equal(self, got, expected, message: Optional[str] = None):
        if got != expected:
            raise TDESAssertionError(self.current_input, expected, got, message)

    def check_close(self, got, expected, tol: float = 1e-6, message: Optional[str] = None):
        try:
            ok = abs(got - expected) <= tol
        except TypeError:
            ok = got == expected
        if not ok:
            raise TDESAssertionError(
                self.current_input, expected, got, message or f"|{got} - {expected}| > {tol}"
            )


@dataclass
class TDESTest:
    """A single hierarchical test."""

    id: str
    level: TestLevel
    module: str  # primary module used to map tests -> modules (section 3.3)
    description: str
    fn: Callable[[TestEnv], None]
    modules: Optional[List[str]] = None  # all modules touched; defaults to [module]

    def touched_modules(self) -> List[str]:
        return list(self.modules) if self.modules else [self.module]


class TDESTestSuite:
    """A hierarchical test suite over a fixed set of codebase modules."""

    def __init__(self, modules: Sequence[str]):
        self.module_names: List[str] = list(modules)
        self.tests: List[TDESTest] = []
        self.source_path: Optional[str] = None  # set when loaded from a file

    # -- registration ----------------------------------------------------
    def add(self, test: TDESTest) -> TDESTest:
        if any(t.id == test.id for t in self.tests):
            raise ValueError(f"duplicate test id: {test.id}")
        self.tests.append(test)
        return test

    def _register(self, level: TestLevel, module: str, id: Optional[str], description, modules):
        def deco(fn: Callable[[TestEnv], None]) -> Callable[[TestEnv], None]:
            self.add(
                TDESTest(
                    id=id or fn.__name__,
                    level=level,
                    module=module,
                    description=description or (fn.__doc__ or fn.__name__).strip(),
                    fn=fn,
                    modules=modules,
                )
            )
            return fn

        return deco

    def unit(self, module: str, *, id=None, description=None, modules=None):
        return self._register(TestLevel.UNIT, module, id, description, modules)

    def integration(self, module: str, *, id=None, description=None, modules=None):
        return self._register(TestLevel.INTEGRATION, module, id, description, modules)

    def system(self, module: str, *, id=None, description=None, modules=None):
        return self._register(TestLevel.SYSTEM, module, id, description, modules)

    # -- introspection (safe; no candidate code executed) ----------------
    def modules_for_tests(self, test_ids) -> List[str]:
        """Modules responsible for the given tests (section 3.3, step 2)."""
        wanted = set(test_ids)
        out: List[str] = []
        for t in self.tests:
            if t.id in wanted:
                for m in t.touched_modules():
                    if m not in out:
                        out.append(m)
        return out

    def tests_for_module(self, module: str) -> List[TDESTest]:
        return [t for t in self.tests if module in t.touched_modules()]

    # -- execution -------------------------------------------------------
    def run(self, candidate: Candidate, *, sandbox: bool = True, timeout: int = 60) -> TestVector:
        """Run the suite against a candidate, returning its TestVector.

        With ``sandbox=True`` candidate code runs in a subprocess with a
        timeout; with ``sandbox=False`` it runs in-process (faster, for trusted
        code / framework tests).
        """
        if sandbox:
            raw = _run_sandboxed(self, candidate.modules, timeout)
        else:
            raw = _run_in_process(self, candidate.modules)
        return self._vector_from_raw(raw)

    def _vector_from_raw(self, raw: List[dict]) -> TestVector:
        vector = TestVector()
        by_id = {t.id: t for t in self.tests}
        for item in raw:
            t = by_id[item["id"]]
            feedback = None
            if not item["passed"]:
                feedback = FeedbackTuple(
                    description=t.description,
                    failing_input=_trunc(item.get("failing_input", "n/a")),
                    error=_trunc(item.get("error", "unknown error")),
                )
            vector.results[t.id] = TestResult(
                test_id=t.id,
                level=t.level,
                module=t.module,
                passed=item["passed"],
                description=t.description,
                feedback=feedback,
            )
        return vector

    @classmethod
    def load_from_file(cls, path: str) -> "TDESTestSuite":
        """Load a suite from a Python file exposing ``suite`` or ``get_suite()``."""
        path = os.path.abspath(path)
        spec = importlib.util.spec_from_file_location("_tdes_suite_module", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # runs only suite-definition code; safe
        if hasattr(module, "get_suite"):
            suite = module.get_suite()
        elif hasattr(module, "suite"):
            suite = module.suite
        else:
            raise ValueError(
                f"{path} must define a module-level `suite` or a `get_suite()` function"
            )
        if not isinstance(suite, TDESTestSuite):
            raise TypeError("`suite`/`get_suite()` must be a TDESTestSuite")
        suite.source_path = path
        return suite


# ---------------------------------------------------------------------------
# Codebase import + test execution (shared by in-process and subprocess paths)
# ---------------------------------------------------------------------------


def _import_codebase(modules_dir: str, module_names: Sequence[str]) -> Dict[str, ModuleType]:
    """Import each codebase module by name from `modules_dir`.

    The directory is placed on ``sys.path`` so modules can import one another
    by their top-level name (e.g. ``pipeline`` doing ``import stats``). Any
    stale cached copies are evicted so each candidate is re-imported fresh.
    """
    if modules_dir not in sys.path:
        sys.path.insert(0, modules_dir)
    for name in module_names:
        sys.modules.pop(name, None)
    importlib.invalidate_caches()
    imported: Dict[str, ModuleType] = {}
    for name in module_names:
        imported[name] = importlib.import_module(name)
    return imported


def _execute_tests(suite: "TDESTestSuite", modules: Dict[str, ModuleType]) -> List[dict]:
    """Run every test against already-imported modules; never raises."""
    results: List[dict] = []
    for test in suite.tests:
        env = TestEnv(modules)
        item = {"id": test.id, "passed": True, "failing_input": "n/a", "error": ""}
        try:
            test.fn(env)
        except TDESAssertionError as e:
            item["passed"] = False
            item["failing_input"] = repr(e.failing_input)
            item["error"] = str(e)
        except Exception as e:  # candidate crashed / raised unexpectedly
            item["passed"] = False
            item["failing_input"] = repr(env.current_input)
            tb = traceback.format_exception_only(type(e), e)[-1].strip()
            item["error"] = tb
        results.append(item)
    return results


def _write_codebase(modules: Dict[str, str], dest_dir: str) -> None:
    for name, source in modules.items():
        with open(os.path.join(dest_dir, f"{name}.py"), "w", encoding="utf-8") as f:
            f.write(source)


def _run_in_process(suite: "TDESTestSuite", modules: Dict[str, str]) -> List[dict]:
    saved_path = list(sys.path)
    with tempfile.TemporaryDirectory(prefix="tdes_cb_") as tmp:
        _write_codebase(modules, tmp)
        try:
            imported = _import_codebase(tmp, suite.module_names)
            return _execute_tests(suite, imported)
        finally:
            for name in suite.module_names:
                sys.modules.pop(name, None)
            sys.path[:] = saved_path


def _run_sandboxed(suite: "TDESTestSuite", modules: Dict[str, str], timeout: int) -> List[dict]:
    if not suite.source_path:
        raise ValueError(
            "sandboxed run requires the suite to be loaded via "
            "TDESTestSuite.load_from_file(...) (need a source path for the subprocess)"
        )
    with tempfile.TemporaryDirectory(prefix="tdes_cb_") as tmp:
        _write_codebase(modules, tmp)
        out_path = os.path.join(tmp, "_results.json")
        cmd = [
            sys.executable,
            "-m",
            "openevolve.tdes._runner",
            suite.source_path,
            tmp,
            out_path,
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmp,
            )
        except subprocess.TimeoutExpired:
            logger.warning("TDES suite run timed out after %ss; marking all tests failed", timeout)
            return _all_failed(suite, "timeout", f"suite exceeded {timeout}s budget")
        if not os.path.exists(out_path):
            logger.warning(
                "TDES runner produced no results (rc=%s). stderr:\n%s",
                proc.returncode,
                proc.stderr,
            )
            return _all_failed(suite, "n/a", f"runner failed: {proc.stderr.strip()[-300:]}")
        with open(out_path, "r", encoding="utf-8") as f:
            return json.load(f)


def _all_failed(suite: "TDESTestSuite", failing_input: str, error: str) -> List[dict]:
    return [
        {"id": t.id, "passed": False, "failing_input": failing_input, "error": error}
        for t in suite.tests
    ]
