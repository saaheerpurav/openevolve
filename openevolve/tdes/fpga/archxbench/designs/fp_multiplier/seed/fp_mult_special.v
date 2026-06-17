`timescale 1ns/1ps
module fp_mult_special #(parameter EXP_WIDTH=8, MANT_WIDTH=23) (
    input  [EXP_WIDTH+MANT_WIDTH:0] a,
    input  [EXP_WIDTH+MANT_WIDTH:0] b,
    output             is_special,
    output reg [EXP_WIDTH+MANT_WIDTH:0] special_result,
    output reg [2:0]   special_flags
);
    assign is_special = 1'b0;
    always @(*) begin special_result = 0; special_flags = 3'b000; end
endmodule
