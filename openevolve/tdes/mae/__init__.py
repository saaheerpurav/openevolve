"""
TDES-MAE: evolving masking strategies for a tiny Masked Autoencoder.

A validation experiment showing TDES can evolve *ML training components*
(here, the patch-masking strategy of an MAE pretrained on CIFAR-10) with the
same hierarchical test-feedback loop used for code synthesis. The evolved
artifact is a single Python module ``masking`` containing ``generate_mask()``;
the evaluator is a 3-tier suite (unit checks on the mask itself -> short
training run -> full pretrain + linear probe). Single-module problem, so
crossover is intentionally disabled — this layer validates hierarchical
selection, CEGIS feedback, and negative-exemplar memory in an ML context.

Reuses the base TDES controller/selection/memory unchanged (duck-typed suite),
like the fpga/ and combopt/ layers. Do not modify base ``tdes/*`` files.
"""
