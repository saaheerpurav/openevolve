`timescale 1ns/1ps
module fpm_normalize(
    input  [47:0] product,
    input  [9:0]  raw_exp,
    output [22:0] norm_frac,
    output [9:0]  norm_exp,
    output        guard,
    output        sticky
);
    wire needs_shift;
    
    // Check if bit 47 is set (product >= 2.0 in normalized form)
    assign needs_shift = product[47];
    
    // Fraction extraction:
    // If shift needed (bit 47 = 1): frac = bits [46:24]
    // If no shift (bit 47 = 0): frac = bits [45:23]
    assign norm_frac = needs_shift ? product[46:24] : product[45:23];
    
    // Exponent adjustment
    assign norm_exp = needs_shift ? (raw_exp + 10'd1) : raw_exp;
    
    // Guard bit:
    // If shift needed: guard = bit 23
    // If no shift: guard = bit 22
    assign guard = needs_shift ? product[23] : product[22];
    
    // Sticky bit (OR of all remaining bits):
    // If shift needed: sticky = OR(bits[22:0])
    // If no shift: sticky = OR(bits[21:0])
    assign sticky = needs_shift ? 
                    (|product[22:0]) : 
                    (|product[21:0]);
    
endmodule