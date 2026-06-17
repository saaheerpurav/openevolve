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
    // Canonical quiet NaN
    localparam [31:0] QNaN = 32'h7FC00000;

    assign is_special = a_is_nan | b_is_nan | a_is_inf | b_is_inf | a_is_zero | b_is_zero;

    always @(*) begin
        if (a_is_nan || b_is_nan) begin
            // NaN input → quiet NaN output
            special_result = QNaN;
        end else if ((a_is_inf && b_is_zero) || (a_is_zero && b_is_inf)) begin
            // Inf × 0 → NaN
            special_result = QNaN;
        end else if (a_is_inf || b_is_inf) begin
            // Inf × non-zero finite → signed Inf
            special_result = {result_sign, 8'hFF, 23'h0};
        end else begin
            // 0 × anything (finite) → signed zero
            special_result = {result_sign, 31'h0};
        end
    end

endmodule