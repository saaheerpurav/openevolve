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
    wire [22:0] rounded_frac;
    wire [9:0]  rounded_exp;
    wire        round_up;
    
    // Determine if we should round up
    // Round to nearest, ties to even:
    // - Round up if guard=1 and (sticky=1 or frac[0]=1)
    assign round_up = guard & (sticky | norm_frac[0]);
    
    // Add rounding bit to fraction
    wire [23:0] frac_plus_round = {1'b0, norm_frac} + (round_up ? 24'b1 : 24'b0);
    
    // Check if rounding caused overflow in fraction (fraction became 1.0)
    wire frac_overflow = frac_plus_round[23];
    
    // If fraction overflowed, increment exponent and clear fraction
    assign rounded_frac = frac_overflow ? 23'b0 : frac_plus_round[22:0];
    assign rounded_exp = frac_overflow ? (norm_exp + 1'b1) : norm_exp;
    
    always @(*) begin
        overflow = 1'b0;
        underflow = 1'b0;
        
        // Check for special cases
        if (rounded_exp >= 10'd255) begin
            // Overflow to infinity
            overflow = 1'b1;
            result = {sign, 8'b11111111, 23'b0};
        end
        else if (rounded_exp == 10'b0) begin
            // Underflow to zero
            underflow = 1'b1;
            result = {sign, 31'b0};
        end
        else begin
            // Normal case: pack into IEEE 754 format
            result = {sign, rounded_exp[7:0], rounded_frac};
        end
    end
endmodule