`timescale 1ns/1ps
// Pipelined FP multiplier top — instantiates 5 combinational sub-modules
// with pipeline registers between stages.  NOT evolved; embedded in the
// system testbench (same pattern as the Level 3 integrator).
module fp_mult_pipeline #(parameter LATENCY = 5) (
    input         clk,
    input         rst,
    input  [31:0] a,
    input  [31:0] b,
    input         valid_in,
    output [31:0] result,
    output        valid_out
);
    // Valid pipeline shift register
    reg [LATENCY-1:0] valid_pipe;
    assign valid_out = valid_pipe[LATENCY-1];

    // ---- Stage 1: capture inputs + unpack (combinational) ----------------
    reg [31:0] a_s1, b_s1;
    wire        a_sign_s1, b_sign_s1;
    wire [7:0]  a_exp_s1,  b_exp_s1;
    wire [23:0] a_mant_s1, b_mant_s1;
    wire a_nan_s1, a_inf_s1, a_zero_s1;
    wire b_nan_s1, b_inf_s1, b_zero_s1;

    fpm_unpack u_unpack(
        .a(a_s1), .b(b_s1),
        .a_sign(a_sign_s1), .a_exp(a_exp_s1), .a_mant(a_mant_s1),
        .b_sign(b_sign_s1), .b_exp(b_exp_s1), .b_mant(b_mant_s1),
        .a_is_nan(a_nan_s1),  .a_is_inf(a_inf_s1),  .a_is_zero(a_zero_s1),
        .b_is_nan(b_nan_s1),  .b_is_inf(b_inf_s1),  .b_is_zero(b_zero_s1)
    );

    // ---- Stage 2 registers -----------------------------------------------
    reg        a_sign_s2, b_sign_s2;
    reg [7:0]  a_exp_s2,  b_exp_s2;
    reg [23:0] a_mant_s2, b_mant_s2;
    reg a_nan_s2, a_inf_s2, a_zero_s2;
    reg b_nan_s2, b_inf_s2, b_zero_s2;

    wire        result_sign_s2;
    wire [47:0] product_s2;
    wire [9:0]  raw_exp_s2;

    fpm_multiply u_multiply(
        .a_sign(a_sign_s2), .a_exp(a_exp_s2), .a_mant(a_mant_s2),
        .b_sign(b_sign_s2), .b_exp(b_exp_s2), .b_mant(b_mant_s2),
        .result_sign(result_sign_s2), .product(product_s2), .raw_exp(raw_exp_s2)
    );

    // ---- Stage 3 registers -----------------------------------------------
    reg        result_sign_s3;
    reg [47:0] product_s3;
    reg [9:0]  raw_exp_s3;
    reg a_nan_s3, a_inf_s3, a_zero_s3;
    reg b_nan_s3, b_inf_s3, b_zero_s3;

    wire [22:0] norm_frac_s3;
    wire [9:0]  norm_exp_s3;
    wire        guard_s3, sticky_s3;

    fpm_normalize u_normalize(
        .product(product_s3), .raw_exp(raw_exp_s3),
        .norm_frac(norm_frac_s3), .norm_exp(norm_exp_s3),
        .guard(guard_s3), .sticky(sticky_s3)
    );

    // ---- Stage 4 registers -----------------------------------------------
    reg        result_sign_s4;
    reg [22:0] norm_frac_s4;
    reg [9:0]  norm_exp_s4;
    reg        guard_s4, sticky_s4;
    reg a_nan_s4, a_inf_s4, a_zero_s4;
    reg b_nan_s4, b_inf_s4, b_zero_s4;

    wire [31:0] normal_result_s4;
    wire        overflow_s4, underflow_s4;

    fpm_round_pack u_round_pack(
        .sign(result_sign_s4),
        .norm_frac(norm_frac_s4), .norm_exp(norm_exp_s4),
        .guard(guard_s4), .sticky(sticky_s4),
        .result(normal_result_s4),
        .overflow(overflow_s4), .underflow(underflow_s4)
    );

    wire        is_special_s4;
    wire [31:0] special_result_s4;

    fpm_special u_special(
        .a_is_nan(a_nan_s4), .a_is_inf(a_inf_s4), .a_is_zero(a_zero_s4),
        .b_is_nan(b_nan_s4), .b_is_inf(b_inf_s4), .b_is_zero(b_zero_s4),
        .result_sign(result_sign_s4),
        .is_special(is_special_s4), .special_result(special_result_s4)
    );

    // ---- Stage 5: output register ----------------------------------------
    reg [31:0] result_r;
    assign result = result_r;

    always @(posedge clk) begin
        if (rst) begin
            valid_pipe     <= {LATENCY{1'b0}};
            a_s1           <= 32'd0;
            b_s1           <= 32'd0;
            a_sign_s2      <= 0; b_sign_s2   <= 0;
            a_exp_s2       <= 0; b_exp_s2    <= 0;
            a_mant_s2      <= 0; b_mant_s2   <= 0;
            a_nan_s2       <= 0; a_inf_s2    <= 0; a_zero_s2 <= 0;
            b_nan_s2       <= 0; b_inf_s2    <= 0; b_zero_s2 <= 0;
            result_sign_s3 <= 0; product_s3  <= 0; raw_exp_s3 <= 0;
            a_nan_s3       <= 0; a_inf_s3    <= 0; a_zero_s3 <= 0;
            b_nan_s3       <= 0; b_inf_s3    <= 0; b_zero_s3 <= 0;
            result_sign_s4 <= 0;
            norm_frac_s4   <= 0; norm_exp_s4 <= 0;
            guard_s4       <= 0; sticky_s4   <= 0;
            a_nan_s4       <= 0; a_inf_s4    <= 0; a_zero_s4 <= 0;
            b_nan_s4       <= 0; b_inf_s4    <= 0; b_zero_s4 <= 0;
            result_r       <= 32'd0;
        end else begin
            valid_pipe <= {valid_pipe[LATENCY-2:0], valid_in};

            // Stage 0 -> 1: capture inputs
            a_s1 <= a;
            b_s1 <= b;

            // Stage 1 -> 2: register unpack results
            a_sign_s2 <= a_sign_s1; b_sign_s2 <= b_sign_s1;
            a_exp_s2  <= a_exp_s1;  b_exp_s2  <= b_exp_s1;
            a_mant_s2 <= a_mant_s1; b_mant_s2 <= b_mant_s1;
            a_nan_s2  <= a_nan_s1;  a_inf_s2  <= a_inf_s1;  a_zero_s2 <= a_zero_s1;
            b_nan_s2  <= b_nan_s1;  b_inf_s2  <= b_inf_s1;  b_zero_s2 <= b_zero_s1;

            // Stage 2 -> 3: register multiply results
            result_sign_s3 <= result_sign_s2;
            product_s3     <= product_s2;
            raw_exp_s3     <= raw_exp_s2;
            a_nan_s3  <= a_nan_s2;  a_inf_s3  <= a_inf_s2;  a_zero_s3 <= a_zero_s2;
            b_nan_s3  <= b_nan_s2;  b_inf_s3  <= b_inf_s2;  b_zero_s3 <= b_zero_s2;

            // Stage 3 -> 4: register normalize results
            result_sign_s4 <= result_sign_s3;
            norm_frac_s4   <= norm_frac_s3;
            norm_exp_s4    <= norm_exp_s3;
            guard_s4       <= guard_s3;
            sticky_s4      <= sticky_s3;
            a_nan_s4  <= a_nan_s3;  a_inf_s4  <= a_inf_s3;  a_zero_s4 <= a_zero_s3;
            b_nan_s4  <= b_nan_s3;  b_inf_s4  <= b_inf_s3;  b_zero_s4 <= b_zero_s3;

            // Stage 4 -> 5: final mux
            result_r <= is_special_s4 ? special_result_s4 : normal_result_s4;
        end
    end
endmodule
