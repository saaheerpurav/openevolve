`timescale 1ns/1ps
// IEEE-754 FP multiplier top. Integrates fp_mult_special + fp_mult_core.
module floating_point_multiplier #(parameter EXP_WIDTH=8, MANT_WIDTH=23) (
    input              clk,
    input              rst,
    input  [EXP_WIDTH+MANT_WIDTH:0] a,
    input  [EXP_WIDTH+MANT_WIDTH:0] b,
    input  [2:0]       rnd_mode,
    output reg [EXP_WIDTH+MANT_WIDTH:0] product,
    output reg [2:0]   exception_flags
);
    localparam WIDTH = EXP_WIDTH + MANT_WIDTH + 1;

    wire              is_special;
    wire [WIDTH-1:0]  sp_result;
    wire [2:0]        sp_flags;
    wire [WIDTH-1:0]  core_result;
    wire [2:0]        core_flags;

    fp_mult_special #(.EXP_WIDTH(EXP_WIDTH), .MANT_WIDTH(MANT_WIDTH)) u_sp (
        .a(a), .b(b),
        .is_special(is_special),
        .special_result(sp_result),
        .special_flags(sp_flags)
    );

    fp_mult_core #(.EXP_WIDTH(EXP_WIDTH), .MANT_WIDTH(MANT_WIDTH)) u_core (
        .a(a), .b(b),
        .product(core_result),
        .flags(core_flags)
    );

    always @(posedge clk) begin
        if (rst) begin
            product          <= {WIDTH{1'b0}};
            exception_flags  <= 3'b000;
        end else begin
            product         <= is_special ? sp_result  : core_result;
            exception_flags <= is_special ? sp_flags   : core_flags;
        end
    end
endmodule
