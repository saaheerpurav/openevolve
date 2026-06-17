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
    assign result_sign = a_sign ^ b_sign;
    assign product     = a_mant * b_mant;
    assign raw_exp     = {2'b00, a_exp} + {2'b00, b_exp} - 10'd127;
endmodule