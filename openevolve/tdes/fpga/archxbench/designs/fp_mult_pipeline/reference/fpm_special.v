`timescale 1ns/1ps
// Special-case priority logic for IEEE-754 multiplication.  Combinational.
// Priority: NaN > Inf*0=NaN > Inf > Zero.
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
    assign is_special = a_is_nan | b_is_nan | a_is_inf | b_is_inf
                      | a_is_zero | b_is_zero;

    always @(*) begin
        special_result = 32'h7FC00000;
        if (a_is_nan || b_is_nan) begin
            special_result = 32'h7FC00000;
        end else if ((a_is_inf && b_is_zero) || (a_is_zero && b_is_inf)) begin
            special_result = 32'h7FC00000;
        end else if (a_is_inf || b_is_inf) begin
            special_result = {result_sign, 8'hFF, 23'd0};
        end else if (a_is_zero || b_is_zero) begin
            special_result = {result_sign, 31'd0};
        end
    end
endmodule
