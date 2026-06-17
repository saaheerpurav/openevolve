// full module source
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
    wire [23:0] rounded_frac; // 24 bits to capture carry
    wire [9:0]  adj_exp;
    wire [22:0] final_frac;
    wire [9:0]  final_exp;
    wire        carry;

    // Round to nearest, ties to even
    assign round_up = guard & (sticky | norm_frac[0]);
    
    // Add rounding bit to the 23-bit stored fraction
    assign rounded_frac = {1'b0, norm_frac} + {23'b0, round_up};
    
    assign carry = rounded_frac[23]; // carry out means fraction overflowed
    
    // If carry, fraction becomes 0 and exponent increments
    assign adj_exp = carry ? (norm_exp + 10'd1) : norm_exp;
    assign final_exp = adj_exp;
    assign final_frac = carry ? 23'b0 : rounded_frac[22:0];

    // Treat norm_exp as signed 10-bit to detect negative (underflow) exponents
    wire signed [9:0] norm_exp_signed;
    assign norm_exp_signed = $signed(norm_exp);
    
    wire signed [9:0] final_exp_signed;
    assign final_exp_signed = $signed(final_exp);

    always @(*) begin
        overflow  = 0;
        underflow = 0;
        result    = 32'b0;
        
        if (norm_exp_signed <= 10'sd0) begin
            // Underflow - exponent is zero or negative, return zero
            underflow = 1;
            result = 32'b0;
        end else if (norm_exp_signed >= 10'sd255) begin
            // Overflow - return infinity
            overflow = 1;
            result = {sign, 8'hFF, 23'h0};
        end else begin
            // Normal case - apply rounding
            if (final_exp_signed >= 10'sd255) begin
                // Rounding caused overflow
                overflow = 1;
                result = {sign, 8'hFF, 23'h0};
            end else if (final_exp_signed <= 10'sd0) begin
                underflow = 1;
                result = 32'b0;
            end else begin
                result = {sign, final_exp[7:0], final_frac};
            end
        end
    end

endmodule