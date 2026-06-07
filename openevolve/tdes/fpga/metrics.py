"""
Metrics collection + result-table rendering for TDES-FPGA experiments.

Captures the per-run quantities the paper reports (Pass@k, pass trajectory,
generations-to-solve, escalation, crossover attempt/success/lift) and renders
the Table 1 (method comparison) and Table 2 (crossover analysis) templates.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


@dataclass
class RunMetrics:
    design: str
    condition: str
    seed: int
    solved: bool
    total_passes: int
    total_tests: int
    generations_run: int
    escalated: bool
    trajectory: List[int] = field(default_factory=list)  # best total passes per generation
    crossover: Optional[dict] = None  # CrossoverStats.as_dict()

    @property
    def pass_at_final(self) -> bool:
        return self.solved

    def to_dict(self) -> dict:
        return asdict(self)


def from_result(design, condition, seed, result, total_tests, crossover=None) -> RunMetrics:
    """Build RunMetrics from a TDESResult."""
    best = result.best
    passes = best.vector.total_passes if best.vector else 0
    trajectory = [h.get("best_summary_passes", 0) for h in result.history] if result.history else []
    # history stores summaries; recompute trajectory from score where available
    traj = []
    for h in result.history:
        # "best_summary" like "system X, integration Y, unit Z (P/T total)"
        summary = h.get("best_summary", "")
        traj.append(_passes_from_summary(summary))
    return RunMetrics(
        design=design,
        condition=condition,
        seed=seed,
        solved=passes == total_tests and total_tests > 0,
        total_passes=passes,
        total_tests=total_tests,
        generations_run=result.generations_run,
        escalated=result.escalated,
        trajectory=traj,
        crossover=crossover,
    )


def _passes_from_summary(summary: str) -> int:
    # ".... (P/T total)"
    import re

    m = re.search(r"\((\d+)\s*/\s*\d+\s*total\)", summary)
    return int(m.group(1)) if m else 0


def save_metrics(metrics: List[RunMetrics], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump([m.to_dict() for m in metrics], f, indent=2)


def load_metrics(path: str) -> List[RunMetrics]:
    with open(path, "r", encoding="utf-8") as f:
        return [RunMetrics(**d) for d in json.load(f)]


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def solve_rate(metrics: List[RunMetrics], condition: str) -> float:
    rows = [m for m in metrics if m.condition == condition]
    if not rows:
        return 0.0
    return sum(1 for m in rows if m.solved) / len(rows)


def aggregate_crossover(metrics: List[RunMetrics]) -> dict:
    """Pool crossover stats across all runs that recorded them."""
    pairs = attempts = accepted = lift = 0
    for m in metrics:
        c = m.crossover
        if not c:
            continue
        pairs += c.get("pairs_considered", 0)
        attempts += c.get("attempts", 0)
        accepted += c.get("accepted", 0)
        lift += int(round(c.get("mean_lift", 0) * c.get("accepted", 0)))
    return {
        "pairs_considered": pairs,
        "attempts": attempts,
        "accepted": accepted,
        "attempt_rate": round(attempts / pairs, 4) if pairs else 0.0,
        "success_rate": round(accepted / attempts, 4) if attempts else 0.0,
        "mean_lift": round(lift / accepted, 4) if accepted else 0.0,
    }


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


def render_table1(metrics: List[RunMetrics], conditions: List[str]) -> str:
    """Per-design solved (✓/✗) across conditions (best over seeds)."""
    designs = sorted({m.design for m in metrics})
    header = "| Design | " + " | ".join(conditions) + " |"
    sep = "|" + "---|" * (len(conditions) + 1)
    lines = [header, sep]
    for d in designs:
        cells = []
        for c in conditions:
            rows = [m for m in metrics if m.design == d and m.condition == c]
            solved = any(m.solved for m in rows)
            cells.append("✓" if solved else ("✗" if rows else "-"))
        lines.append(f"| {d} | " + " | ".join(cells) + " |")
    # solve-rate footer
    footer = (
        "| **solve rate** | "
        + " | ".join(f"{solve_rate(metrics, c):.0%}" for c in conditions)
        + " |"
    )
    lines.append(footer)
    return "\n".join(lines)


def render_table2(metrics: List[RunMetrics]) -> str:
    agg = aggregate_crossover(metrics)
    return "\n".join(
        [
            "| Metric | Value |",
            "|---|---|",
            f"| Crossover pairs considered | {agg['pairs_considered']} |",
            f"| Complementary coverage existed | {agg['attempts']} ({agg['attempt_rate']:.0%}) |",
            f"| Accepted (strict superset) | {agg['accepted']} ({agg['success_rate']:.0%}) |",
            f"| Mean Δ tests per successful crossover | +{agg['mean_lift']:.2f} |",
        ]
    )
