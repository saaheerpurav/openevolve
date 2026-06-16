`timescale 1ns/1ps
// TDES UNIT testbench for fp_mult_special (combinational)
module tb;
    reg  [31:0] a, b;
    wire        is_special;
    wire [31:0] sp_result;
    wire [2:0]  sp_flags;
    integer     fails;

    fp_mult_special #(.EXP_WIDTH(8), .MANT_WIDTH(23)) dut (
        .a(a), .b(b),
        .is_special(is_special),
        .special_result(sp_result),
        .special_flags(sp_flags)
    );

    task check;
        input [255:0] tid;
        input [31:0] exp_is_sp;
        input [31:0] exp_result;
        input [2:0]  exp_flags;
        begin
            #10;
            if (is_special === exp_is_sp[0]
                && (!exp_is_sp[0] || (sp_result === exp_result && sp_flags === exp_flags))) begin
                $display("TDES_PASS: test_id=%0s", tid);
            end else begin
                $display("TDES_FAIL: test_id=%0s | input=a=%h,b=%h | expected=is_sp=%0b res=%h flags=%0b | got=is_sp=%0b res=%h flags=%0b",
                    tid, a, b, exp_is_sp[0], exp_result, exp_flags,
                    is_special, sp_result, sp_flags);
                fails = fails + 1;
            end
        end
    endtask

    initial begin
        fails = 0;
        // 0 × 0 → special: 0, flags=001
        a=32'h00000000; b=32'h00000000;
        check("mspec_zero_times_zero", 1, 32'h00000000, 3'b001);
        // 0 × 1.0 → special: 0, flags=001
        a=32'h00000000; b=32'h3F800000;
        check("mspec_zero_times_one", 1, 32'h00000000, 3'b001);
        // +Inf × 1.0 → special: +Inf, flags=010
        a=32'h7F800000; b=32'h3F800000;
        check("mspec_inf_times_one", 1, 32'h7F800000, 3'b010);
        // +Inf × 0 → special: NaN, flags=100
        a=32'h7F800000; b=32'h00000000;
        check("mspec_inf_times_zero", 1, 32'h7FC00000, 3'b100);
        // NaN × 1.0 → special: NaN, flags=100
        a=32'h7FC00000; b=32'h3F800000;
        check("mspec_nan_propagate", 1, 32'h7FC00000, 3'b100);
        // -Inf × -Inf → special: +Inf, flags=010
        a=32'hFF800000; b=32'hFF800000;
        check("mspec_neg_inf_sq", 1, 32'h7F800000, 3'b010);
        // Normal × Normal → NOT special
        a=32'h3FC00000; b=32'h40000000;
        check("mspec_normal_not_special", 0, 32'h0, 3'b000);
        $finish;
    end
    initial begin #5000; $display("TDES_FAIL: test_id=mspec_timeout | input=timeout | expected=completion | got=timeout"); $finish; end
endmodule
