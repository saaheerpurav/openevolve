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

    // Extract fields from a
    wire a_sign_bit = a[31];
    wire [7:0] a_exp_bits = a[30:23];
    wire [22:0] a_mant_bits = a[22:0];
    
    // Extract fields from b
    wire b_sign_bit = b[31];
    wire [7:0] b_exp_bits = b[30:23];
    wire [22:0] b_mant_bits = b[22:0];
    
    // Detect special cases for a
    wire a_is_zero_val = (a_exp_bits == 8'b0) & (a_mant_bits == 23'b0);
    wire a_is_inf_val = (a_exp_bits == 8'hFF) & (a_mant_bits == 23'b0);
    wire a_is_nan_val = (a_exp_bits == 8'hFF) & (a_mant_bits != 23'b0);
    
    // Detect special cases for b
    wire b_is_zero_val = (b_exp_bits == 8'b0) & (b_mant_bits == 23'b0);
    wire b_is_inf_val = (b_exp_bits == 8'hFF) & (b_mant_bits == 23'b0);
    wire b_is_nan_val = (b_exp_bits == 8'hFF) & (b_mant_bits != 23'b0);
    
    // Add implicit leading 1 for normalized numbers (exp != 0 and exp != 255)
    wire a_is_normalized = (a_exp_bits != 8'b0) & (a_exp_bits != 8'hFF);
    wire b_is_normalized = (b_exp_bits != 8'b0) & (b_exp_bits != 8'hFF);
    
    wire [23:0] a_mant_val = a_is_normalized ? {1'b1, a_mant_bits} : {1'b0, a_mant_bits};
    wire [23:0] b_mant_val = b_is_normalized ? {1'b1, b_mant_bits} : {1'b0, b_mant_bits};
    
    // Assign outputs for a
    assign a_sign = a_sign_bit;
    assign a_exp = a_exp_bits;
    assign a_mant = a_mant_val;
    assign a_is_nan = a_is_nan_val;
    assign a_is_inf = a_is_inf_val;
    assign a_is_zero = a_is_zero_val;
    
    // Assign outputs for b
    assign b_sign = b_sign_bit;
    assign b_exp = b_exp_bits;
    assign b_mant = b_mant_val;
    assign b_is_nan = b_is_nan_val;
    assign b_is_inf = b_is_inf_val;
    assign b_is_zero = b_is_zero_val;

endmodule