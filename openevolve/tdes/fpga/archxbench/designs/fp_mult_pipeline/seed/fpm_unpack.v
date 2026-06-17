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
    assign a_sign = 0; assign a_exp = 0; assign a_mant = 0;
    assign b_sign = 0; assign b_exp = 0; assign b_mant = 0;
    assign a_is_nan = 0; assign a_is_inf = 0; assign a_is_zero = 0;
    assign b_is_nan = 0; assign b_is_inf = 0; assign b_is_zero = 0;
endmodule
