"""
CI/CD repair test suite — built dynamically from the lca-ci-builds-repair dataset.

Download the dataset first:
    pip install datasets
    python -c "
    from datasets import load_dataset
    ds = load_dataset('JetBrains-Research/lca-ci-builds-repair')
    ds['train'].to_json('openevolve/tdes/repair/tasks/cicd/lca_samples.jsonl')
    "

Then use get_suite(sample_idx) to build a suite for one sample.

Each sample becomes a single-module repair task:
  Module "workflow" contains the broken YAML workflow as a Python string.
  Tests:
    UNIT        — YAML parses without error
    INTEGRATION — required CI steps are present and in the right order
    SYSTEM      — structural match to the known-good fixed workflow
"""

from __future__ import annotations

import json
import os
import re
from typing import Optional

from openevolve.tdes.test_suite import TDESTestSuite, TestEnv

_DATA_PATH = os.path.join(os.path.dirname(__file__), "lca_samples.jsonl")


def _load_samples() -> list:
    if not os.path.exists(_DATA_PATH):
        raise FileNotFoundError(
            f"Dataset not found at {_DATA_PATH}.\n"
            "Download it with:\n"
            "  pip install datasets\n"
            "  python -c \"\n"
            "  from datasets import load_dataset\n"
            "  ds = load_dataset('JetBrains-Research/lca-ci-builds-repair')\n"
            "  ds['train'].to_json('openevolve/tdes/repair/tasks/cicd/lca_samples.jsonl')\n"
            "  \""
        )
    samples = []
    with open(_DATA_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))
    return samples


def _yaml_parses(text: str) -> bool:
    try:
        import yaml
        yaml.safe_load(text)
        return True
    except Exception:
        return False


def _extract_steps(yaml_text: str) -> list:
    """Return list of 'uses' or 'run' values from all job steps."""
    try:
        import yaml
        doc = yaml.safe_load(yaml_text)
        steps = []
        jobs = doc.get("jobs", {}) if doc else {}
        for job in jobs.values():
            for step in job.get("steps", []):
                if "uses" in step:
                    steps.append(("uses", step["uses"]))
                elif "run" in step:
                    steps.append(("run", step["run"][:80]))
        return steps
    except Exception:
        return []


def _structural_match(broken: str, fixed: str) -> float:
    """Return fraction of fixed workflow's top-level keys present in broken."""
    try:
        import yaml
        b = yaml.safe_load(broken) or {}
        f = yaml.safe_load(fixed) or {}
        if not f:
            return 1.0
        keys = set(f.keys())
        return len(keys & set(b.keys())) / len(keys)
    except Exception:
        return 0.0


def get_suite(sample_idx: int = 0) -> TDESTestSuite:
    """Build a TDESTestSuite for one lca-ci-builds-repair sample."""
    samples = _load_samples()
    sample = samples[sample_idx % len(samples)]

    broken_yaml: str = sample.get("buggy_workflow", sample.get("broken", ""))
    fixed_yaml: str = sample.get("fixed_workflow", sample.get("fixed", ""))
    error_msg: str = sample.get("error_message", "")

    suite = TDESTestSuite(modules=["workflow"])

    @suite.unit(
        "workflow",
        id=f"cicd_{sample_idx}_yaml_valid",
        description=f"workflow YAML parses without error (sample {sample_idx})",
    )
    def test_yaml_valid(env: TestEnv):
        env.case(f"sample_{sample_idx}_yaml_parse")
        text = env.workflow.WORKFLOW
        env.check(_yaml_parses(text), f"YAML parse failed: check syntax")

    @suite.integration(
        "workflow",
        id=f"cicd_{sample_idx}_steps_present",
        description=f"required CI steps are present (sample {sample_idx})",
    )
    def test_steps_present(env: TestEnv):
        env.case(f"sample_{sample_idx}_steps")
        text = env.workflow.WORKFLOW
        fixed_steps = _extract_steps(fixed_yaml)
        if not fixed_steps:
            return  # no reference steps to check
        broken_steps = _extract_steps(text)
        broken_tags = {s[1] for s in broken_steps}
        for kind, tag in fixed_steps[:3]:   # check first 3 required steps
            env.case(f"step {kind}={tag}")
            env.check(
                any(tag in bt for bt in broken_tags),
                f"expected step '{tag}' not found in repaired workflow",
            )

    @suite.system(
        "workflow",
        id=f"cicd_{sample_idx}_structural_match",
        description=f"structural match >= 0.8 against known-good fix (sample {sample_idx})",
    )
    def test_structural_match(env: TestEnv):
        env.case(f"sample_{sample_idx}_structure")
        text = env.workflow.WORKFLOW
        score = _structural_match(text, fixed_yaml)
        env.check(
            score >= 0.8,
            f"structural match {score:.2f} < 0.8 (need >= 80% of fixed keys present)",
        )

    return suite


def get_seed_source(sample_idx: int = 0) -> str:
    """Return Python source for the 'workflow' module seeded with the broken YAML."""
    samples = _load_samples()
    sample = samples[sample_idx % len(samples)]
    broken_yaml: str = sample.get("buggy_workflow", sample.get("broken", ""))
    escaped = broken_yaml.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    return f'"""Broken CI/CD workflow — repair this."""\n\nWORKFLOW = """\n{escaped}\n"""\n'
