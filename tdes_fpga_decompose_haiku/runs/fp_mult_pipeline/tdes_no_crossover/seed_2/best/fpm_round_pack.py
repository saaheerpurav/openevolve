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
        reg [23:0] rounded_frac;
        reg [9:0] final_exp;
        reg should_round_up;
        
        overflow = 0;
        underflow = 0;
        
        // Determine if we should round up
        // Round to nearest even: round up if guard=1 and (sticky=1 or frac[0]=1)
        should_round_up = guard & (sticky | norm_frac[0]);
        
        // Apply rounding to fraction
        rounded_frac = {1'b0, norm_frac};
        if (should_round_up) begin
            rounded_frac = rounded_frac + 1;
        end
        
        // Check if rounding overflowed the fraction (24-bit value becomes 24'h1000000)
        if (rounded_frac[23]) begin
            // Fraction overflowed, increment exponent
            final_exp = norm_exp + 1;
        end else begin
            final_exp = norm_exp;
        end
        
        // Handle special cases
        if (final_exp == 10'h0) begin
            // Underflow: return signed zero
            underflow = 1;
            result = {sign, 31'h0};
        end else if (final_exp >= 10'hFF) begin
            // Overflow: return signed infinity
            overflow = 1;
            result = {sign, 8'hFF, 23'h0};
        end else begin
            // Normal case: pack into IEEE 754 format
            // Sign (1 bit) | Exponent (8 bits) | Fraction (23 bits)
            result = {sign, final_exp[7:0], rounded_frac[22:0]};
        end
    end

endmodule