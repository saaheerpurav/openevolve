// full module source
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
    wire [9:0]  exp_adjusted;
    wire [22:0] final_frac;
    wire [9:0]  final_exp;
    
    // Round to nearest even
    // Round up if: guard=1 AND (sticky=1 OR frac[0]=1)
    assign round_up = guard & (sticky | norm_frac[0]);
    
    // Add round bit to fraction
    assign frac_rounded = {1'b0, norm_frac} + {23'b0, round_up};
    
    // If rounding caused overflow of mantissa (bit 23 set), increment exponent
    assign exp_adjusted = norm_exp + (frac_rounded[23] ? 10'd1 : 10'd0);
    
    // Final fraction: if mantissa overflowed due to rounding, shift right (becomes 0)
    assign final_frac = frac_rounded[23] ? frac_rounded[23:1] : frac_rounded[22:0];
    
    // Final exponent
    assign final_exp = exp_adjusted;
    
    always @(*) begin
        overflow  = 0;
        underflow = 0;
        result    = 0;
        
        // norm_exp is 10-bit, may be signed (two's complement)
        // If bit 9 is set, it's a negative exponent => underflow
        if (norm_exp[9]) begin
            // Negative exponent: underflow to zero
            underflow = 1;
            result    = 0;
        end else if (norm_exp == 10'd0) begin
            // Zero exponent: underflow
            underflow = 1;
            result    = 0;
        end else if (norm_exp >= 10'd255) begin
            // Overflow: result is infinity
            overflow = 1;
            result   = {sign, 8'hFF, 23'h0};
        end else begin
            // Check after rounding if exponent overflows
            if (final_exp >= 10'd255) begin
                overflow = 1;
                result   = {sign, 8'hFF, 23'h0};
            end else if (final_exp == 10'd0 || final_exp[9]) begin
                underflow = 1;
                result    = 0;
            end else begin
                result = {sign, final_exp[7:0], final_frac};
            end
        end
    end

endmodule