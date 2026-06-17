// full module source
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
    // Unpack a
    assign a_sign = a[31];
    assign a_exp  = a[30:23];
    // mantissa: implicit leading 1 for normal numbers, no implicit 1 for denormals/zero
    assign a_mant = (a[30:23] == 8'h00) ? {1'b0, a[22:0]} : {1'b1, a[22:0]};
    
    wire a_exp_all_ones = (a[30:23] == 8'hFF);
    wire a_exp_zero     = (a[30:23] == 8'h00);
    wire a_mant_zero    = (a[22:0] == 23'h0);
    
    assign a_is_nan  = a_exp_all_ones & ~a_mant_zero;
    assign a_is_inf  = a_exp_all_ones &  a_mant_zero;
    assign a_is_zero = a_exp_zero     &  a_mant_zero;
    
    // Unpack b
    assign b_sign = b[31];
    assign b_exp  = b[30:23];
    assign b_mant = (b[30:23] == 8'h00) ? {1'b0, b[22:0]} : {1'b1, b[22:0]};
    
    wire b_exp_all_ones = (b[30:23] == 8'hFF);
    wire b_exp_zero     = (b[30:23] == 8'h00);
    wire b_mant_zero    = (b[22:0] == 23'h0);
    
    assign b_is_nan  = b_exp_all_ones & ~b_mant_zero;
    assign b_is_inf  = b_exp_all_ones &  b_mant_zero;
    assign b_is_zero = b_exp_zero     &  b_mant_zero;

endmodule