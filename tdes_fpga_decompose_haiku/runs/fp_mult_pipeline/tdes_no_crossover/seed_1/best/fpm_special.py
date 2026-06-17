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
    
    // NaN if either input is NaN
    assign is_nan = a_is_nan | b_is_nan;
    
    // Inf × 0 or 0 × Inf is NaN
    assign is_inf_times_zero = (a_is_inf & b_is_zero) | (a_is_zero & b_is_inf);
    
    // Result is special if any special case detected
    assign is_special = is_nan | is_inf_times_zero | a_is_inf | b_is_inf | a_is_zero | b_is_zero;
    
    // Determine if result should be Inf (but not if it's Inf×0 which becomes NaN)
    assign is_inf = (a_is_inf | b_is_inf) & ~is_inf_times_zero;
    
    // Determine if result should be Zero (but not if it's Inf×0 which becomes NaN)
    assign is_zero = (a_is_zero | b_is_zero) & ~is_inf_times_zero;
    
    always @(*) begin
        if (is_nan | is_inf_times_zero) begin
            // Output NaN: 0x7FC00000
            special_result = 32'h7FC00000;
        end
        else if (is_inf) begin
            // Output Infinity with sign
            special_result = {result_sign, 8'hFF, 23'h0};
        end
        else if (is_zero) begin
            // Output Zero with sign
            special_result = {result_sign, 31'h0};
        end
        else begin
            special_result = 32'h0;
        end
    end
    
endmodule