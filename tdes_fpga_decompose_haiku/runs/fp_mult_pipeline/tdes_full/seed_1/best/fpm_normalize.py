`timescale 1ns/1ps
module fpm_normalize(
    input  [47:0] product,
    input  [9:0]  raw_exp,
    output [22:0] norm_frac,
    output [9:0]  norm_exp,
    output        guard,
    output        sticky
);
    
    // Check if bit 47 is set (overflow case)
    wire overflow = product[47];
    
    // If overflow: extract bits [46:24] as fraction
    // If no overflow: extract bits [45:23] as fraction
    wire [22:0] frac_overflow = product[46:24];
    wire [22:0] frac_no_overflow = product[45:23];
    
    assign norm_frac = overflow ? frac_overflow : frac_no_overflow;
    
    // Adjust exponent: increment if overflow
    assign norm_exp = overflow ? (raw_exp + 1'b1) : raw_exp;
    
    // Guard bit:
    // If overflow: bit 23
    // If no overflow: bit 22
    assign guard = overflow ? product[23] : product[22];
    
    // Sticky bit: OR of remaining bits below guard
    // If overflow: OR of bits [22:0]
    // If no overflow: OR of bits [21:0]
    assign sticky = overflow ? (|product[22:0]) : (|product[21:0]);
    
endmodule