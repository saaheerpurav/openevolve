"""
Merge repair and combopt results into a unified comparison table.

Usage:
    python -m openevolve.tdes.repair.experiments.merge_results \\
        --repair results/repair/ \\
        --combopt results/combopt/ \\
        --out results/merged_table.json

Prints a LaTeX-ready table of final pass rates by condition x task.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict


def load_dir(path: str) -> list:
    results = []
    if not os.path.isdir(path):
        return results
    for fname in os.listdir(path):
        if fname.endswith(".json") and not fname.startswith("_"):
            with open(os.path.join(path, fname), "r", encoding="utf-8") as f:
                try:
                    results.append(json.load(f))
                except json.JSONDecodeError:
                    pass
    return results


def avg_final_rate(records: list) -> float:
    rates = []
    for r in records:
        pg = r.get("test_pass_rate_per_generation", [])
        if pg:
            rates.append(pg[-1])
    return sum(rates) / len(rates) if rates else 0.0


def avg_llm_calls(records: list) -> float:
    calls = [r["llm_calls_to_solution"] for r in records if r.get("llm_calls_to_solution") is not None]
    return sum(calls) / len(calls) if calls else 0.0


def solved_rate(records: list) -> float:
    solved = [r for r in records if r.get("solved")]
    return len(solved) / len(records) if records else 0.0


def print_latex_table(table: dict, conditions: list, tasks: list) -> None:
    print()
    print("% LaTeX results table — paste into paper/results_table.tex")
    print(r"\begin{table}[h]")
    print(r"\centering")
    print(r"\begin{tabular}{l" + "c" * len(tasks) + "}")
    print(r"\toprule")
    print("Condition & " + " & ".join(t.capitalize() for t in tasks) + r" \\")
    print(r"\midrule")
    for cond in conditions:
        row = cond.replace("_", r"\_")
        for task in tasks:
            rate = table.get((cond, task), {}).get("final_pass_rate", 0.0)
            row += f" & {rate:.2f}"
        row += r" \\"
        print(row)
    print(r"\bottomrule")
    print(r"\end{tabular}")
    print(r"\caption{Mean final test-pass rate by condition and task.}")
    print(r"\end{table}")
    print()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repair",  default="results/repair/")
    parser.add_argument("--combopt", default="results/combopt/")
    parser.add_argument("--out",     default="results/merged_table.json")
    args = parser.parse_args()

    repair_records = load_dir(args.repair)
    combopt_records = load_dir(args.combopt)
    all_records = repair_records + combopt_records

    # Group by (condition, task)
    grouped: dict = defaultdict(list)
    for r in all_records:
        key = (r.get("condition", "?"), r.get("task", "?"))
        grouped[key].append(r)

    conditions = ["tdes_full", "tdes_no_crossover", "unconstrained_evo", "single_shot"]
    repair_tasks = ["pipeline", "api", "cicd"]

    table = {}
    for (cond, task), records in grouped.items():
        table[(cond, task)] = {
            "n": len(records),
            "final_pass_rate": round(avg_final_rate(records), 4),
            "solved_rate": round(solved_rate(records), 4),
            "avg_llm_calls": round(avg_llm_calls(records), 1),
        }

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    serializable = {f"{c}|{t}": v for (c, t), v in table.items()}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2)
    print(f"Merged table written to {args.out}")

    print_latex_table(table, conditions, repair_tasks)

    # Ablation summary
    print("=== Ablation: tdes_full vs tdes_no_crossover ===")
    for task in repair_tasks:
        full = table.get(("tdes_full", task), {}).get("final_pass_rate", 0.0)
        abl = table.get(("tdes_no_crossover", task), {}).get("final_pass_rate", 0.0)
        delta = full - abl
        print(f"  {task}: full={full:.3f} ablation={abl:.3f} delta={delta:+.3f}")


if __name__ == "__main__":
    main()
