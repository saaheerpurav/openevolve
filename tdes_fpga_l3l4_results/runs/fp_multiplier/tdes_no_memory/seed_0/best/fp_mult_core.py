`timescale 1ns/1ps
module fp_mult_core #(parameter EXP_WIDTH=8, MANT_WIDTH=23) (
    input  [EXP_WIDTH+MANT_WIDTH:0] a,
    input  [EXP_WIDTH+MANT_WIDTH:0] b,
    output reg [EXP_WIDTH+MANT_WIDTH:0] product,
    output reg [2:0]   flags
);
    always @(*) begin product = 0; flags = 3'b000; end
endmodule
