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
    
    // Product is the 48-bit result of multiplying two 24-bit mantissas
    assign product = a_mant * b_mant;
    
    // Raw exponent: sum of exponents minus bias (127 for single precision)
    // Result uses 10 bits to accommodate exponent range (0-254 gives 0-381)
    assign raw_exp = a_exp + b_exp - 8'd127;
    
endmodule