# Enhanced TDES-FPGA Experiment Results

## Solve Rate by Condition

| Condition | solve rate | median LLM calls | semantic_xo accepted |
|---|---|---|---|
| best_of_30 | 0% (0/15) | 30 | 0 |
| single_agent | 100% (15/15) | 3 | 0 |
| tdes_full | 87% (13/15) | 6 | 0 |
| tdes_enhanced | 80% (12/15) | 11 | 0 |
| tdes_no_diverse_seed | 80% (12/15) | 6 | 0 |
| tdes_no_semantic_xo | 93% (14/15) | 11 | 0 |
| tdes_no_priority_mut | 93% (14/15) | 11 | 0 |
| tdes_no_positive_mem | 93% (14/15) | 11 | 0 |

## Per-Design Breakdown

| Design | Condition | seed 0 | seed 1 | seed 2 | passes (best) |
|---|---|---|---|---|---|
| carry_select_adder_32bit | best_of_30 | 0/3 | 1/3 | 1/3 | 1/3 |
| carry_select_adder_32bit | single_agent | ✓ | ✓ | ✓ | 3/3 |
| carry_select_adder_32bit | tdes_full | 1/3 | ✓ | 1/3 | 3/3 |
| carry_select_adder_32bit | tdes_enhanced | 1/3 | 1/3 | 1/3 | 1/3 |
| carry_select_adder_32bit | tdes_no_diverse_seed | 1/3 | 1/3 | ✓ | 3/3 |
| carry_select_adder_32bit | tdes_no_semantic_xo | 1/3 | ✓ | ✓ | 3/3 |
| carry_select_adder_32bit | tdes_no_priority_mut | ✓ | 1/3 | ✓ | 3/3 |
| carry_select_adder_32bit | tdes_no_positive_mem | 1/3 | ✓ | ✓ | 3/3 |
| comparator-8bit | best_of_30 | 1/3 | 1/3 | 1/3 | 1/3 |
| comparator-8bit | single_agent | ✓ | ✓ | ✓ | 3/3 |
| comparator-8bit | tdes_full | ✓ | ✓ | ✓ | 3/3 |
| comparator-8bit | tdes_enhanced | ✓ | ✓ | ✓ | 3/3 |
| comparator-8bit | tdes_no_diverse_seed | ✓ | ✓ | ✓ | 3/3 |
| comparator-8bit | tdes_no_semantic_xo | ✓ | ✓ | ✓ | 3/3 |
| comparator-8bit | tdes_no_priority_mut | ✓ | ✓ | ✓ | 3/3 |
| comparator-8bit | tdes_no_positive_mem | ✓ | ✓ | ✓ | 3/3 |
| decoder-3to8 | best_of_30 | 0/3 | 0/3 | 0/3 | 0/3 |
| decoder-3to8 | single_agent | ✓ | ✓ | ✓ | 3/3 |
| decoder-3to8 | tdes_full | ✓ | ✓ | ✓ | 3/3 |
| decoder-3to8 | tdes_enhanced | ✓ | ✓ | ✓ | 3/3 |
| decoder-3to8 | tdes_no_diverse_seed | ✓ | ✓ | ✓ | 3/3 |
| decoder-3to8 | tdes_no_semantic_xo | ✓ | ✓ | ✓ | 3/3 |
| decoder-3to8 | tdes_no_priority_mut | ✓ | ✓ | ✓ | 3/3 |
| decoder-3to8 | tdes_no_positive_mem | ✓ | ✓ | ✓ | 3/3 |
| demux-1to4 | best_of_30 | 1/3 | 1/3 | 1/3 | 1/3 |
| demux-1to4 | single_agent | ✓ | ✓ | ✓ | 3/3 |
| demux-1to4 | tdes_full | ✓ | ✓ | ✓ | 3/3 |
| demux-1to4 | tdes_enhanced | ✓ | ✓ | ✓ | 3/3 |
| demux-1to4 | tdes_no_diverse_seed | ✓ | ✓ | ✓ | 3/3 |
| demux-1to4 | tdes_no_semantic_xo | ✓ | ✓ | ✓ | 3/3 |
| demux-1to4 | tdes_no_priority_mut | ✓ | ✓ | ✓ | 3/3 |
| demux-1to4 | tdes_no_positive_mem | ✓ | ✓ | ✓ | 3/3 |
| mux4to1 | best_of_30 | 1/3 | 1/3 | 1/3 | 1/3 |
| mux4to1 | single_agent | ✓ | ✓ | ✓ | 3/3 |
| mux4to1 | tdes_full | ✓ | ✓ | ✓ | 3/3 |
| mux4to1 | tdes_enhanced | ✓ | ✓ | ✓ | 3/3 |
| mux4to1 | tdes_no_diverse_seed | ✓ | 1/3 | ✓ | 3/3 |
| mux4to1 | tdes_no_semantic_xo | ✓ | ✓ | ✓ | 3/3 |
| mux4to1 | tdes_no_priority_mut | ✓ | ✓ | ✓ | 3/3 |
| mux4to1 | tdes_no_positive_mem | ✓ | ✓ | ✓ | 3/3 |

## Crossover Statistics (enhanced conditions only)

| Condition | xo_attempts | xo_accepted | semantic_attempts | semantic_accepted |
|---|---|---|---|---|
| tdes_enhanced | 0 | 0 | 0 | 0 |
| tdes_no_diverse_seed | 0 | 0 | 0 | 0 |
| tdes_no_semantic_xo | 0 | 0 | 0 | 0 |
| tdes_no_priority_mut | 0 | 0 | 0 | 0 |
| tdes_no_positive_mem | 0 | 0 | 0 | 0 |
| tdes_full | 18 | 18 | 0 | 0 |