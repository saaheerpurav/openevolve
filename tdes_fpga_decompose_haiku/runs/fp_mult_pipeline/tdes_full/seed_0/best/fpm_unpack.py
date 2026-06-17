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
    assign a_exp = a[30:23];
    wire [22:0] a_mant_frac = a[22:0];
    
    // Determine a special cases
    assign a_is_zero = (a_exp == 8'b0) && (a_mant_frac == 23'b0);
    assign a_is_inf = (a_exp == 8'hFF) && (a_mant_frac == 23'b0);
    assign a_is_nan = (a_exp == 8'hFF) && (a_mant_frac != 23'b0);
    
    // Build a mantissa with implicit 1 for normalized numbers
    // For normalized (exp != 0): mant = 1.mant_frac (24 bits, implicit 1 in bit 23)
    // For denormal (exp == 0): mant = 0.mant_frac (24 bits, no implicit 1)
    assign a_mant = (a_exp == 8'b0) ? {1'b0, a_mant_frac} : {1'b1, a_mant_frac};
    
    // Unpack b
    assign b_sign = b[31];
    assign b_exp = b[30:23];
    wire [22:0] b_mant_frac = b[22:0];
    
    // Determine b special cases
    assign b_is_zero = (b_exp == 8'b0) && (b_mant_frac == 23'b0);
    assign b_is_inf = (b_exp == 8'hFF) && (b_mant_frac == 23'b0);
    assign b_is_nan = (b_exp == 8'hFF) && (b_mant_frac != 23'b0);
    
    // Build b mantissa with implicit 1 for normalized numbers
    assign b_mant = (b_exp == 8'b0) ? {1'b0, b_mant_frac} : {1'b1, b_mant_frac};
    
endmodule