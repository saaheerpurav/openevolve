`timescale 1ns/1ps
// TDES UNIT testbench for fp_special_case (combinational — no clock)
// Tests: NaN detection, Inf propagation, zero identity, ±0 rounding
module tb;
    reg  [31:0] a, b;
    reg  [2:0]  rnd_mode;
    wire        is_special;
    wire [31:0] sp_result;
    wire [2:0]  sp_flags;
    integer     fails;

    fp_special_case #(.WIDTH(32)) dut (
        .a(a), .b(b), .rnd_mode(rnd_mode),
        .is_special(is_special),
        .special_result(sp_result),
        .special_flags(sp_flags)
    );

    task check;
        input [255:0] tid;
        input [31:0] exp_is_sp_ext; // 1-bit in lsb
        input [31:0] exp_result;
        input [2:0]  exp_flags;
        begin
            #10;
            if (is_special === exp_is_sp_ext[0]
                && (!exp_is_sp_ext[0] || (sp_result === exp_result && sp_flags === exp_flags))) begin
                $display("TDES_PASS: test_id=%0s", tid);
            end else begin
                $display("TDES_FAIL: test_id=%0s | input=a=%h,b=%h,rnd=%0b | expected=is_sp=%0b res=%h flags=%0b | got=is_sp=%0b res=%h flags=%0b",
                    tid, a, b, rnd_mode,
                    exp_is_sp_ext[0], exp_result, exp_flags,
                    is_special, sp_result, sp_flags);
                fails = fails + 1;
            end
        end
    endtask

    initial begin
        fails = 0;
        rnd_mode = 3'b000;

        // NaN input → is_special, result=7FC00000, flags=100
        a = 32'h7FC00000; b = 32'h3F800000; rnd_mode = 0;
        check("special_nan_a", 1, 32'h7FC00000, 3'b100);

        a = 32'h3F800000; b = 32'h7FC00000; rnd_mode = 0;
        check("special_nan_b", 1, 32'h7FC00000, 3'b100);

        // +Inf + -Inf = NaN
        a = 32'h7F800000; b = 32'hFF800000; rnd_mode = 0;
        check("special_inf_sub_inf", 1, 32'h7FC00000, 3'b100);

        a = 32'hFF800000; b = 32'h7F800000; rnd_mode = 0;
        check("special_neg_inf_plus_pos", 1, 32'h7FC00000, 3'b100);

        // +Inf + 1.0 = +Inf
        a = 32'h7F800000; b = 32'h3F800000; rnd_mode = 0;
        check("special_inf_plus_one", 1, 32'h7F800000, 3'b000);

        // -Inf + -Inf = -Inf
        a = 32'hFF800000; b = 32'hFF800000; rnd_mode = 0;
        check("special_neg_inf_sum", 1, 32'hFF800000, 3'b000);

        // +Inf + +Inf = +Inf
        a = 32'h7F800000; b = 32'h7F800000; rnd_mode = 0;
        check("special_pos_inf_sum", 1, 32'h7F800000, 3'b000);

        // 0 + 5.0 = 5.0
        a = 32'h00000000; b = 32'h40A00000; rnd_mode = 0;
        check("special_zero_identity", 1, 32'h40A00000, 3'b000);

        // -0 + 1.0 = 1.0
        a = 32'h80000000; b = 32'h3F800000; rnd_mode = 0;
        check("special_neg_zero_id", 1, 32'h3F800000, 3'b000);

        // +0 + -0 = +0 (RNE)
        a = 32'h00000000; b = 32'h80000000; rnd_mode = 3'b000;
        check("special_zero_rne", 1, 32'h00000000, 3'b000);

        // +0 + -0 = -0 (RTN)
        a = 32'h00000000; b = 32'h80000000; rnd_mode = 3'b011;
        check("special_zero_rtn", 1, 32'h80000000, 3'b000);

        // 1.0 + 2.0 = NOT special
        a = 32'h3F800000; b = 32'h40000000; rnd_mode = 3'b000;
        check("special_normal_not_special", 0, 32'h0, 3'b000);

        $finish;
    end

    initial begin
        #5000;
        $display("TDES_FAIL: test_id=special_timeout | input=timeout | expected=completion | got=timeout");
        $finish;
    end
endmodule
