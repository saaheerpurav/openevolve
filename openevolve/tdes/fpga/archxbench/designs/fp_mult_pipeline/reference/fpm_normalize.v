`timescale 1ns/1ps
// Normalize the 48-bit mantissa product and extract guard/sticky bits.
// Combinational.
module fpm_normalize(
    input  [47:0] product,
    input  [9:0]  raw_exp,
    output [22:0] norm_frac,
    output [9:0]  norm_exp,
    output        guard,
    output        sticky
);
    wire msb = product[47];
    wire [47:0] shifted = msb ? product : (product << 1);
    assign norm_exp  = msb ? (raw_exp + 10'd1) : raw_exp;
    assign norm_frac = shifted[46:24];
    assign guard     = shifted[23];
    assign sticky    = |shifted[22:0];
endmodule
