// full module source
`timescale 1ns/1ps
module fpm_normalize(
    input  [47:0] product,
    input  [9:0]  raw_exp,
    output [22:0] norm_frac,
    output [9:0]  norm_exp,
    output        guard,
    output        sticky
);
    wire overflow = product[47];

    assign norm_frac = overflow ? product[46:24] : product[45:23];
    assign norm_exp  = overflow ? (raw_exp + 10'd1) : raw_exp;
    assign guard     = overflow ? product[23]       : product[22];
    assign sticky    = overflow ? |product[22:0]    : |product[21:0];

endmodule