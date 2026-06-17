`timescale 1ns/1ps
module fpm_normalize(
    input  [47:0] product,
    input  [9:0]  raw_exp,
    output [22:0] norm_frac,
    output [9:0]  norm_exp,
    output        guard,
    output        sticky
);
    wire [22:0] norm_frac_unshifted;
    wire [22:0] norm_frac_shifted;
    wire guard_unshifted;
    wire guard_shifted;
    wire sticky_unshifted;
    wire sticky_shifted;
    
    // When bit 47 is clear: extract bits [45:23] as fraction, bit 22 as guard, OR of [21:0] as sticky
    assign norm_frac_unshifted = product[45:23];
    assign guard_unshifted = product[22];
    assign sticky_unshifted = |product[21:0];
    
    // When bit 47 is set: right-shift, extract bits [46:24] as fraction, bit 23 as guard, OR of [22:0] as sticky
    assign norm_frac_shifted = product[46:24];
    assign guard_shifted = product[23];
    assign sticky_shifted = |product[22:0];
    
    // Select based on bit 47
    assign norm_frac = product[47] ? norm_frac_shifted : norm_frac_unshifted;
    assign guard = product[47] ? guard_shifted : guard_unshifted;
    assign sticky = product[47] ? sticky_shifted : sticky_unshifted;
    
    // Exponent adjustment
    assign norm_exp = product[47] ? (raw_exp + 10'd1) : raw_exp;
    
endmodule