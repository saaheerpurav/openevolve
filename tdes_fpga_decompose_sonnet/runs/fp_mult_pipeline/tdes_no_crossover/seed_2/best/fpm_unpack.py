// full module source
`timescale 1ns/1ps
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
    // Unpack a
    assign a_sign = a[31];
    assign a_exp  = a[30:23];
    // mantissa: implicit leading 1 for normal numbers, no implicit 1 for denormals/zero
    assign a_mant = (a[30:23] == 8'h00) ? {1'b0, a[22:0]}   // denormal or zero: no implicit 1
                                         : {1'b1, a[22:0]};  // normal: implicit 1

    // Special cases for a
    assign a_is_zero = (a[30:0] == 31'h0);                          // exp=0, mantissa=0
    assign a_is_inf  = (a[30:23] == 8'hFF) && (a[22:0] == 23'h0);  // exp=FF, mantissa=0
    assign a_is_nan  = (a[30:23] == 8'hFF) && (a[22:0] != 23'h0);  // exp=FF, mantissa!=0

    // Unpack b
    assign b_sign = b[31];
    assign b_exp  = b[30:23];
    assign b_mant = (b[30:23] == 8'h00) ? {1'b0, b[22:0]}
                                         : {1'b1, b[22:0]};

    // Special cases for b
    assign b_is_zero = (b[30:0] == 31'h0);
    assign b_is_inf  = (b[30:23] == 8'hFF) && (b[22:0] == 23'h0);
    assign b_is_nan  = (b[30:23] == 8'hFF) && (b[22:0] != 23'h0);

endmodule