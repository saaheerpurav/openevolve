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
        reg [22:0] rounded_frac;
        reg [9:0] rounded_exp;
        reg round_bit;
        
        // Determine rounding: round up if (guard & (sticky | frac[0]))
        round_bit = guard & (sticky | norm_frac[0]);
        
        // Add rounding
        if (round_bit) begin
            rounded_frac = norm_frac + 1;
        end else begin
            rounded_frac = norm_frac;
        end
        
        // Handle mantissa overflow from rounding
        rounded_exp = norm_exp;
        if (rounded_frac[22] == 0 && round_bit == 1 && norm_frac == 23'h7FFFFF) begin
            // Mantissa overflowed to 24 bits, need to increment exponent
            rounded_exp = norm_exp + 1;
            rounded_frac = 23'h0;
        end
        
        // Check for underflow and overflow
        underflow = (rounded_exp == 10'd0);
        overflow = (rounded_exp >= 10'd255);
        
        // Pack the result
        if (underflow) begin
            result = {sign, 31'h0};
            overflow = 1'b0;
        end else if (overflow) begin
            result = {sign, 8'hFF, 23'h0};
            underflow = 1'b0;
        end else begin
            result = {sign, rounded_exp[7:0], rounded_frac[22:0]};
            overflow = 1'b0;
            underflow = 1'b0;
        end
    end
    
endmodule