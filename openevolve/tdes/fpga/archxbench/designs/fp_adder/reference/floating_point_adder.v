`timescale 1ns/1ps
// Top-level IEEE-754 FP adder. Integrates fp_special_case + fp_adder_core.
// Output is registered on posedge clk.
module floating_point_adder #(parameter WIDTH = 32) (
    input              clk,
    input              rst,
    input  [WIDTH-1:0] a,
    input  [WIDTH-1:0] b,
    input  [2:0]       rnd_mode,
    output reg [WIDTH-1:0] sum,
    output reg [2:0]   exception_flags
);
    wire              is_special;
    wire [WIDTH-1:0]  sp_result;
    wire [2:0]        sp_flags;
    wire [WIDTH-1:0]  core_result;
    wire [2:0]        core_flags;

    fp_special_case #(.WIDTH(WIDTH)) u_sc (
        .a(a), .b(b), .rnd_mode(rnd_mode),
        .is_special(is_special),
        .special_result(sp_result),
        .special_flags(sp_flags)
    );

    fp_adder_core #(.WIDTH(WIDTH)) u_core (
        .a(a), .b(b), .rnd_mode(rnd_mode),
        .result(core_result),
        .flags(core_flags)
    );

    always @(posedge clk) begin
        if (rst) begin
            sum             <= {WIDTH{1'b0}};
            exception_flags <= 3'b000;
        end else begin
            sum             <= is_special ? sp_result  : core_result;
            exception_flags <= is_special ? sp_flags   : core_flags;
        end
    end
endmodule
