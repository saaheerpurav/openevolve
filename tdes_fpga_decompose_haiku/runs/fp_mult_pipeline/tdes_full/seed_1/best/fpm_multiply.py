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
    // Result sign is XOR of input signs
    assign result_sign = a_sign ^ b_sign;
    
    // Multiply the mantissas (24-bit × 24-bit = 48-bit)
    assign product = a_mant * b_mant;
    
    // Raw exponent: sum of exponents minus bias (127)
    // a_exp + b_exp - 127, but we need to handle the 10-bit output
    assign raw_exp = a_exp + b_exp - 8'd127;
    
endmodule