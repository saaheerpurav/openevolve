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
    
    // Product of mantissas (24-bit × 24-bit = 48-bit)
    assign product = a_mant * b_mant;
    
    // Raw exponent: sum of exponents minus bias (127)
    // a_exp + b_exp - 127, but we need to handle the range
    // Result is 10 bits to accommodate values up to 254+254-127=381
    assign raw_exp = {2'b0, a_exp} + {2'b0, b_exp} - 10'd127;
    
endmodule