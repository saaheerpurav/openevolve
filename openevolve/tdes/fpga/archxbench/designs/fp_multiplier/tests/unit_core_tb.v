`timescale 1ns/1ps
// TDES UNIT testbench for fp_mult_core (combinational, normal operands only)
module tb;
    reg  [31:0] a, b;
    wire [31:0] result;
    wire [2:0]  flags;
    integer     fails;

    fp_mult_core #(.EXP_WIDTH(8), .MANT_WIDTH(23)) dut (
        .a(a), .b(b), .product(result), .flags(flags)
    );

    task check;
        input [255:0] tid;
        input [31:0] exp_result;
        input [2:0]  exp_flags;
        begin
            #10;
            if (result === exp_result && flags === exp_flags) begin
                $display("TDES_PASS: test_id=%0s", tid);
            end else begin
                $display("TDES_FAIL: test_id=%0s | input=a=%h,b=%h | expected=%h flags=%0b | got=%h flags=%0b",
                    tid, a, b, exp_result, exp_flags, result, flags);
                fails = fails + 1;
            end
        end
    endtask

    initial begin
        fails = 0;
        // 1.5 × 2.0 = 3.0
        a=32'h3FC00000; b=32'h40000000;
        check("mcore_1p5x2", 32'h40400000, 3'b000);
        // -2.5 × -0.5 = 1.25
        a=32'hC0200000; b=32'hBF000000;
        check("mcore_negxneg", 32'h3FA00000, 3'b000);
        // 1.0 × 1.0 = 1.0
        a=32'h3F800000; b=32'h3F800000;
        check("mcore_1x1", 32'h3F800000, 3'b000);
        // -1.0 × -1.0 = +1.0
        a=32'hBF800000; b=32'hBF800000;
        check("mcore_neg1xneg1", 32'h3F800000, 3'b000);
        // 2.0 × 3.0 = 6.0
        a=32'h40000000; b=32'h40400000;
        check("mcore_2x3", 32'h40C00000, 3'b000);
        // MAX_NORMAL × 2.0 = Inf (overflow)
        a=32'h7F7FFFFF; b=32'h40000000;
        check("mcore_overflow", 32'h7F800000, 3'b010);
        // MIN_DENORM × MIN_DENORM = 0 (flush-to-zero underflow)
        a=32'h00000001; b=32'h00000002;
        check("mcore_underflow", 32'h00000000, 3'b001);
        $finish;
    end
    initial begin #5000; $display("TDES_FAIL: test_id=mcore_timeout | input=timeout | expected=completion | got=timeout"); $finish; end
endmodule
