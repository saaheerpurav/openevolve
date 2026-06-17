`timescale 1ns/1ps
// Round-to-nearest-even and pack into IEEE-754.  Combinational.
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
    wire round_up = guard & (sticky | norm_frac[0]);
    wire [23:0] frac_rounded = {1'b0, norm_frac} + {23'd0, round_up};
    wire carry = frac_rounded[23];
    wire [22:0] frac_final = carry ? 23'd0 : frac_rounded[22:0];
    wire [9:0]  exp_final  = norm_exp + {9'd0, carry};

    always @(*) begin
        overflow  = 1'b0;
        underflow = 1'b0;
        if ($signed(exp_final) >= 255) begin
            overflow = 1'b1;
            result = {sign, 8'hFF, 23'd0};
        end else if (exp_final[9] || exp_final == 10'd0) begin
            underflow = 1'b1;
            result = {sign, 31'd0};
        end else begin
            result = {sign, exp_final[7:0], frac_final};
        end
    end
endmodule
