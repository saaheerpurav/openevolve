# TDES-FPGA benchmarks

These benchmark repositories are **not vendored** (they are gitignored). Clone
them here before running the experiment harness.

```bash
cd openevolve/tdes/fpga/benchmarks
git clone --depth 1 https://github.com/hkust-zhiyao/RTLLM.git        rtllm
git clone --depth 1 https://github.com/sureshpurini/ArchXBench.git   archxbench
git clone --depth 1 https://github.com/jultrishyyy/ResBench.git      resbench
```

| Benchmark | Layout expected by the loader |
|---|---|
| `rtllm/`     | `Category/[Sub/]design/` with `design_description.txt`, `testbench.v`, `verified_*.v` |
| `archxbench/`| `level-*/design/` with `design-specs.txt`, `problem-description.txt`, `tb.v` (no reference RTL) |
| `resbench/`  | `problems.json` (module / Problem / Module header / Testbench) + `solutions/` |

## EDA toolchain

Simulation/synthesis needs Icarus Verilog (`iverilog`/`vvp`) and, for
synthesis tests, Yosys. The easiest cross-platform install is the
[OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build/releases)
(ships `iverilog`, `vvp`, `yosys`, `verilator`).

On Windows/MSYS the suite keeps its DLLs in `lib`, so both `bin` **and** `lib`
must be on `PATH`. The cleanest way is to point TDES-FPGA at the install root:

```bash
export OSS_CAD_SUITE_ROOT=/path/to/oss-cad-suite   # auto-activates bin+lib on import
```

(or call `openevolve.tdes.fpga.activate_toolchain(root)`). On Linux/macOS,
`apt-get install iverilog yosys` and a normal `PATH` are sufficient.

## Quick checks

```bash
# offline harness mechanics (reference-injecting mutator, no API key):
python -m openevolve.tdes.fpga.experiments.run_rtllm --scripted \
    --designs adder_8bit adder_16bit --conditions tdes_full tdes_no_crossover

# real LLM run (set OPENAI_API_KEY):
python -m openevolve.tdes.fpga.experiments.ablation --benchmark rtllm \
    --designs adder_8bit multi_16bit \
    --config openevolve/tdes/fpga/experiments/configs/tdes_full.yaml --seeds 0 1 2
```

## Design usability

Not every benchmark design is a sound evolution target: some references do not
pass under the open-source toolchain, and a few testbenches are too weak to fail
an empty skeleton. The harness calls `benchmark_loader.is_usable(seed, suite)`
to skip those automatically (RTLLM yields ~36 usable designs of 50).
