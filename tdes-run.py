#!/usr/bin/env python3
"""
Entry point for Test-Driven Evolutionary Synthesis (TDES).

Usage:
    python tdes-run.py <seed_dir> <suite.py> [--config cfg.yaml] [--gens N] \
        [--pop N] [--scripted] [--output DIR]

See openevolve/tdes/ for the framework and examples/tdes_example/ for a demo.
"""

import sys

from openevolve.tdes.cli import main

if __name__ == "__main__":
    sys.exit(main())
