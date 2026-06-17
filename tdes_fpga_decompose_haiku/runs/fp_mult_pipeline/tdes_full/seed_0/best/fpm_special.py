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
    
    // is_special is 1 if any operand is NaN, Inf, or Zero
    assign is_special = a_is_nan | a_is_inf | a_is_zero | b_is_nan | b_is_inf | b_is_zero;
    
    always @(*) begin
        // Default: normal case (should not reach here if is_special=0)
        special_result = 32'h0;
        
        // NaN cases: if either operand is NaN, result is NaN
        if (a_is_nan | b_is_nan) begin
            special_result = 32'h7FC00000;  // Quiet NaN
        end
        // Inf × 0 or 0 × Inf → NaN (invalid operation)
        else if ((a_is_inf & b_is_zero) | (a_is_zero & b_is_inf)) begin
            special_result = 32'h7FC00000;  // NaN
        end
        // Inf × non-zero → Inf with sign
        else if (a_is_inf | b_is_inf) begin
            special_result = {result_sign, 31'h7F800000};
        end
        // 0 × non-zero → signed zero
        else if (a_is_zero | b_is_zero) begin
            special_result = {result_sign, 31'h0};
        end
    end
    
endmodule