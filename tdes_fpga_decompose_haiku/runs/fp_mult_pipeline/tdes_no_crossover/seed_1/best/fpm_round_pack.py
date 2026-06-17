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
    always @(*) begin
        overflow = 0;
        underflow = 0;
        result = 0;
        
        // Check for underflow (exponent is 0)
        if (norm_exp == 10'd0) begin
            underflow = 1;
            result = {sign, 31'b0};  // Return signed zero
        end
        // Check for overflow (exponent is 255 or more)
        else if (norm_exp >= 10'd255) begin
            overflow = 1;
            // Return signed infinity
            result = {sign, 8'b11111111, 23'b0};
        end
        else begin
            // Normal case: pack the number
            reg [22:0] frac_to_pack;
            reg [8:0] exp_to_pack;
            
            // Determine if we should round up
            reg round_up;
            round_up = 0;
            
            if (guard == 1) begin
                // Guard bit is 1
                if (sticky == 1) begin
                    // guard=1, sticky=1: always round up
                    round_up = 1;
                end
                else begin
                    // guard=1, sticky=0: round up only if LSB is 1 (banker's rounding)
                    round_up = norm_frac[0];
                end
            end
            
            // Apply rounding
            if (round_up) begin
                frac_to_pack = norm_frac + 23'd1;
                // Check if fraction overflowed (all 1s became 0s + carry)
                if (frac_to_pack == 23'd0) begin
                    // Fraction overflowed, increment exponent
                    exp_to_pack = norm_exp[8:0] + 9'd1;
                end
                else begin
                    exp_to_pack = norm_exp[8:0];
                end
            end
            else begin
                frac_to_pack = norm_frac;
                exp_to_pack = norm_exp[8:0];
            end
            
            // Pack into IEEE 754 format
            result = {sign, exp_to_pack, frac_to_pack};
        end
    end
endmodule