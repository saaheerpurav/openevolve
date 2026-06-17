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
    
    wire is_nan;
    wire is_inf_times_zero;
    wire is_inf;
    wire is_zero;
    
    // NaN if either operand is NaN
    assign is_nan = a_is_nan | b_is_nan;
    
    // Inf × 0 or 0 × Inf produces NaN
    assign is_inf_times_zero = (a_is_inf & b_is_zero) | (a_is_zero & b_is_inf);
    
    // Infinity result (but not if it's inf*0 which is NaN)
    assign is_inf = (a_is_inf | b_is_inf) & ~is_inf_times_zero;
    
    // Zero result (but not if it involves inf*0 which is NaN)
    assign is_zero = (a_is_zero | b_is_zero) & ~is_inf_times_zero;
    
    // Special case if any of the above apply
    assign is_special = is_nan | is_inf_times_zero | is_inf | is_zero;
    
    always @(*) begin
        if (is_nan | is_inf_times_zero) begin
            // NaN: 0x7FC00000 (quiet NaN with sign bit 0)
            special_result = 32'h7FC00000;
        end
        else if (is_inf) begin
            // Infinity: sign bit determines +Inf or -Inf
            special_result = {result_sign, 31'h7F800000};
        end
        else if (is_zero) begin
            // Zero: sign bit determines +0 or -0
            special_result = {result_sign, 31'h00000000};
        end
        else begin
            special_result = 32'h00000000;
        end
    end
    
endmodule