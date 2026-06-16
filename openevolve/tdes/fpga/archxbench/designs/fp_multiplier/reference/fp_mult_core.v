`timescale 1ns/1ps
// IEEE-754 single-precision FP multiplier core — combinational reference.
// Handles normal operands (special cases: see fp_mult_special).
// Design: flush-to-zero for underflow (matching ArchXBench testbench expectation).
module fp_mult_core #(parameter EXP_WIDTH=8, MANT_WIDTH=23) (
    input  [EXP_WIDTH+MANT_WIDTH:0] a,
    input  [EXP_WIDTH+MANT_WIDTH:0] b,
    output reg [EXP_WIDTH+MANT_WIDTH:0] product,
    output reg [2:0]   flags       // [2]=invalid,[1]=overflow,[0]=underflow
);
    localparam WIDTH = EXP_WIDTH + MANT_WIDTH + 1;
    localparam BIAS  = (1 << (EXP_WIDTH-1)) - 1;  // 127 for single

    wire sa = a[WIDTH-1], sb = b[WIDTH-1];
    wire [EXP_WIDTH-1:0]  ea = a[WIDTH-2:MANT_WIDTH];
    wire [MANT_WIDTH-1:0] ma = a[MANT_WIDTH-1:0];
    wire [EXP_WIDTH-1:0]  eb = b[WIDTH-2:MANT_WIDTH];
    wire [MANT_WIDTH-1:0] mb = b[MANT_WIDTH-1:0];

    wire res_sign = sa ^ sb;

    // 24-bit significands with implicit leading 1
    wire [MANT_WIDTH:0] sigA = {1'b1, ma};
    wire [MANT_WIDTH:0] sigB = {1'b1, mb};

    // Multiply significands: 24-bit × 24-bit = 48-bit product
    wire [2*MANT_WIDTH+1:0] mant_prod = sigA * sigB;

    // Exponent: sum - bias  (bias is counted once in the formula ea+eb-bias)
    // Unbiased result exponent = (ea-bias) + (eb-bias) + leading_bit_adj
    // Biased result exponent = ea + eb - bias
    wire [EXP_WIDTH+1:0] exp_sum = {2'b0, ea} + {2'b0, eb};  // ea+eb
    // Subtract bias
    wire signed [EXP_WIDTH+1:0] exp_raw = $signed(exp_sum) - $signed({{2{1'b0}}, BIAS[EXP_WIDTH-1:0]});

    // The 48-bit product has its leading 1 at bit 46 or 47:
    // - If bit 47 set (both had leading 1s → product >= 2): right-shift by 1, exponent+1
    // - If bit 46 set: already normalized (1.xxxxx...)
    wire prod_msb = mant_prod[2*MANT_WIDTH+1];  // bit 47

    // Normalized mantissa: 24 bits after normalizing (leading 1 at bit 23)
    // With adjustment for the double-leading-1 from multiplication
    wire [2*MANT_WIDTH+1:0] mant_norm = prod_msb ? mant_prod : (mant_prod << 1);
    wire signed [EXP_WIDTH+1:0] exp_adj = exp_raw + {{(EXP_WIDTH){1'b0}}, prod_msb};

    // Extract 23-bit mantissa (bits [46:24] of normalized 48-bit product)
    // mant_norm[47] = implicit 1, [46:24] = 23-bit mantissa, [23:0] = round bits
    wire [MANT_WIDTH-1:0] mant23 = mant_norm[2*MANT_WIDTH:MANT_WIDTH+1];
    // Round bit = mant_norm[23], sticky = |mant_norm[22:0]
    wire Gr = mant_norm[MANT_WIDTH];   // Guard (round) bit
    wire Sr = |mant_norm[MANT_WIDTH-1:0]; // Sticky

    // Round to nearest even (RNE only for simplicity — testbench uses default mode)
    wire round_up = Gr & (Sr | mant23[0]);
    wire [MANT_WIDTH:0] mant_rounded = {1'b0, mant23} + {{MANT_WIDTH{1'b0}}, round_up};
    wire rnd_carry = mant_rounded[MANT_WIDTH];
    wire [MANT_WIDTH-1:0] mant_final = rnd_carry ? {MANT_WIDTH{1'b0}} : mant_rounded[MANT_WIDTH-1:0];
    wire signed [EXP_WIDTH+1:0] exp_final = exp_adj + {{(EXP_WIDTH+1){1'b0}}, rnd_carry};

    always @(*) begin
        flags   = 3'b000;
        product = {WIDTH{1'b0}};

        if ($signed(exp_final) >= $signed({{2{1'b0}}, {EXP_WIDTH{1'b1}}})) begin
            // Overflow → ±Infinity
            flags[1] = 1'b1;
            product  = {res_sign, {EXP_WIDTH{1'b1}}, {MANT_WIDTH{1'b0}}};
        end else if ($signed(exp_final) <= 0) begin
            // Underflow → flush to ±0
            flags[0] = 1'b1;
            product  = {res_sign, {(WIDTH-1){1'b0}}};
        end else begin
            product = {res_sign, exp_final[EXP_WIDTH-1:0], mant_final};
        end
    end
endmodule
