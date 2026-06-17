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
    // Special case: NaN input, Inf*0, or 0*Inf -> NaN
    // Inf * normal -> Inf with sign
    // 0 * normal -> zero with sign
    // normal * normal -> not special

    wire nan_result  = a_is_nan | b_is_nan | (a_is_inf & b_is_zero) | (a_is_zero & b_is_inf);
    wire inf_result  = (a_is_inf | b_is_inf) & ~nan_result;
    wire zero_result = (a_is_zero | b_is_zero) & ~nan_result & ~inf_result;

    assign is_special = nan_result | inf_result | zero_result;

    always @(*) begin
        if (nan_result)
            special_result = 32'h7FC00000; // quiet NaN
        else if (inf_result)
            special_result = {result_sign, 8'hFF, 23'h0}; // signed Inf
        else if (zero_result)
            special_result = {result_sign, 31'h0}; // signed zero
        else
            special_result = 32'h0;
    end
endmodule