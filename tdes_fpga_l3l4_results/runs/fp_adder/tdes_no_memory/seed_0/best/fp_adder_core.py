`timescale 1ns/1ps
// SEED SKELETON — fp_adder_core
// Ports are correct; logic intentionally empty (outputs 0).
module fp_adder_core #(parameter WIDTH = 32) (
    input  [WIDTH-1:0] a,
    input  [WIDTH-1:0] b,
    input  [2:0]       rnd_mode,
    output reg [WIDTH-1:0] result,
    output reg [2:0]   flags
);
    // TODO: implement IEEE-754 single-precision FP addition
    always @(*) begin
        result = {WIDTH{1'b0}};
        flags  = 3'b000;
    end
endmodule
