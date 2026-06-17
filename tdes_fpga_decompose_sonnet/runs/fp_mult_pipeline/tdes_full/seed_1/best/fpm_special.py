`timescale 1ns/1ps
module fpm_special(
    input         a_is_nan,
    input         a_is_inf,
    input         a_is_zero,
    input         b_is_nan,
    input         b_is_inf,
    input         b_is_zero,
    input         result_sign,
    output        is_special,
    output reg [31:0] special_result
);
    // Special case detection
    wire nan_result  = a_is_nan | b_is_nan | (a_is_inf & b_is_zero) | (a_is_zero & b_is_inf);
    wire inf_result  = (a_is_inf | b_is_inf) & ~nan_result;
    wire zero_result = (a_is_zero | b_is_zero) & ~nan_result;

    assign is_special = nan_result | inf_result | zero_result;

    always @(*) begin
        if (nan_result)
            special_result = 32'h7FC00000; // Quiet NaN
        else if (inf_result)
            special_result = {result_sign, 8'hFF, 23'h0}; // Signed Inf
        else if (zero_result)
            special_result = {result_sign, 31'h0}; // Signed zero
        else
            special_result = 32'h0;
    end
endmodule