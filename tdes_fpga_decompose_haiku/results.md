# TDES-FPGA Decompose-Then-Evolve Experiment

**Thesis**: decomposing a Level-4 pipelined FP multiplier into 5
independently-evolvable sub-modules enables TDES crossover.

## Solve Rate

| Condition | fp_mult_pipeline | Total |
|---|---|---|
| single_agent_30 | 0/3 | 0/3 |
| tdes_full | 1/3 | 1/3 |
| tdes_no_crossover | 0/3 | 0/3 |

## Crossover Activity (tdes_full only)

| Design | seed | attempts | accepted | total_passes |
|---|---|---|---|---|
| fp_mult_pipeline | 0 | 0 | 0 | 37/59 |
| fp_mult_pipeline | 1 | 2 | 0 | 59/59 |
| fp_mult_pipeline | 2 | 2 | 0 | 53/59 |

## Module First-Solved Generation

| Design | Condition | seed | fpm_unpack | fpm_multiply | fpm_normalize | fpm_round_pack | fpm_special |
|---|---|---|---|---|---|---|---|
| fp_mult_pipeline | tdes_full | 0 | 2 | 1 | 2 | 2 | 1 |
| fp_mult_pipeline | tdes_full | 1 | 2 | 1 | 2 | 2 | 1 |
| fp_mult_pipeline | tdes_full | 2 | 2 | 1 | 2 | 2 | 1 |
| fp_mult_pipeline | tdes_no_crossover | 0 | 2 | 1 | 2 | 2 | 1 |
| fp_mult_pipeline | tdes_no_crossover | 1 | 2 | 1 | 2 | 2 | 1 |
| fp_mult_pipeline | tdes_no_crossover | 2 | 2 | 1 | 2 | 2 | 1 |

## Per-Cell Detail

| Design | Condition | seed 0 | seed 1 | seed 2 | calls (med) |
|---|---|---|---|---|---|
| fp_mult_pipeline | single_agent_30 | 26/59 | 26/59 | 26/59 | 13 |
| fp_mult_pipeline | tdes_full | 37/59 | SOLVED | 53/59 | 22 |
| fp_mult_pipeline | tdes_no_crossover | 37/59 | 55/59 | 58/59 | 24 |