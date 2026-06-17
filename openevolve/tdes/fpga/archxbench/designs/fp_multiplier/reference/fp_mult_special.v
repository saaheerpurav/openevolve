`timescale 1ns/1ps
// IEEE-754 special-case handler for floating_point_multiplier. Combinational.
// Handles: NaN, Inf×0=NaN, Inf×normal=Inf, 0×x=0, sign XOR.
module fp_mult_special #(parameter EXP_WIDTH=8, MANT_WIDTH=23) (
    input  [EXP_WIDTH+MANT_WIDTH:0] a,
    input  [EXP_WIDTH+MANT_WIDTH:0] b,
    output             is_special,
    output reg [EXP_WIDTH+MANT_WIDTH:0] special_result,
    output reg [2:0]   special_flags   // [2]=invalid,[1]=overflow,[0]=underflow
);
    localparam WIDTH = EXP_WIDTH + MANT_WIDTH + 1;
    wire sa = a[WIDTH-1], sb = b[WIDTH-1];
    wire [EXP_WIDTH-1:0]  ea = a[WIDTH-2:MANT_WIDTH];
    wire [MANT_WIDTH-1:0] ma = a[MANT_WIDTH-1:0];
    wire [EXP_WIDTH-1:0]  eb = b[WIDTH-2:MANT_WIDTH];
    wire [MANT_WIDTH-1:0] mb = b[MANT_WIDTH-1:0];

    wire a_nan  = (ea == {EXP_WIDTH{1'b1}}) && (ma != 0);
    wire b_nan  = (eb == {EXP_WIDTH{1'b1}}) && (mb != 0);
    wire a_inf  = (ea == {EXP_WIDTH{1'b1}}) && (ma == 0);
    wire b_inf  = (eb == {EXP_WIDTH{1'b1}}) && (mb == 0);
    wire a_zero = (ea == 0) && (ma == 0);
    wire b_zero = (eb == 0) && (mb == 0);

    wire res_sign = sa ^ sb;

    assign is_special = a_nan | b_nan | a_inf | b_inf | a_zero | b_zero;

    always @(*) begin
        special_result = 32'h7FC00000;
        special_flags  = 3'b000;

        if (a_nan || b_nan) begin
            // NaN propagation — result is quiet NaN, invalid flag
            special_result = {1'b0, {EXP_WIDTH{1'b1}}, 1'b1, {(MANT_WIDTH-1){1'b0}}};
            special_flags  = 3'b100;
        end else if ((a_inf && b_zero) || (a_zero && b_inf)) begin
            // Inf × 0 = NaN (invalid)
            special_result = {1'b0, {EXP_WIDTH{1'b1}}, 1'b1, {(MANT_WIDTH-1){1'b0}}};
            special_flags  = 3'b100;
        end else if (a_inf || b_inf) begin
            // Inf × normal = ±Inf
            special_result = {res_sign, {EXP_WIDTH{1'b1}}, {MANT_WIDTH{1'b0}}};
            special_flags  = 3'b010;   // overflow flag for infinity result
        end else if (a_zero || b_zero) begin
            // 0 × x = ±0
            special_result = {res_sign, {(WIDTH-1){1'b0}}};
            special_flags  = 3'b001;   // underflow/inexact for zero result
        end
    end
endmodule
