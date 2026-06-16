`timescale 1ns/1ps
module fp_mult_special #(parameter EXP_WIDTH=8, MANT_WIDTH=23) (
    input  [EXP_WIDTH+MANT_WIDTH:0] a,
    input  [EXP_WIDTH+MANT_WIDTH:0] b,
    output             is_special,
    output reg [EXP_WIDTH+MANT_WIDTH:0] special_result,
    output reg [2:0]   special_flags
);
    localparam WIDTH = EXP_WIDTH + MANT_WIDTH + 1;
    localparam MANT_LSB = 0;
    localparam MANT_MSB = MANT_WIDTH - 1;
    localparam EXP_LSB = MANT_WIDTH;
    localparam EXP_MSB = MANT_WIDTH + EXP_WIDTH - 1;
    localparam SIGN_BIT = MANT_WIDTH + EXP_WIDTH;
    
    wire a_sign = a[SIGN_BIT];
    wire b_sign = b[SIGN_BIT];
    wire [EXP_WIDTH-1:0] a_exp = a[EXP_MSB:EXP_LSB];
    wire [EXP_WIDTH-1:0] b_exp = b[EXP_MSB:EXP_LSB];
    wire [MANT_WIDTH-1:0] a_mant = a[MANT_MSB:MANT_LSB];
    wire [MANT_WIDTH-1:0] b_mant = b[MANT_MSB:MANT_LSB];
    
    wire a_is_zero = (a_exp == 0) && (a_mant == 0);
    wire b_is_zero = (b_exp == 0) && (b_mant == 0);
    wire a_is_inf = (a_exp == {EXP_WIDTH{1'b1}}) && (a_mant == 0);
    wire b_is_inf = (b_exp == {EXP_WIDTH{1'b1}}) && (b_mant == 0);
    wire a_is_nan = (a_exp == {EXP_WIDTH{1'b1}}) && (a_mant != 0);
    wire b_is_nan = (b_exp == {EXP_WIDTH{1'b1}}) && (b_mant != 0);
    
    wire is_special_case = a_is_zero || b_is_zero || a_is_inf || b_is_inf || a_is_nan || b_is_nan;
    
    assign is_special = is_special_case;
    
    always @(*) begin
        special_result = {WIDTH{1'b0}};
        special_flags = 3'b000;
        
        if (is_special_case) begin
            // NaN cases: NaN × anything = NaN, or anything × NaN = NaN
            if (a_is_nan || b_is_nan) begin
                special_result = {{1'b0}, {EXP_WIDTH{1'b1}}, {1'b1}, {MANT_WIDTH-1{1'b0}}};
                special_flags = 3'b100; // NaN flag (bit 2)
            end
            // Inf × 0 = NaN (or 0 × Inf = NaN)
            else if ((a_is_inf && b_is_zero) || (a_is_zero && b_is_inf)) begin
                special_result = {{1'b0}, {EXP_WIDTH{1'b1}}, {1'b1}, {MANT_WIDTH-1{1'b0}}};
                special_flags = 3'b100; // NaN flag (bit 2)
            end
            // Inf × non-zero = Inf (sign depends on operands)
            else if (a_is_inf || b_is_inf) begin
                special_result = {{a_sign ^ b_sign}, {EXP_WIDTH{1'b1}}, {MANT_WIDTH{1'b0}}};
                special_flags = 3'b010; // Inf flag (bit 1)
            end
            // Zero cases: 0 × anything = 0 (sign depends on operands)
            else if (a_is_zero || b_is_zero) begin
                special_result = {{a_sign ^ b_sign}, {EXP_WIDTH{1'b0}}, {MANT_WIDTH{1'b0}}};
                special_flags = 3'b001; // Zero flag (bit 0)
            end
        end
    end
endmodule