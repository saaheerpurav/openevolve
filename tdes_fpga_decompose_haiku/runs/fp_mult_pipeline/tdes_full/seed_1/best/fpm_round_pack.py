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
    reg [22:0] rounded_frac;
    reg [9:0]  rounded_exp;
    reg        round_up;
    
    always @(*) begin
        overflow = 0;
        underflow = 0;
        
        // Determine if we should round up
        // Round to nearest, ties to even
        round_up = guard && (sticky || norm_frac[0]);
        
        // Perform rounding
        if (round_up) begin
            rounded_frac = norm_frac + 1;
            // Check if rounding caused overflow in fraction (all bits became 0)
            if (rounded_frac == 0) begin
                rounded_exp = norm_exp + 1;
            end else begin
                rounded_exp = norm_exp;
            end
        end else begin
            rounded_frac = norm_frac;
            rounded_exp = norm_exp;
        end
        
        // Check for underflow (exponent <= 0, including negative exponents)
        if (rounded_exp == 0 || rounded_exp[9] == 1) begin
            underflow = 1;
            result = {sign, 31'h0};  // Zero
        end
        // Check for overflow (exponent >= 255)
        else if (rounded_exp >= 255) begin
            overflow = 1;
            result = {sign, 8'hFF, 23'h0};  // Infinity
        end
        // Normal case
        else begin
            result = {sign, rounded_exp[7:0], rounded_frac};
        end
    end
endmodule