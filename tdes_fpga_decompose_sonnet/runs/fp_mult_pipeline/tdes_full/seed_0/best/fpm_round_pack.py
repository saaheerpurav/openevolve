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
    
    // Round to nearest even
    assign round_up = guard & (sticky | norm_frac[0]);
    
    // Add rounding bit to fraction
    assign frac_rounded = {1'b0, norm_frac} + {23'b0, round_up};
    
    // frac_rounded[23] indicates carry (fraction was 1.111...1 and rounded up)
    
    always @(*) begin
        overflow  = 1'b0;
        underflow = 1'b0;
        result    = 32'b0;
        
        if (norm_exp[9] == 1'b1) begin
            // Negative exponent (underflow/denorm) - return zero
            underflow = 1'b1;
            result = {sign, 31'b0};
        end else if (norm_exp >= 10'd255) begin
            // Overflow: return infinity
            overflow = 1'b1;
            result = {sign, 8'hFF, 23'h0};
        end else if (norm_exp == 10'd0) begin
            // Zero exponent - underflow
            underflow = 1'b1;
            result = {sign, 31'b0};
        end else begin
            // Normal case: apply rounding
            if (frac_rounded[23]) begin
                // Fraction overflowed, increment exponent
                if (norm_exp + 10'd1 >= 10'd255) begin
                    overflow = 1'b1;
                    result = {sign, 8'hFF, 23'h0};
                end else begin
                    result = {sign, norm_exp[7:0] + 8'd1, 23'h0};
                end
            end else begin
                result = {sign, norm_exp[7:0], frac_rounded[22:0]};
            end
        end
    end

endmodule