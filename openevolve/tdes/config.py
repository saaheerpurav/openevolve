"""
Configuration for TDES.

Reuses OpenEvolve's :class:`~openevolve.config.Config` for the LLM ensemble
settings and adds the TDES-specific evolutionary parameters from Appendix A.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Union

import yaml

from openevolve.config import Config


@dataclass
class TDESConfig:
    """Master configuration for a TDES run."""

    # Evolutionary parameters (Appendix A defaults)
    pop_size: int = 5
    max_generations: int = 5
    window_size: int = 3  # negative memory window (section 3.4)

    # Mutation / evaluation
    diff_based: bool = True
    sandbox: bool = True  # run candidate code in an isolated subprocess
    suite_timeout: int = 60  # per-candidate test-suite timeout (seconds)
    mutate_modules_per_candidate: Optional[int] = None  # None = all failing modules

    # Run management
    output_dir: str = "tdes_output"
    random_seed: Optional[int] = 42
    log_level: str = "INFO"

    # LLM ensemble settings (None when running with a scripted mutator)
    llm: Optional[Config] = field(default=None)

    @classmethod
    def from_yaml(cls, path: Union[str, Path]) -> "TDESConfig":
        """Load TDES config from YAML.

        Recognized top-level sections:
          * ``tdes:`` — the evolutionary parameters below
          * everything else (``llm:``, ``prompt:``, ...) — parsed by OpenEvolve's
            :meth:`Config.from_dict` and stored on ``.llm``.
        """
        with open(path, "r", encoding="utf-8") as f:
            raw: Dict[str, Any] = yaml.safe_load(f) or {}

        tdes_section = dict(raw.pop("tdes", {}) or {})
        llm_config = Config.from_dict(raw) if raw else None

        valid = {f for f in cls.__dataclass_fields__ if f != "llm"}
        kwargs = {k: v for k, v in tdes_section.items() if k in valid}
        cfg = cls(**kwargs)
        cfg.llm = llm_config
        return cfg
