"""
Result analysis for the TDES-Repair campaign.

Renders the paper tables from ``metrics_repair.json``:
  * Table 1 — solve rate per condition, stratified by bug placement
    (split = crossover-favorable, colocated = control). The headline claim is
    tdes_full > tdes_no_crossover on the split stratum and ≈ on the control.
  * Table 2 — crossover mechanism: pairs / attempts / accepted / lift for the
    complementary-coverage crossover vs the unconstrained random baseline.
  * Efficiency — median LLM calls and calls-to-solve per condition.
  * Per-variant ✓/✗ matrix (best over seeds).

Usage:
    python -m openevolve.tdes.repair.experiments.analysis \
        --metrics tdes_repair_results/metrics_repair.json [--write RESULTS.md]
"""

from __future__ import annotations

import argparse
import math
import statistics
import sys
from typing import List, Optional, Tuple

from openevolve.tdes.fpga import metrics

try:  # tables use ✓/✗; force UTF-8 so Windows consoles don't choke
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ALL_CONDITIONS = ["single_shot", "random_crossover", "tdes_no_crossover", "tdes_full"]
STRATA = ["split", "colocated"]


def stratum(design: str) -> str:
    return "colocated" if design.endswith("_coloc") else "split"


def _rate(rows: List[metrics.RunMetrics]) -> Optional[float]:
    return sum(1 for m in rows if m.solved) / len(rows) if rows else None


def _fmt_rate(rate: Optional[float], n: int) -> str:
    return f"{rate:.0%} (n={n})" if rate is not None else "—"


def wilson_ci(k: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    """95% Wilson score interval for a binomial proportion."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def _fmt_rate_ci(rows: List[metrics.RunMetrics]) -> str:
    if not rows:
        return "—"
    k, n = sum(1 for m in rows if m.solved), len(rows)
    lo, hi = wilson_ci(k, n)
    return f"{k}/{n} = {k / n:.0%} [{lo:.0%}, {hi:.0%}]"


def _binom_two_sided(k: int, n: int) -> float:
    """Exact two-sided binomial test p-value against p=0.5."""
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(max(k, n - k), n + 1)) * 0.5**n
    return min(1.0, 2 * tail)


def paired_cells(
    results: List[metrics.RunMetrics], cond_a: str, cond_b: str, s: Optional[str]
) -> List[Tuple[metrics.RunMetrics, metrics.RunMetrics]]:
    """Pair runs of two conditions by (design, seed), optionally within a stratum."""
    index = {
        (m.design, m.seed): m
        for m in results
        if m.condition == cond_b and (s is None or stratum(m.design) == s)
    }
    pairs = []
    for m in results:
        if m.condition != cond_a or (s is not None and stratum(m.design) != s):
            continue
        partner = index.get((m.design, m.seed))
        if partner is not None:
            pairs.append((m, partner))
    return pairs


def _paired_row(results, cond_a, cond_b, s) -> Optional[str]:
    pairs = paired_cells(results, cond_a, cond_b, s)
    if not pairs:
        return None
    # Solve outcome: exact McNemar on discordant pairs.
    a_only = sum(1 for a, b in pairs if a.solved and not b.solved)
    b_only = sum(1 for a, b in pairs if b.solved and not a.solved)
    p_solve = _binom_two_sided(a_only, a_only + b_only)
    # Pass count: sign test over non-tied pairs.
    wins = sum(1 for a, b in pairs if a.total_passes > b.total_passes)
    losses = sum(1 for a, b in pairs if a.total_passes < b.total_passes)
    p_passes = _binom_two_sided(wins, wins + losses)
    return (
        f"| {cond_a} vs {cond_b} | {s or 'all'} | {len(pairs)} | "
        f"+{a_only} / -{b_only} (p={p_solve:.3f}) | "
        f"+{wins} / -{losses} / ={len(pairs) - wins - losses} (p={p_passes:.3f}) |"
    )


def render_paired_table(results: List[metrics.RunMetrics]) -> str:
    lines = [
        "| Comparison | stratum | pairs | solved (discordant, McNemar) | passes (sign test) |",
        "|---|---|---|---|---|",
    ]
    comparisons = [
        ("tdes_full", "tdes_no_crossover", "split"),
        ("tdes_full", "tdes_no_crossover", "colocated"),
        ("tdes_full", "random_crossover", "split"),
        ("tdes_full", "single_shot", None),
        ("tdes_no_crossover", "single_shot", None),
    ]
    for cond_a, cond_b, s in comparisons:
        row = _paired_row(results, cond_a, cond_b, s)
        if row:
            lines.append(row)
    return "\n".join(lines)


def render_solve_table(results: List[metrics.RunMetrics], conditions: List[str]) -> str:
    lines = ["| Stratum | " + " | ".join(conditions) + " |", "|---|" + "---|" * len(conditions)]
    for s in STRATA + ["all"]:
        cells = []
        for c in conditions:
            rows = [
                m for m in results if m.condition == c and (s == "all" or stratum(m.design) == s)
            ]
            cells.append(_fmt_rate_ci(rows))
        lines.append(f"| {s} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _crossover_agg(results: List[metrics.RunMetrics], condition: str, s: str) -> dict:
    pairs = attempts = accepted = lift = raw = 0
    has_raw = False
    for m in results:
        if m.condition != condition or stratum(m.design) != s or not m.crossover:
            continue
        c = m.crossover
        pairs += c.get("pairs_considered", 0)
        attempts += c.get("attempts", 0)
        accepted += c.get("accepted", 0)
        lift += int(round(c.get("mean_lift", 0) * c.get("accepted", 0)))
        if "raw_lift_total" in c:
            has_raw = True
            raw += c["raw_lift_total"]
    return {
        "pairs": pairs,
        "attempts": attempts,
        "accepted": accepted,
        "mean_lift": lift / accepted if accepted else 0.0,
        "raw_mean_lift": (raw / accepted if accepted else 0.0) if has_raw else None,
    }


def render_crossover_table(results: List[metrics.RunMetrics]) -> str:
    lines = [
        "| Condition | stratum | pairs | attempts | accepted | mean lift (clamped) | mean lift (raw) |",
        "|---|---|---|---|---|---|---|",
    ]
    for condition in ["tdes_full", "random_crossover"]:
        for s in STRATA:
            a = _crossover_agg(results, condition, s)
            raw = f"{a['raw_mean_lift']:+.2f}" if a["raw_mean_lift"] is not None else "—"
            lines.append(
                f"| {condition} | {s} | {a['pairs']} | {a['attempts']} | {a['accepted']} "
                f"| +{a['mean_lift']:.2f} | {raw} |"
            )
    return "\n".join(lines)


def _median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def render_efficiency(results: List[metrics.RunMetrics], conditions: List[str]) -> str:
    lines = [
        "| Condition | solve rate | median calls (all) | median calls-to-solve (solved) |",
        "|---|---|---|---|",
    ]
    for c in conditions:
        rows = [m for m in results if m.condition == c]
        if not rows:
            continue
        mc = _median([m.llm_calls for m in rows])
        cts = _median([m.calls_to_solve for m in rows if m.solved])
        mc_s = f"{mc:.0f}" if mc is not None else "—"
        cts_s = f"{cts:.0f}" if cts is not None else "—"
        lines.append(f"| {c} | {_rate(rows):.0%} | {mc_s} | {cts_s} |")
    return "\n".join(lines)


def render_report(results: List[metrics.RunMetrics]) -> str:
    conditions = [c for c in ALL_CONDITIONS if any(m.condition == c for m in results)]
    sections = [
        "# TDES-Repair campaign results",
        f"\n{len(results)} completed cells.",
        "\n## Table 1 — solve rate by bug-placement stratum\n",
        render_solve_table(results, conditions),
        "\n## Per-variant outcome (best over seeds)\n",
        metrics.render_table1(results, conditions),
    ]
    if any(m.crossover for m in results):
        sections += ["\n## Table 2 — crossover mechanism\n", render_crossover_table(results)]
    if len(conditions) > 1:
        sections += [
            "\n## Paired comparisons (matched by design and seed)\n",
            render_paired_table(results),
        ]
    sections += ["\n## Efficiency\n", render_efficiency(results, conditions)]
    return "\n".join(sections)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--metrics",
        nargs="+",
        default=["tdes_repair_results/metrics_repair.json"],
        help="one or more metrics JSON files (shards are concatenated)",
    )
    parser.add_argument("--write", default=None, help="also write the report to this file")
    args = parser.parse_args(argv)

    results = []
    for path in args.metrics:
        results.extend(metrics.load_metrics(path))
    report = render_report(results)
    print(report)
    if args.write:
        with open(args.write, "w", encoding="utf-8") as f:
            f.write(report + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
