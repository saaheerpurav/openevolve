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
    wire [9:0]  exp_after_round;
    wire [22:0] frac_final;
    
    // Round to nearest, ties to even
    assign round_up = guard & (sticky | norm_frac[0]);
    
    // Add round bit to fraction (24-bit to catch carry)
    assign frac_rounded = {1'b0, norm_frac} + {{23{1'b0}}, round_up};
    
    // If rounding caused carry, increment exponent and shift fraction
    assign exp_after_round = frac_rounded[23] ? (norm_exp + 10'd1) : norm_exp;
    assign frac_final = frac_rounded[23] ? frac_rounded[23:1] : frac_rounded[22:0];
    
    always @(*) begin
        overflow  = 1'b0;
        underflow = 1'b0;
        result    = 32'b0;
        
        // norm_exp is treated as signed-extended: values >= 512 (bit[9]=1) are negative -> underflow
        // values 0 also signal underflow from upstream
        if (norm_exp == 10'd0 || norm_exp[9] == 1'b1) begin
            // Underflow: return zero
            underflow = 1'b1;
            result    = 32'b0;
        end else if (norm_exp >= 10'd255) begin
            // Overflow: return +/-Infinity
            overflow = 1'b1;
            result   = {sign, 8'hFF, 23'h0};
        end else begin
            // Check after rounding
            if (exp_after_round >= 10'd255) begin
                overflow = 1'b1;
                result   = {sign, 8'hFF, 23'h0};
            end else if (exp_after_round == 10'd0 || exp_after_round[9] == 1'b1) begin
                underflow = 1'b1;
                result    = 32'b0;
            end else begin
                result = {sign, exp_after_round[7:0], frac_final};
            end
        end
    end
endmodule