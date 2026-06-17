`timescale 1ns/1ps
module fp_mult_special #(parameter EXP_WIDTH=8, MANT_WIDTH=23) (
    input  [EXP_WIDTH+MANT_WIDTH:0] a,
    input  [EXP_WIDTH+MANT_WIDTH:0] b,
    output             is_special,
    output reg [EXP_WIDTH+MANT_WIDTH:0] special_result,
    output reg [2:0]   special_flags
);
    localparam SIGN_BIT = EXP_WIDTH + MANT_WIDTH;
    localparam EXP_MSB = EXP_WIDTH + MANT_WIDTH - 1;
    localparam EXP_LSB = MANT_WIDTH;
    
    wire [EXP_WIDTH-1:0] exp_a = a[EXP_MSB:EXP_LSB];
    wire [MANT_WIDTH-1:0] mant_a = a[MANT_WIDTH-1:0];
    wire [EXP_WIDTH-1:0] exp_b = b[EXP_MSB:EXP_LSB];
    wire [MANT_WIDTH-1:0] mant_b = b[MANT_WIDTH-1:0];
    
    wire sign_a = a[SIGN_BIT];
    wire sign_b = b[SIGN_BIT];
    
    wire a_is_zero = (exp_a == 0) && (mant_a == 0);
    wire b_is_zero = (exp_b == 0) && (mant_b == 0);
    wire a_is_inf = (exp_a == {EXP_WIDTH{1'b1}}) && (mant_a == 0);
    wire b_is_inf = (exp_b == {EXP_WIDTH{1'b1}}) && (mant_b == 0);
    wire a_is_nan = (exp_a == {EXP_WIDTH{1'b1}}) && (mant_a != 0);
    wire b_is_nan = (exp_b == {EXP_WIDTH{1'b1}}) && (mant_b != 0);
    
    wire result_sign = sign_a ^ sign_b;
    
    // Check for special cases
    wire is_zero_result = a_is_zero || b_is_zero;
    wire is_nan_result = a_is_nan || b_is_nan || (a_is_inf && b_is_zero) || (a_is_zero && b_is_inf);
    wire is_inf_result = (a_is_inf && !b_is_zero) || (b_is_inf && !a_is_zero);
    
    assign is_special = is_zero_result || is_nan_result || is_inf_result;
    
    always @(*) begin
        if (is_nan_result) begin
            // NaN: exponent all 1s, mantissa non-zero
            special_result = {{1'b0}, {EXP_WIDTH{1'b1}}, {1'b1}, {MANT_WIDTH-1{1'b0}}};
            special_flags = 3'b100;  // NaN flag
        end
        else if (is_inf_result) begin
            // Infinity: exponent all 1s, mantissa zero, sign from multiplication
            special_result = {{result_sign}, {EXP_WIDTH{1'b1}}, {MANT_WIDTH{1'b0}}};
            special_flags = 3'b010;  // Infinity flag
        end
        else if (is_zero_result) begin
            // Zero: exponent and mantissa zero, sign from multiplication
            special_result = {{result_sign}, {EXP_WIDTH{1'b0}}, {MANT_WIDTH{1'b0}}};
            special_flags = 3'b001;  // Zero flag
        end
        else begin
            special_result = 0;
            special_flags = 3'b000;
        end
    end
endmodule