`timescale 1ns/1ps
// Unpack IEEE-754 single-precision inputs into sign, exponent, mantissa, and
// classification flags.  Combinational; pipeline registers live in the top.
module fpm_unpack(
    input  [31:0] a,
    input  [31:0] b,
    output        a_sign,
    output [7:0]  a_exp,
    output [23:0] a_mant,
    output        b_sign,
    output [7:0]  b_exp,
    output [23:0] b_mant,
    output        a_is_nan,
    output        a_is_inf,
    output        a_is_zero,
    output        b_is_nan,
    output        b_is_inf,
    output        b_is_zero
);
    assign a_sign = a[31];
    assign a_exp  = a[30:23];
    assign a_mant = (a_exp == 8'd0) ? {1'b0, a[22:0]} : {1'b1, a[22:0]};

    assign b_sign = b[31];
    assign b_exp  = b[30:23];
    assign b_mant = (b_exp == 8'd0) ? {1'b0, b[22:0]} : {1'b1, b[22:0]};

    assign a_is_nan  = (&a_exp) &&  (|a[22:0]);
    assign a_is_inf  = (&a_exp) && ~(|a[22:0]);
    assign a_is_zero = ~(|a_exp) && ~(|a[22:0]);

    assign b_is_nan  = (&b_exp) &&  (|b[22:0]);
    assign b_is_inf  = (&b_exp) && ~(|b[22:0]);
    assign b_is_zero = ~(|b_exp) && ~(|b[22:0]);
endmodule
