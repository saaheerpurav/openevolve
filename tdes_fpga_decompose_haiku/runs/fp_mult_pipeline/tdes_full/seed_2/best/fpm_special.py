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

    // Detect special cases
    wire is_nan = a_is_nan | b_is_nan;
    wire is_inf_times_zero = (a_is_inf & b_is_zero) | (b_is_inf & a_is_zero);
    wire is_inf = (a_is_inf | b_is_inf) & ~is_inf_times_zero;
    wire is_zero = (a_is_zero | b_is_zero) & ~is_nan & ~is_inf_times_zero;
    
    assign is_special = is_nan | is_inf_times_zero | is_inf | is_zero;
    
    always @(*) begin
        if (is_nan) begin
            special_result = 32'h7FC00000;  // Quiet NaN
        end
        else if (is_inf_times_zero) begin
            special_result = 32'h7FC00000;  // NaN (inf * 0 is undefined)
        end
        else if (is_inf) begin
            if (result_sign)
                special_result = 32'hFF800000;  // -Inf
            else
                special_result = 32'h7F800000;  // +Inf
        end
        else if (is_zero) begin
            if (result_sign)
                special_result = 32'h80000000;  // -Zero
            else
                special_result = 32'h00000000;  // +Zero
        end
        else begin
            special_result = 32'h00000000;
        end
    end

endmodule