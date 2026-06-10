"""
TDES-MAE entry point.

Usage:
    python -m openevolve.tdes.mae.run                       # CPU, Haiku, 10 gens
    python -m openevolve.tdes.mae.run --device cuda
    python -m openevolve.tdes.mae.run --gens 2 --scripted   # offline smoke test
    python -m openevolve.tdes.mae.run --compare-only best.py  # just the head-to-head

Outputs (under --out, default ./tdes_mae_results):
    evolution_log.json        per-generation population, scores, raw eval records
    best_mask_fn.py           the best evolved masking module (importable)
    baseline_vs_evolved.json  3-seed head-to-head at system_epochs
    convergence_plot.png      best probe accuracy per generation (if matplotlib)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import statistics
import sys
from typing import Dict, List, Optional

from openevolve.tdes.config import TDESConfig
from openevolve.tdes.mae import masking
from openevolve.tdes.mae.config import MAEConfig
from openevolve.tdes.mae.controller import build_controller
from openevolve.tdes.mae.evaluator import MAESuite
from openevolve.tdes.mae.mutation import MaskLLMMutator
from openevolve.tdes.mae.trainer import pretrain_and_probe

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "configs", "anthropic_haiku.yaml"
)


def _scripted_mutator():
    """Offline stand-in: proposes a fixed 2x2 block-masking strategy once."""
    from openevolve.tdes.mutation import ScriptedMutator

    block_source = '''\
import torch


def generate_mask(batch_size, num_patches, mask_ratio, epoch, device):
    """Mask three of the four 2x2 quadrant-blocks per image (12/16 = 0.75)."""
    grid = 4
    blocks = torch.tensor([[0, 1, 4, 5], [2, 3, 6, 7], [8, 9, 12, 13], [10, 11, 14, 15]])
    mask = torch.zeros(batch_size, num_patches, dtype=torch.bool, device=device)
    for i in range(batch_size):
        keep = torch.randint(4, (1,)).item()
        for b in range(4):
            if b != keep:
                mask[i, blocks[b]] = True
    return mask
'''

    def fix(module, source, feedback, memory_text):
        if "quadrant-blocks" in source:
            return None
        return block_source, "2x2 block masking (scripted)"

    return ScriptedMutator(fix)


def compare(baseline_source: str, evolved_source: str, cfg: MAEConfig, seeds: List[int]) -> Dict:
    """Head-to-head at full system budget across seeds."""
    rows = []
    for seed in seeds:
        base = pretrain_and_probe(baseline_source, cfg.system_epochs, cfg, seed=seed)
        evo = pretrain_and_probe(evolved_source, cfg.system_epochs, cfg, seed=seed)
        rows.append({"seed": seed, "baseline": base, "evolved": evo})
        logger.info(
            "seed %d: baseline acc %.3f vs evolved acc %.3f",
            seed,
            base["probe_acc"],
            evo["probe_acc"],
        )
    base_accs = [r["baseline"]["probe_acc"] for r in rows]
    evo_accs = [r["evolved"]["probe_acc"] for r in rows]
    return {
        "epochs": cfg.system_epochs,
        "seeds": seeds,
        "runs": rows,
        "baseline_mean_acc": statistics.mean(base_accs),
        "evolved_mean_acc": statistics.mean(evo_accs),
        "mean_delta": statistics.mean(evo_accs) - statistics.mean(base_accs),
        "evolved_wins": sum(e > b for e, b in zip(evo_accs, base_accs)),
    }


def _plot_convergence(history: List[Dict], rungs, out_path: str) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        logger.info("matplotlib not installed; skipping convergence plot")
        return
    gens = [h["generation"] for h in history]
    # Best candidate's SYSTEM passes -> highest rung reached that generation.
    best_acc = []
    for h in history:
        n_sys = h["best_score_key"][0]
        best_acc.append(rungs[n_sys - 1] if n_sys else 0.0)
    plt.figure(figsize=(6, 4))
    plt.step(gens, best_acc, where="post", marker="o")
    plt.xlabel("generation")
    plt.ylabel("highest probe-accuracy rung passed (best candidate)")
    plt.title("TDES-MAE convergence")
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_path, dpi=120)
    logger.info("wrote %s", out_path)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=_DEFAULT_CONFIG)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--gens", type=int, default=None)
    parser.add_argument("--pop", type=int, default=None)
    parser.add_argument("--out", default="tdes_mae_results")
    parser.add_argument("--scripted", action="store_true", help="offline smoke test (no LLM)")
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    parser.add_argument(
        "--patience", type=int, default=3, help="flat generations before escalating"
    )
    parser.add_argument("--compare-only", default=None, metavar="MASK_PY")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    os.makedirs(args.out, exist_ok=True)
    mae_cfg = MAEConfig(device=args.device)

    if args.compare_only:
        with open(args.compare_only, "r", encoding="utf-8") as f:
            evolved = f.read()
        result = compare(masking.BASELINE_SOURCE, evolved, mae_cfg, args.seeds)
        path = os.path.join(args.out, "baseline_vs_evolved.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(json.dumps({k: v for k, v in result.items() if k != "runs"}, indent=2))
        return 0

    tdes_cfg = TDESConfig.from_yaml(args.config)
    tdes_cfg.output_dir = os.path.join(args.out, "runs")
    if args.gens:
        tdes_cfg.max_generations = args.gens
    if args.pop:
        tdes_cfg.pop_size = args.pop

    if args.scripted:
        mutator = _scripted_mutator()
    else:
        from openevolve.llm.ensemble import LLMEnsemble

        if tdes_cfg.llm is None or not tdes_cfg.llm.llm.models:
            raise SystemExit("config has no llm: section (or use --scripted)")
        mutator = MaskLLMMutator(LLMEnsemble(tdes_cfg.llm.llm.models))

    suite = MAESuite(mae_cfg)
    controller = build_controller(
        masking.BASELINE_SOURCE, suite, mutator, tdes_cfg, stagnation_patience=args.patience
    )
    try:
        result = controller.run()

        best_source = result.best.modules["masking"]
        best_path = os.path.join(args.out, "best_mask_fn.py")
        with open(best_path, "w", encoding="utf-8") as f:
            f.write(best_source)

        log = {
            "generations_run": result.generations_run,
            "escalated": result.escalated,
            "best_summary": result.best.vector.summary(),
            "history": result.history,
            "eval_records": suite.eval_records,
        }
        with open(os.path.join(args.out, "evolution_log.json"), "w", encoding="utf-8") as f:
            json.dump(log, f, indent=2)

        _plot_convergence(
            result.history,
            list(mae_cfg.system_acc_rungs),
            os.path.join(args.out, "convergence_plot.png"),
        )

        evolved_is_new = best_source.strip() != masking.BASELINE_SOURCE.strip()
        comparison = None
        if evolved_is_new:
            logger.info("running 3-seed baseline-vs-evolved comparison ...")
            comparison = compare(masking.BASELINE_SOURCE, best_source, mae_cfg, args.seeds)
            with open(
                os.path.join(args.out, "baseline_vs_evolved.json"), "w", encoding="utf-8"
            ) as f:
                json.dump(comparison, f, indent=2)
        else:
            logger.info("best candidate is still the baseline; no comparison to run")

        print(f"\nBest: {result.best.vector.summary()}  ({best_path})")
        if comparison:
            print(
                f"Head-to-head ({len(args.seeds)} seeds, {mae_cfg.system_epochs} epochs): "
                f"baseline {comparison['baseline_mean_acc']:.3f} vs "
                f"evolved {comparison['evolved_mean_acc']:.3f} "
                f"(delta {comparison['mean_delta']:+.3f}, "
                f"wins {comparison['evolved_wins']}/{len(args.seeds)})"
            )
        return 0
    finally:
        suite.close()


if __name__ == "__main__":
    sys.exit(main())
