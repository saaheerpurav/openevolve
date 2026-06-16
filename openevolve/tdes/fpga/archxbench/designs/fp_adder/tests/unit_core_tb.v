`timescale 1ns/1ps
// TDES UNIT testbench for fp_adder_core (combinational — no clock)
// Tests: basic arithmetic, cancellation, overflow, rounding, edge cases
module tb;
    reg  [31:0] a, b;
    reg  [2:0]  rnd_mode;
    wire [31:0] result;
    wire [2:0]  flags;
    integer     fails;

    fp_adder_core #(.WIDTH(32)) dut (
        .a(a), .b(b), .rnd_mode(rnd_mode),
        .result(result), .flags(flags)
    );

    task check;
        input [255:0] tid;
        input [31:0]  exp_result;
        input [2:0]   exp_flags;
        begin
            #10;
            if (result === exp_result && flags === exp_flags) begin
                $display("TDES_PASS: test_id=%0s", tid);
            end else begin
                $display("TDES_FAIL: test_id=%0s | input=a=%h,b=%h,rnd=%0b | expected=%h flags=%0b | got=%h flags=%0b",
                    tid, a, b, rnd_mode, exp_result, exp_flags, result, flags);
                fails = fails + 1;
            end
        end
    endtask

    initial begin
        fails = 0;

        // Basic arithmetic
        a=32'h3F800000; b=32'h40000000; rnd_mode=0; // 1.0 + 2.0 = 3.0
        check("core_basic_1p2", 32'h40400000, 3'b000);

        a=32'h3F800000; b=32'h3F000000; rnd_mode=0; // 1.0 + 0.5 = 1.5
        check("core_basic_halves", 32'h3FC00000, 3'b000);

        a=32'hBFC00000; b=32'hC0200000; rnd_mode=0; // -1.5 + -2.5 = -4.0
        check("core_neg_add", 32'hC0800000, 3'b000);

        a=32'h3F800000; b=32'h3F800000; rnd_mode=0; // 1.0 + 1.0 = 2.0
        check("core_equal", 32'h40000000, 3'b000);

        a=32'h40400000; b=32'h40800000; rnd_mode=0; // 3.0 + 4.0 = 7.0
        check("core_basic_3p4", 32'h40E00000, 3'b000);

        a=32'hC0000000; b=32'h3F800000; rnd_mode=0; // -2.0 + 1.0 = -1.0
        check("core_neg_basic", 32'hBF800000, 3'b000);

        // Cancellation
        a=32'h3F800000; b=32'hBF800000; rnd_mode=0; // 1.0 + (-1.0) = +0
        check("core_cancel_rne", 32'h00000000, 3'b000);

        a=32'h3F800000; b=32'hBF800000; rnd_mode=3; // 1.0 + (-1.0) = -0 (RTN)
        check("core_cancel_rtn", 32'h80000000, 3'b000);

        // Overflow
        a=32'h7F7FFFFF; b=32'h7F7FFFFF; rnd_mode=0; // MAX + MAX = +Inf
        check("core_overflow", 32'h7F800000, 3'b010);

        // Denormal
        a=32'h00400000; b=32'h00400000; rnd_mode=0; // denorm + denorm = normal
        check("core_denorm", 32'h00800000, 3'b001);

        // Rounding modes
        a=32'h3F800000; b=32'h33800000; rnd_mode=2; // RTP: increment
        check("core_round_rtp", 32'h3F800001, 3'b000);

        a=32'hBF800000; b=32'hB3800000; rnd_mode=3; // RTN: neg increment
        check("core_round_rtn_neg", 32'hBF800001, 3'b000);

        a=32'h40400000; b=32'h33800001; rnd_mode=1; // RTZ: truncate
        check("core_round_rtz", 32'h40400000, 3'b000);

        a=32'h3F800000; b=32'h33800000; rnd_mode=0; // RNE: round down (tie down)
        check("core_round_rne_down", 32'h3F800000, 3'b000);

        // Edge cases
        a=32'h00800000; b=32'h00800000; rnd_mode=0; // min_normal + min_normal
        check("core_min_normal", 32'h01000000, 3'b000);

        a=32'h5F000000; b=32'h3F800000; rnd_mode=0; // large exp diff: absorption
        check("core_absorption", 32'h5F000000, 3'b000);

        a=32'h3F800000; b=32'hBF7FFFFF; rnd_mode=0; // near cancellation
        check("core_near_cancel", 32'h33800000, 3'b000);

        $finish;
    end

    initial begin
        #10000;
        $display("TDES_FAIL: test_id=core_timeout | input=timeout | expected=completion | got=timeout");
        $finish;
    end
endmodule
