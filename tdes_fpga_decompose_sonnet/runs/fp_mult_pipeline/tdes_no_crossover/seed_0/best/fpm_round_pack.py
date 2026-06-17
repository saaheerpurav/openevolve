`timescale 1ns/1ps
module fpm_round_pack(
    input         sign,
    input  [22:0] norm_frac,
    input  [9:0]  norm_exp,
    input         guard,
    input         sticky,
    output reg [31:0] result,
    output reg        overflow,
    output reg        underflow
);
    wire round_up;
    wire [23:0] frac_rounded;
    wire [8:0]  exp_after_round;
    
    assign round_up = guard & (sticky | norm_frac[0]);
    assign frac_rounded = {1'b0, norm_frac} + {23'b0, round_up};
    // If frac_rounded[23] set, mantissa overflowed, increment exponent
    wire [7:0] exp_inc;
    wire [22:0] frac_final;
    assign exp_inc = frac_rounded[23] ? (norm_exp[7:0] + 8'd1) : norm_exp[7:0];
    assign frac_final = frac_rounded[23] ? frac_rounded[22:0] : frac_rounded[22:0];
    // Actually frac_rounded[22:0] is the same either way for the fraction bits
    // When frac_rounded[23]=1, the result is 1.0...0 shifted, so frac = 0
    wire [22:0] frac_out;
    assign frac_out = frac_rounded[23] ? 23'b0 : frac_rounded[22:0];
    wire [7:0] exp_out;
    assign exp_out = frac_rounded[23] ? (norm_exp[7:0] + 8'd1) : norm_exp[7:0];

    always @(*) begin
        overflow  = 0;
        underflow = 0;
        result    = 0;
        
        if (norm_exp == 10'd0 || (norm_exp[9] == 1'b1)) begin
            // underflow or negative exponent
            underflow = 1;
            result    = 0;
        end else if (norm_exp >= 10'd255) begin
            // overflow
            overflow = 1;
            result   = {sign, 8'hFF, 23'h0};
        end else begin
            // Normal: pack result
            result = {sign, exp_out, frac_out};
        end
    end
endmodule