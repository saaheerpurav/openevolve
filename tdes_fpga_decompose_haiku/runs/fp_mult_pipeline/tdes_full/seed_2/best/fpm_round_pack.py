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
        
        // Check for special cases
        if (norm_exp == 10'd0) begin
            // Underflow: exponent is 0
            underflow = 1;
            result = {sign, 31'd0};  // Return signed zero
        end
        else if (norm_exp >= 10'd255) begin
            // Overflow: exponent is 255 or greater
            overflow = 1;
            // Return signed infinity
            result = {sign, 8'b11111111, 23'd0};
        end
        else begin
            // Normal case: pack the number
            // We need to handle rounding with the implicit leading 1
            reg [23:0] mantissa_with_implicit;
            reg [23:0] rounded_mantissa;
            reg [9:0] rounded_exp;
            
            mantissa_with_implicit = {1'b1, norm_frac};  // Add implicit leading 1
            rounded_mantissa = mantissa_with_implicit;
            rounded_exp = norm_exp;
            
            // Rounding logic (round to nearest, ties to even)
            // Round up if guard=1 and (sticky=1 or lsb=1)
            if (guard & (sticky | mantissa_with_implicit[0])) begin
                rounded_mantissa = mantissa_with_implicit + 1;
                // Check if mantissa overflowed (24-bit overflow)
                if (rounded_mantissa[23] == 1'b0) begin
                    // Mantissa overflowed past 24 bits, increment exponent
                    rounded_exp = norm_exp + 1;
                    // Check if this caused overflow to exponent 255
                    if (rounded_exp >= 10'd255) begin
                        overflow = 1;
                        result = {sign, 8'b11111111, 23'd0};  // Return infinity
                    end
                    else begin
                        // After overflow, mantissa is 1.0, so frac is all 0s
                        result = {sign, rounded_exp[7:0], 23'd0};
                    end
                end
                else begin
                    // Normal case: use the lower 23 bits as fraction
                    result = {sign, rounded_exp[7:0], rounded_mantissa[22:0]};
                end
            end
            else begin
                result = {sign, rounded_exp[7:0], norm_frac};
            end
        end
    end
    
endmodule