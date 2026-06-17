"""Probe one-shot module solvability on ArchXBench FPGA designs.

This is a cheap go/no-go experiment before running full TDES. It estimates
whether each module is in the crossover "Goldilocks" regime by repeatedly
asking a frontier model to repair one module from the seed plus initial
counterexample feedback, then running the existing Verilog unit/system tests.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from openevolve.tdes.fpga.archxbench import loader as archx_loader
from openevolve.tdes.fpga.config import FPGAConfig
from openevolve.tdes.fpga.mutation import VerilogLLMMutator
from openevolve.tdes.types import Candidate, FeedbackTuple

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

logger = logging.getLogger(__name__)


class CountingEnsemble:
    """Minimal ensemble wrapper used by VerilogLLMMutator."""

    def __init__(self, inner):
        self.inner = inner
        self.calls = 0

    async def generate_with_context(self, system_message: str, messages: list[dict[str, str]], **kwargs) -> str:
        self.calls += 1
        return await self.inner.generate_with_context(system_message, messages, **kwargs)


class CodexCLIBackend:
    """Codex CLI backend with ChatGPT session auth."""

    def __init__(self, *, model: str, reasoning_effort: str, timeout: int, cwd: str):
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.timeout = timeout
        self.cwd = cwd
        self.codex_bin = shutil.which("codex")
        if not self.codex_bin:
            raise RuntimeError("codex CLI not found on PATH")

    async def generate_with_context(self, system_message: str, messages: list[dict[str, str]], **kwargs) -> str:
        prompt = "INSTRUCTIONS:\n" + system_message + "\n\n---\n\n"
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            prompt += f"<{role}>\n{content}\n</{role}>\n\n"

        fd, response_path = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        try:
            cmd = [
                self.codex_bin,
                "exec",
                "--ephemeral",
                "--ignore-rules",
                "--skip-git-repo-check",
                "-m",
                self.model,
                "-c",
                f"model_reasoning_effort={self.reasoning_effort}",
                "-o",
                response_path,
                "-",
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self.cwd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(
                proc.communicate(input=prompt.encode("utf-8")),
                timeout=self.timeout,
            )
            if proc.returncode != 0:
                err = stderr.decode("utf-8", errors="replace")[:1000]
                raise RuntimeError(f"codex exec failed rc={proc.returncode}: {err}")
            text = Path(response_path).read_text(encoding="utf-8", errors="replace").strip()
            if not text:
                raise RuntimeError("codex exec returned empty output")
            return text
        finally:
            try:
                os.unlink(response_path)
            except OSError:
                pass


def build_anthropic_ensemble(config_path: str):
    from openevolve.llm.ensemble import LLMEnsemble

    cfg = FPGAConfig.from_yaml(config_path)
    if cfg.llm is None or not cfg.llm.llm.models:
        raise ValueError("LLM config missing models")
    return cfg, CountingEnsemble(LLMEnsemble(cfg.llm.llm.models))


def feedback_for_module(seed: Candidate, suite, module: str, *, timeout: int) -> list[FeedbackTuple]:
    seed_eval = seed.clone()
    seed_eval.vector = suite.run(seed_eval, timeout=timeout)
    feedback = []
    for result in seed_eval.vector.results.values():
        if result.module == module and not result.passed and result.feedback is not None:
            feedback.append(result.feedback)
    return feedback


def vector_row(vector) -> dict[str, Any]:
    row: dict[str, Any] = {
        "total_passes": vector.total_passes,
        "passed_tests": ";".join(sorted(vector.passes())),
    }
    for test_id, result in vector.results.items():
        row[f"pass_{test_id}"] = int(result.passed)
    return row


async def run_probe(args) -> list[dict[str, Any]]:
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "module_probe_samples.csv"
    jsonl_path = out_dir / "module_probe_samples.jsonl"

    completed = set()
    rows: list[dict[str, Any]] = []
    if csv_path.exists() and args.resume:
        with csv_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                key = (row["backend"], row["design"], row["module"], int(row["sample"]))
                completed.add(key)
                rows.append(dict(row))

    if args.backend == "codex":
        cfg = FPGAConfig()
        cfg.diff_based = args.diff_based
        cfg.suite_timeout = args.suite_timeout
        ensemble = CountingEnsemble(
            CodexCLIBackend(
                model=args.codex_model,
                reasoning_effort=args.reasoning_effort,
                timeout=args.llm_timeout,
                cwd=str(Path.cwd()),
            )
        )
        backend_name = f"codex:{args.codex_model}:{args.reasoning_effort}"
    else:
        cfg, ensemble = build_anthropic_ensemble(args.config)
        cfg.diff_based = args.diff_based
        cfg.suite_timeout = args.suite_timeout
        backend_name = f"config:{Path(args.config).name}"

    mutator = VerilogLLMMutator(ensemble, diff_based=cfg.diff_based)

    fieldnames = [
        "backend",
        "design",
        "module",
        "sample",
        "proposal_ok",
        "approach",
        "error",
        "total_passes",
        "passed_tests",
    ]
    test_fields: list[str] = []

    for design in args.designs:
        seed, suite, _ = archx_loader.load(design, with_mutator=False)
        modules = args.modules or list(seed.modules)
        seed_vector = suite.run(seed.clone(), timeout=args.suite_timeout)
        logger.info(
            "%s seed: %d/%d passes (%s)",
            design,
            seed_vector.total_passes,
            len(suite.tests),
            ",".join(sorted(seed_vector.passes())) or "none",
        )
        for module in modules:
            if module not in seed.modules:
                logger.warning("skip unknown module %s/%s", design, module)
                continue
            initial_feedback = feedback_for_module(seed, suite, module, timeout=args.suite_timeout)
            for sample in range(args.samples):
                key = (backend_name, design, module, sample)
                if key in completed:
                    logger.info("skip completed %s/%s sample=%d", design, module, sample)
                    continue

                row: dict[str, Any] = {
                    "backend": backend_name,
                    "design": design,
                    "module": module,
                    "sample": sample,
                    "proposal_ok": 0,
                    "approach": "",
                    "error": "",
                    "total_passes": 0,
                    "passed_tests": "",
                }
                try:
                    proposal = await mutator.propose(
                        candidate=seed,
                        module=module,
                        feedback=initial_feedback,
                        memory_text="",
                        generation=sample + 1,
                    )
                    if proposal is None:
                        row["error"] = "no_proposal"
                    else:
                        candidate = seed.clone(
                            modules={**seed.modules, module: proposal.new_source},
                            metadata={"origin": "module_probe", "design": design, "module": module},
                        )
                        candidate.vector = suite.run(candidate, timeout=args.suite_timeout)
                        row["proposal_ok"] = 1
                        row["approach"] = proposal.approach
                        row.update(vector_row(candidate.vector))
                        if args.save_sources:
                            src_dir = out_dir / "sources" / design / module
                            src_dir.mkdir(parents=True, exist_ok=True)
                            (src_dir / f"sample_{sample}.v").write_text(
                                proposal.new_source,
                                encoding="utf-8",
                            )
                except Exception as exc:
                    row["error"] = repr(exc)
                    logger.warning("%s/%s sample=%d failed: %s", design, module, sample, exc)

                for name in row:
                    if name.startswith("pass_") and name not in test_fields:
                        test_fields.append(name)
                rows.append(row)
                with jsonl_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(row, sort_keys=True) + "\n")
                all_fields = fieldnames + sorted(test_fields)
                with csv_path.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=all_fields, extrasaction="ignore")
                    writer.writeheader()
                    writer.writerows(rows)
                logger.info(
                    "%s/%s sample=%d -> proposal=%s passes=%s tests=%s",
                    design,
                    module,
                    sample,
                    row["proposal_ok"],
                    row["total_passes"],
                    row["passed_tests"] or "none",
                )

    return rows


def write_summary(rows: list[dict[str, Any]], out_dir: Path) -> None:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((row["backend"], row["design"], row["module"]), []).append(row)

    summary_rows = []
    for (backend, design, module), group in sorted(groups.items()):
        n = len(group)
        proposal_ok = sum(int(row.get("proposal_ok") or 0) for row in group)
        unit_special = sum(int(row.get("pass_unit_special") or 0) for row in group)
        unit_core = sum(int(row.get("pass_unit_core") or 0) for row in group)
        system_full = sum(int(row.get("pass_system_full") or 0) for row in group)
        any_unit = sum(
            1
            for row in group
            if int(row.get("pass_unit_special") or 0) or int(row.get("pass_unit_core") or 0)
        )
        summary_rows.append(
            {
                "backend": backend,
                "design": design,
                "module": module,
                "samples": n,
                "proposal_rate": proposal_ok / n if n else 0.0,
                "any_unit_rate": any_unit / n if n else 0.0,
                "unit_special_rate": unit_special / n if n else 0.0,
                "unit_core_rate": unit_core / n if n else 0.0,
                "system_rate": system_full / n if n else 0.0,
            }
        )

    summary_path = out_dir / "module_probe_summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary_rows[0]))
        writer.writeheader()
        writer.writerows(summary_rows)

    md = ["# ArchXBench Module Solvability Probe", ""]
    md.append("| Backend | Design | Module | Samples | Proposal | Any UNIT | unit_special | unit_core | system |")
    md.append("|---|---|---|---:|---:|---:|---:|---:|---:|")
    for row in summary_rows:
        md.append(
            "| {backend} | {design} | {module} | {samples} | {proposal_rate:.2f} | "
            "{any_unit_rate:.2f} | {unit_special_rate:.2f} | {unit_core_rate:.2f} | "
            "{system_rate:.2f} |".format(**row)
        )
    md.append("")
    md.append("Goldilocks read: useful TDES crossover needs at least two independent modules with roughly 0.30-0.60 UNIT pass probability.")
    (out_dir / "module_probe_summary.md").write_text("\n".join(md), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["codex", "config"], default="codex")
    parser.add_argument("--config", default="openevolve/tdes/fpga/experiments/configs/anthropic_sonnet.yaml")
    parser.add_argument("--codex-model", default="gpt-5.5")
    parser.add_argument("--reasoning-effort", default="low")
    parser.add_argument("--designs", nargs="+", default=list(archx_loader.DESIGNS))
    parser.add_argument("--modules", nargs="*", default=None)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--suite-timeout", type=int, default=90)
    parser.add_argument("--llm-timeout", type=int, default=420)
    parser.add_argument("--diff-based", action="store_true")
    parser.add_argument("--out", default="results/archxbench_module_probe")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--save-sources", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    rows = asyncio.run(run_probe(args))
    if rows:
        write_summary(rows, Path(args.out))
        print(Path(args.out) / "module_probe_summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
