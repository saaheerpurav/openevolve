"""
Hierarchical test suite for evolved masking strategies.

Three gated tiers over the single evolved module ``"masking"``:

  UNIT        8 instant checks on the mask function itself (shape, dtype,
              ratio, non-degeneracy, stochasticity, epoch handling, NaN).
              All must pass before any training compute is spent.
  INTEGRATION a short pretraining run (``integration_epochs``); passes iff the
              final reconstruction loss is below ``integration_loss_max`` —
              catches valid-looking masks that make training diverge.
  SYSTEM      full pretraining + frozen-encoder linear probe. The scalar probe
              accuracy is expressed as a *ladder* of SYSTEM tests
              (``acc >= rung`` for each configured rung), so hierarchical
              selection sees "higher accuracy" as "more system passes" and the
              no-regression mutation check ratchets accuracy upward.

``MAESuite`` is duck-type compatible with the base TDES controller
(``run`` / ``tests`` / ``modules_for_tests`` / ``module_names``), like the
fpga and combopt suites. Candidate code executes in a persistent worker
subprocess (timeout => kill + respawn), and evaluations are memoized by source
hash so elitist clones never retrain.

CEGIS feedback carries the *actual scalars* (measured ratio, final loss, probe
accuracy), which is the gradient signal the LLM mutator steers by.
"""

from __future__ import annotations

import hashlib
import logging
import multiprocessing
from concurrent.futures import BrokenExecutor, ProcessPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set

from openevolve.tdes.mae.config import MAEConfig
from openevolve.tdes.types import Candidate, FeedbackTuple, TestLevel, TestResult, TestVector

logger = logging.getLogger(__name__)

MODULE = "masking"
_CALL = "generate_mask(batch_size=32, num_patches=16, mask_ratio=0.75, epoch=0, device='cpu')"


# ---------------------------------------------------------------------------
# Worker-side evaluation (top-level functions: picklable for the subprocess)
# ---------------------------------------------------------------------------


def warmup_worker() -> bool:
    """Pay the torch import inside the worker before any timed evaluation."""
    import torch  # noqa: F401

    return True


def run_unit_tier(source: str, cfg: MAEConfig) -> Dict[str, Dict]:
    """Tier 1: compile + the 8 unit checks. Returns {test_name: {passed, detail}}."""
    import torch

    from openevolve.tdes.mae.masking import compile_mask_fn

    out: Dict[str, Dict] = {}
    try:
        fn = compile_mask_fn(source)
    except Exception as e:
        err = f"module failed to compile/define generate_mask: {type(e).__name__}: {e}"
        return {name: {"passed": False, "detail": err} for name, _ in _UNIT_CHECKS}

    torch.manual_seed(cfg.eval_seed)
    for name, check in _UNIT_CHECKS:
        try:
            ok, detail = check(fn, cfg)
        except Exception as e:
            ok, detail = False, f"raised {type(e).__name__}: {e}"
        out[name] = {"passed": bool(ok), "detail": detail}
    return out


def run_train_tier(source: str, cfg: MAEConfig) -> Dict[str, Dict]:
    """Tiers 2+3: short run for the loss gate, then full pretrain + probe."""
    from openevolve.tdes.mae.trainer import pretrain_and_probe

    result = {"integration": {"loss": None, "error": None}, "system": {"acc": None, "error": None}}
    try:
        integ = pretrain_and_probe(source, cfg.integration_epochs, cfg, seed=cfg.eval_seed)
        result["integration"]["loss"] = integ["recon_loss"]
    except Exception as e:
        result["integration"]["error"] = f"training raised {type(e).__name__}: {e}"
        result["system"]["error"] = "skipped: integration training failed"
        return result

    if integ["recon_loss"] >= cfg.integration_loss_max:
        result["system"]["error"] = (
            f"skipped: integration loss {integ['recon_loss']:.3f} "
            f">= {cfg.integration_loss_max} gate"
        )
        return result

    try:
        full = pretrain_and_probe(source, cfg.system_epochs, cfg, seed=cfg.eval_seed)
        result["system"]["acc"] = full["probe_acc"]
        result["system"]["recon_loss"] = full["recon_loss"]
    except Exception as e:
        result["system"]["error"] = f"training raised {type(e).__name__}: {e}"
    return result


def _check_shape(fn, cfg):
    m = fn(4, 16, 0.75, 0, "cpu")
    return tuple(m.shape) == (4, 16), f"shape was {tuple(m.shape)}, expected (4, 16)"


def _check_dtype(fn, cfg):
    import torch

    m = fn(4, 16, 0.75, 0, "cpu")
    return m.dtype == torch.bool, f"dtype was {m.dtype}, expected torch.bool"


def _check_ratio(fn, cfg):
    r = float(fn(32, 16, 0.75, 0, "cpu").float().mean())
    return abs(r - 0.75) < 0.10, f"mask ratio was {r:.3f}, expected 0.75 +/- 0.10"


def _check_not_all_masked(fn, cfg):
    return not bool(fn(32, 16, 0.75, 0, "cpu").all()), "every patch was masked (degenerate)"


def _check_not_all_unmasked(fn, cfg):
    return bool(fn(32, 16, 0.75, 0, "cpu").any()), "no patch was masked (degenerate)"


def _check_stochastic(fn, cfg):
    import torch

    a, b = fn(4, 16, 0.75, 0, "cpu"), fn(4, 16, 0.75, 0, "cpu")
    return not torch.equal(a, b), "two consecutive calls returned identical masks"


def _check_epoch_range(fn, cfg):
    a, b = fn(4, 16, 0.75, 0, "cpu"), fn(4, 16, 0.75, 29, "cpu")
    ok = a is not None and b is not None and tuple(b.shape) == (4, 16)
    return ok, "failed for epoch=0 or epoch=29"


def _check_no_nan(fn, cfg):
    import torch

    return (
        not bool(torch.isnan(fn(4, 16, 0.75, 0, "cpu").float()).any()),
        "NaN in mask after float conversion",
    )


_UNIT_CHECKS = [
    ("u_shape", _check_shape),
    ("u_dtype", _check_dtype),
    ("u_ratio", _check_ratio),
    ("u_not_all_masked", _check_not_all_masked),
    ("u_not_all_unmasked", _check_not_all_unmasked),
    ("u_stochastic", _check_stochastic),
    ("u_epoch_range", _check_epoch_range),
    ("u_no_nan", _check_no_nan),
]

_UNIT_DESCRIPTIONS = {
    "u_shape": "mask has shape (batch_size, num_patches)",
    "u_dtype": "mask dtype is torch.bool",
    "u_ratio": "fraction of masked patches is mask_ratio +/- 0.10",
    "u_not_all_masked": "mask is not degenerate: at least one patch visible",
    "u_not_all_unmasked": "mask is not degenerate: at least one patch masked",
    "u_stochastic": "consecutive calls produce different masks",
    "u_epoch_range": "works for both epoch=0 and epoch=29",
    "u_no_nan": "no NaN values in the mask",
}


# ---------------------------------------------------------------------------
# Persistent worker (controller side)
# ---------------------------------------------------------------------------


class EvalTimeout(Exception):
    pass


class _EvalWorker:
    """One reusable subprocess; killed and respawned on timeout/crash.

    Keeping the process alive across evaluations amortizes the torch import
    and dataset load (~several seconds) over the whole evolution run.
    """

    def __init__(self):
        self._pool: Optional[ProcessPoolExecutor] = None

    def call(self, fn, *args, timeout: float):
        if self._pool is None:
            self._pool = ProcessPoolExecutor(
                max_workers=1, mp_context=multiprocessing.get_context("spawn")
            )
            # Timed evaluations must not be billed for the worker's torch import.
            self._pool.submit(warmup_worker).result(timeout=180)
        future = self._pool.submit(fn, *args)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeoutError:
            self._kill()
            raise EvalTimeout(f"evaluation exceeded {timeout:.0f}s (killed worker)")
        except BrokenExecutor as e:
            self._kill()
            raise EvalTimeout(f"evaluation worker died: {e}")

    def _kill(self):
        if self._pool is None:
            return
        for proc in list(getattr(self._pool, "_processes", {}).values()):
            try:
                proc.kill()
            except Exception:
                pass
        self._pool.shutdown(wait=False, cancel_futures=True)
        self._pool = None

    def close(self):
        if self._pool is not None:
            self._pool.shutdown(wait=True, cancel_futures=True)
            self._pool = None


# ---------------------------------------------------------------------------
# The duck-typed suite
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MAETestSpec:
    id: str
    level: TestLevel
    module: str
    description: str


class MAESuite:
    """Drop-in hierarchical suite over the single evolved ``masking`` module."""

    def __init__(self, cfg: Optional[MAEConfig] = None):
        self.cfg = cfg or MAEConfig()
        self.module_names: List[str] = [MODULE]
        self.tests: List[MAETestSpec] = self._build_specs()
        self._worker = _EvalWorker()
        # source-hash -> raw tier results; also the run's score log.
        self.eval_records: Dict[str, Dict] = {}

    def _build_specs(self) -> List[MAETestSpec]:
        specs = [
            MAETestSpec(name, TestLevel.UNIT, MODULE, _UNIT_DESCRIPTIONS[name])
            for name, _ in _UNIT_CHECKS
        ]
        specs.append(
            MAETestSpec(
                "integ_trains",
                TestLevel.INTEGRATION,
                MODULE,
                f"{self.cfg.integration_epochs}-epoch MAE pretraining converges "
                f"(final reconstruction loss < {self.cfg.integration_loss_max})",
            )
        )
        for rung in self.cfg.system_acc_rungs:
            specs.append(
                MAETestSpec(
                    f"sys_acc_ge_{int(round(rung * 1000)):03d}",
                    TestLevel.SYSTEM,
                    MODULE,
                    f"linear probe accuracy after {self.cfg.system_epochs}-epoch "
                    f"pretraining reaches {rung:.1%}",
                )
            )
        return specs

    def modules_for_tests(self, test_ids: Iterable[str]) -> Set[str]:
        return {MODULE} if list(test_ids) else set()

    # -- evaluation --------------------------------------------------------
    def run(self, candidate: Candidate, sandbox: bool = True, timeout: Optional[int] = None):
        source = candidate.modules[MODULE]
        key = hashlib.sha256(source.encode()).hexdigest()
        if key not in self.eval_records:
            self.eval_records[key] = self._evaluate(source, sandbox, timeout)
        return self._to_vector(self.eval_records[key])

    def close(self):
        self._worker.close()

    def _evaluate(self, source: str, sandbox: bool, timeout: Optional[int]) -> Dict:
        cfg = self.cfg
        train_timeout = float(timeout) if timeout else cfg.full_timeout_s

        def call(fn, tier_timeout):
            if sandbox:
                return self._worker.call(fn, source, cfg, timeout=tier_timeout)
            return fn(source, cfg)

        record: Dict = {"unit": None, "train": None, "timeout": None}
        try:
            record["unit"] = call(run_unit_tier, cfg.unit_timeout_s)
        except EvalTimeout as e:
            record["timeout"] = str(e)
            return record
        if all(r["passed"] for r in record["unit"].values()):
            try:
                record["train"] = call(run_train_tier, train_timeout)
            except EvalTimeout as e:
                record["timeout"] = str(e)
        loss = (record.get("train") or {}).get("integration", {}).get("loss")
        acc = (record.get("train") or {}).get("system", {}).get("acc")
        logger.info(
            "eval masking[%s..]: unit %s, loss=%s, probe_acc=%s%s",
            hashlib.sha256(source.encode()).hexdigest()[:8],
            (
                f"{sum(r['passed'] for r in record['unit'].values())}/{len(_UNIT_CHECKS)}"
                if record["unit"]
                else "timeout"
            ),
            f"{loss:.3f}" if loss is not None else "-",
            f"{acc:.3f}" if acc is not None else "-",
            " [TIMEOUT]" if record["timeout"] else "",
        )
        return record

    # -- vector construction -------------------------------------------------
    def _to_vector(self, record: Dict) -> TestVector:
        vector = TestVector()
        unit = record["unit"] or {}
        train = record["train"] or {}
        timeout_msg = record["timeout"]

        for name, _ in _UNIT_CHECKS:
            res = unit.get(name)
            passed = bool(res and res["passed"])
            error = res["detail"] if res else (timeout_msg or "not evaluated")
            vector.results[name] = self._result(name, passed, error)

        integ = train.get("integration", {})
        loss = integ.get("loss")
        integ_passed = loss is not None and loss < self.cfg.integration_loss_max
        if loss is not None and not integ_passed:
            integ_err = (
                f"final reconstruction loss was {loss:.3f}, gate is "
                f"< {self.cfg.integration_loss_max} (training did not converge usefully)"
            )
        else:
            integ_err = integ.get("error") or timeout_msg or "skipped: unit tests not all passed"
        vector.results["integ_trains"] = self._result("integ_trains", integ_passed, integ_err)

        system = train.get("system", {})
        acc = system.get("acc")
        for spec in self.tests:
            if spec.level is not TestLevel.SYSTEM:
                continue
            rung = float(spec.id.split("_")[-1]) / 1000.0
            passed = acc is not None and acc >= rung
            if acc is not None and not passed:
                sys_loss = system.get("recon_loss")
                error = (
                    f"linear probe accuracy was {acc:.3f}, below the {rung:.2f} target "
                    f"(reconstruction loss {sys_loss:.3f})"
                    if sys_loss is not None
                    else f"linear probe accuracy was {acc:.3f}, below the {rung:.2f} target"
                )
            else:
                error = system.get("error") or timeout_msg or "skipped: earlier tier failed"
            vector.results[spec.id] = self._result(spec.id, passed, error)
        return vector

    def _result(self, test_id: str, passed: bool, error: str) -> TestResult:
        spec = next(s for s in self.tests if s.id == test_id)
        feedback = None
        if not passed:
            feedback = FeedbackTuple(description=spec.description, failing_input=_CALL, error=error)
        return TestResult(
            test_id=test_id,
            level=spec.level,
            module=MODULE,
            passed=passed,
            description=spec.description,
            feedback=feedback,
        )
