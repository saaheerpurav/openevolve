`timescale 1ns/1ps
module fpm_normalize(
    input  [47:0] product,
    input  [9:0]  raw_exp,
    output [22:0] norm_frac,
    output [9:0]  norm_exp,
    output        guard,
    output        sticky
);
    wire [47:0] shifted;
    wire [4:0] shift_amount;
    wire shift_right;
    
    // Check if we need to shift right (bit 47 is set)
    assign shift_right = product[47];
    
    // Find position of leading 1 for left shift case
    // If bit46=1, shift_amount=1; if bit45=1, shift_amount=2; etc.
    assign shift_amount = shift_right ? 5'd0 :
                          product[46] ? 5'd1 :
                          product[45] ? 5'd2 :
                          product[44] ? 5'd3 :
                          product[43] ? 5'd4 :
                          product[42] ? 5'd5 :
                          product[41] ? 5'd6 :
                          product[40] ? 5'd7 :
                          5'd0;
    
    // Shift: right by 1 if bit47=1, else left by shift_amount
    assign shifted = shift_right ? (product >> 1) : (product << shift_amount);
    
    // Extract 23-bit fraction from bits [46:24]
    assign norm_frac = shifted[46:24];
    
    // Guard bit is bit 23
    assign guard = shifted[23];
    
    // Sticky bit is OR of bits [22:0]
    assign sticky = |shifted[22:0];
    
    // Exponent adjustment: 
    // If shift_right: increment by 1 (we shifted right, so exponent increases)
    // Else: no change (leading 1 is already in implicit position)
    assign norm_exp = shift_right ? (raw_exp + 1) : raw_exp;
    
endmodule