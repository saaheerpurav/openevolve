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
    wire [23:0] rounded_frac;
    wire carry_out;
    wire [10:0] adj_exp;

    // Round-to-nearest-even: round up if guard=1 AND (sticky=1 OR lsb=1)
    assign round_up = guard & (sticky | norm_frac[0]);
    
    // Add rounding increment to fraction
    assign rounded_frac = {1'b0, norm_frac} + {23'b0, round_up};
    
    // Check if rounding caused mantissa overflow (carry out)
    assign carry_out = rounded_frac[23];
    
    // Adjusted exponent after rounding
    assign adj_exp = {1'b0, norm_exp} + {10'b0, carry_out};
    
    always @(*) begin
        overflow  = 1'b0;
        underflow = 1'b0;
        result    = 32'b0;
        
        // Underflow: norm_exp is zero or negative (MSB set in 10-bit signed)
        // norm_exp[9] set means it wrapped negative (two's complement)
        if (norm_exp == 10'b0 || norm_exp[9]) begin
            // Underflow: result is zero
            underflow = 1'b1;
            result = {sign, 31'b0};
        end else if (norm_exp >= 10'd255) begin
            // Overflow: result is +Infinity
            overflow = 1'b1;
            result = {sign, 8'hFF, 23'b0};
        end else begin
            // Normal case: apply rounding
            if (carry_out) begin
                // Rounding caused carry - increment exponent, fraction becomes 0
                if (adj_exp >= 11'd255) begin
                    // Overflow after rounding
                    overflow = 1'b1;
                    result = {sign, 8'hFF, 23'b0};
                end else begin
                    result = {sign, adj_exp[7:0], 23'b0};
                end
            end else begin
                result = {sign, norm_exp[7:0], rounded_frac[22:0]};
            end
        end
    end
    
endmodule