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
    wire a_sign_raw = a[31];
    wire [7:0] a_exp_raw = a[30:23];
    wire [22:0] a_mant_raw = a[22:0];
    
    wire a_is_normal = (a_exp_raw != 8'b0) && (a_exp_raw != 8'hFF);
    wire a_is_denormal = (a_exp_raw == 8'b0) && (a_mant_raw != 23'b0);
    wire a_is_zero_raw = (a_exp_raw == 8'b0) && (a_mant_raw == 23'b0);
    wire a_is_inf_raw = (a_exp_raw == 8'hFF) && (a_mant_raw == 23'b0);
    wire a_is_nan_raw = (a_exp_raw == 8'hFF) && (a_mant_raw != 23'b0);
    
    assign a_sign = a_sign_raw;
    assign a_exp = a_exp_raw;
    assign a_mant = a_is_normal ? {1'b1, a_mant_raw} : {1'b0, a_mant_raw};
    assign a_is_nan = a_is_nan_raw;
    assign a_is_inf = a_is_inf_raw;
    assign a_is_zero = a_is_zero_raw;
    
    // Unpack b
    wire b_sign_raw = b[31];
    wire [7:0] b_exp_raw = b[30:23];
    wire [22:0] b_mant_raw = b[22:0];
    
    wire b_is_normal = (b_exp_raw != 8'b0) && (b_exp_raw != 8'hFF);
    wire b_is_denormal = (b_exp_raw == 8'b0) && (b_mant_raw != 23'b0);
    wire b_is_zero_raw = (b_exp_raw == 8'b0) && (b_mant_raw == 23'b0);
    wire b_is_inf_raw = (b_exp_raw == 8'hFF) && (b_mant_raw == 23'b0);
    wire b_is_nan_raw = (b_exp_raw == 8'hFF) && (b_mant_raw != 23'b0);
    
    assign b_sign = b_sign_raw;
    assign b_exp = b_exp_raw;
    assign b_mant = b_is_normal ? {1'b1, b_mant_raw} : {1'b0, b_mant_raw};
    assign b_is_nan = b_is_nan_raw;
    assign b_is_inf = b_is_inf_raw;
    assign b_is_zero = b_is_zero_raw;

endmodule