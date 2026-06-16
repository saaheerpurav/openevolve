`timescale 1ns/1ps
// IEEE-754 special-case handler for floating_point_adder.
// Purely combinational. Detects NaN, Inf, and zero operands.
// Normal/denormal arithmetic is handled by fp_adder_core.
module fp_special_case #(parameter WIDTH = 32) (
    input  [WIDTH-1:0] a,
    input  [WIDTH-1:0] b,
    input  [2:0]       rnd_mode,
    output             is_special,
    output reg [WIDTH-1:0] special_result,
    output reg [2:0]   special_flags   // [2]=invalid,[1]=overflow,[0]=underflow
);
    wire sa = a[31], sb = b[31];
    wire [7:0]  ea = a[30:23], eb = b[30:23];
    wire [22:0] ma = a[22:0],  mb = b[22:0];

    wire a_nan  = (ea == 8'hFF) && (ma != 23'b0);
    wire b_nan  = (eb == 8'hFF) && (mb != 23'b0);
    wire a_inf  = (ea == 8'hFF) && (ma == 23'b0);
    wire b_inf  = (eb == 8'hFF) && (mb == 23'b0);
    wire a_zero = (ea == 8'h00) && (ma == 23'b0);
    wire b_zero = (eb == 8'h00) && (mb == 23'b0);

    assign is_special = a_nan | b_nan | a_inf | b_inf | a_zero | b_zero;

    always @(*) begin
        special_result = 32'h7FC00000;
        special_flags  = 3'b000;

        if (a_nan || b_nan) begin
            // Any NaN input → quiet NaN, invalid flag
            special_result = 32'h7FC00000;
            special_flags  = 3'b100;
        end else if (a_inf && b_inf && (sa != sb)) begin
            // +Inf + -Inf = NaN (invalid)
            special_result = 32'h7FC00000;
            special_flags  = 3'b100;
        end else if (a_inf) begin
            special_result = a;
            special_flags  = 3'b000;
        end else if (b_inf) begin
            special_result = b;
            special_flags  = 3'b000;
        end else if (a_zero && b_zero) begin
            // ±0 + ±0
            if (sa && sb) begin
                // -0 + -0 = -0
                special_result = 32'h80000000;
            end else if (!sa && !sb) begin
                // +0 + +0 = +0
                special_result = 32'h00000000;
            end else begin
                // +0 + -0: RTN → -0, all others → +0
                special_result = (rnd_mode == 3'b011) ? 32'h80000000 : 32'h00000000;
            end
            special_flags = 3'b000;
        end else if (a_zero) begin
            // 0 + b = b
            special_result = b;
            special_flags  = 3'b000;
        end else if (b_zero) begin
            // a + 0 = a
            special_result = a;
            special_flags  = 3'b000;
        end
    end
endmodule
