`timescale 1ns/1ps
module fpm_normalize(
    input  [47:0] product,
    input  [9:0]  raw_exp,
    output [22:0] norm_frac,
    output [9:0]  norm_exp,
    output        guard,
    output        sticky
);
    assign norm_frac = 0;
    assign norm_exp  = 0;
    assign guard     = 0;
    assign sticky    = 0;
endmodule
