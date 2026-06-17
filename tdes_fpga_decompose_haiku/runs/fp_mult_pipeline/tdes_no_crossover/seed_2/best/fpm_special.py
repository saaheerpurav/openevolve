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
    
    // is_special is 1 if any operand is special (NaN, Inf, or Zero)
    assign is_special = a_is_nan | a_is_inf | a_is_zero | b_is_nan | b_is_inf | b_is_zero;
    
    always @(*) begin
        if (a_is_nan | b_is_nan) begin
            // NaN × anything → NaN
            special_result = 32'h7FC00000;
        end
        else if ((a_is_inf & b_is_zero) | (a_is_zero & b_is_inf)) begin
            // Inf × 0 or 0 × Inf → NaN
            special_result = 32'h7FC00000;
        end
        else if (a_is_inf | b_is_inf) begin
            // Inf × normal or Inf × Inf → Inf with sign
            special_result = result_sign ? 32'hFF800000 : 32'h7F800000;
        end
        else if (a_is_zero | b_is_zero) begin
            // 0 × anything → signed zero
            special_result = result_sign ? 32'h80000000 : 32'h00000000;
        end
        else begin
            special_result = 32'h00000000;
        end
    end
    
endmodule