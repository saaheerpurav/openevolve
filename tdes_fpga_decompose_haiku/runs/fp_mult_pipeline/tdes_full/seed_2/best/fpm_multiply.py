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
    
    // Exponent: subtract bias once during addition
    // result_exp = (a_exp - 127) + (b_exp - 127) + 127 = a_exp + b_exp - 127
    wire [9:0] exp_sum;
    assign exp_sum = {1'b0, a_exp} + {1'b0, b_exp} - 10'd127;
    assign raw_exp = exp_sum;
    
    // Mantissa multiplication: (1.a_mant) × (1.b_mant)
    // Treat 24-bit mantissa as fractional part after implicit leading 1
    // (1 + a_mant/2^24) * (1 + b_mant/2^24)
    // Multiply as integers treating implicit 1 as 2^24:
    // (2^24 + a_mant) * (2^24 + b_mant) = 2^48 + a_mant*2^24 + b_mant*2^24 + a_mant*b_mant
    
    wire [47:0] mant_a_scaled;  // a_mant in 48-bit with implicit 1
    wire [47:0] mant_b_scaled;  // b_mant in 48-bit with implicit 1
    
    assign mant_a_scaled = {1'b1, a_mant};  // 1.a_mant as 48-bit (bit 47 is the 1, bits 46:23 are a_mant)
    assign mant_b_scaled = {1'b1, b_mant};  // 1.b_mant as 48-bit
    
    wire [95:0] full_product;
    assign full_product = mant_a_scaled * mant_b_scaled;  // 48×48 = 96-bit product
    
    // The product is in range [1, 4) in 48-bit fixed point
    // Bits [95:48] contain the integer part, bits [47:0] contain the fractional part
    // We want to return the normalized 48-bit mantissa (bits [47:0] of the result after normalization)
    // Since product is 96-bit and we want 48-bit output with implicit leading 1,
    // we take bits [95:48] which gives us the result with leading 1 in the implicit position
    
    assign product = full_product[95:48];
    
endmodule