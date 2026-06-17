`timescale 1ns/1ps
module fpm_multiply(
    input         a_sign,
    input  [7:0]  a_exp,
    input  [23:0] a_mant,
    input         b_sign,
    input  [7:0]  b_exp,
    input  [23:0] b_mant,
    output        result_sign,
    output [47:0] product,
    output [9:0]  raw_exp
);
    // Sign is XOR of input signs
    assign result_sign = a_sign ^ b_sign;
    
    // Product is multiplication of mantissas (24-bit × 24-bit = 48-bit)
    assign product = a_mant * b_mant;
    
    // Raw exponent is sum of exponents minus the bias (127)
    // Using 10 bits to handle intermediate sum (8+8=16 bits, minus 7 bits bias = 9 bits, but need headroom)
    assign raw_exp = a_exp + b_exp - 10'd127;
endmodule