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
    
    wire is_nan_result;
    wire is_inf_result;
    wire is_zero_result;
    
    // NaN if either operand is NaN
    assign is_nan_result = a_is_nan | b_is_nan;
    
    // NaN if Inf × 0 or 0 × Inf (indeterminate forms)
    wire inf_times_zero = (a_is_inf & b_is_zero) | (a_is_zero & b_is_inf);
    
    // Infinity if one is Inf and the other is not zero (and not NaN, but that's covered above)
    assign is_inf_result = (a_is_inf | b_is_inf) & ~inf_times_zero & ~is_nan_result;
    
    // Zero if one is zero and the other is not infinity (and not NaN)
    assign is_zero_result = (a_is_zero | b_is_zero) & ~(a_is_inf | b_is_inf) & ~is_nan_result;
    
    // Result is special if any special case applies
    assign is_special = is_nan_result | inf_times_zero | is_inf_result | is_zero_result;
    
    always @(*) begin
        if (is_nan_result | inf_times_zero) begin
            // NaN: quiet NaN with exponent all 1s and non-zero mantissa
            special_result = 32'h7FC00000;
        end
        else if (is_inf_result) begin
            // Infinity with appropriate sign
            if (result_sign) begin
                special_result = 32'hFF800000;  // negative infinity
            end
            else begin
                special_result = 32'h7F800000;  // positive infinity
            end
        end
        else if (is_zero_result) begin
            // Zero with appropriate sign
            if (result_sign) begin
                special_result = 32'h80000000;  // negative zero
            end
            else begin
                special_result = 32'h00000000;  // positive zero
            end
        end
        else begin
            special_result = 32'h00000000;
        end
    end
    
endmodule