`timescale 1ns/1ps
module tb;
    reg  a_nan, a_inf, a_zero;
    reg  b_nan, b_inf, b_zero;
    reg  result_sign;
    wire is_special;
    wire [31:0] special_result;

    fpm_special dut(
        .a_is_nan(a_nan), .a_is_inf(a_inf), .a_is_zero(a_zero),
        .b_is_nan(b_nan), .b_is_inf(b_inf), .b_is_zero(b_zero),
        .result_sign(result_sign),
        .is_special(is_special), .special_result(special_result)
    );

    initial begin
        // NaN * anything → NaN (7FC00000)
        a_nan=1; a_inf=0; a_zero=0; b_nan=0; b_inf=0; b_zero=0; result_sign=0; #10;
        if (is_special===1'b1 && special_result===32'h7FC00000)
            $display("TDES_PASS: test_id=spec_nan_prop");
        else
            $display("TDES_FAIL: test_id=spec_nan_prop | input=nan*norm | expected=sp=1,7FC00000 | got=sp%b,%h", is_special, special_result);

        // Inf * 0 → NaN
        a_nan=0; a_inf=1; a_zero=0; b_nan=0; b_inf=0; b_zero=1; result_sign=0; #10;
        if (is_special===1'b1 && special_result===32'h7FC00000)
            $display("TDES_PASS: test_id=spec_inf_x_zero");
        else
            $display("TDES_FAIL: test_id=spec_inf_x_zero | input=inf*0 | expected=NaN | got=sp%b,%h", is_special, special_result);

        // 0 * Inf → NaN
        a_nan=0; a_inf=0; a_zero=1; b_nan=0; b_inf=1; b_zero=0; result_sign=0; #10;
        if (is_special===1'b1 && special_result===32'h7FC00000)
            $display("TDES_PASS: test_id=spec_zero_x_inf");
        else
            $display("TDES_FAIL: test_id=spec_zero_x_inf | input=0*inf | expected=NaN | got=sp%b,%h", is_special, special_result);

        // +Inf * normal → +Inf (7F800000)
        a_nan=0; a_inf=1; a_zero=0; b_nan=0; b_inf=0; b_zero=0; result_sign=0; #10;
        if (is_special===1'b1 && special_result===32'h7F800000)
            $display("TDES_PASS: test_id=spec_inf_result");
        else
            $display("TDES_FAIL: test_id=spec_inf_result | input=inf*norm,s=0 | expected=7F800000 | got=%h", special_result);

        // -Inf * -Inf → +Inf
        a_nan=0; a_inf=1; a_zero=0; b_nan=0; b_inf=1; b_zero=0; result_sign=0; #10;
        if (is_special===1'b1 && special_result===32'h7F800000)
            $display("TDES_PASS: test_id=spec_neg_inf_sq");
        else
            $display("TDES_FAIL: test_id=spec_neg_inf_sq | input=-inf*-inf,s=0 | expected=7F800000 | got=%h", special_result);

        // 0 * normal → signed zero
        a_nan=0; a_inf=0; a_zero=1; b_nan=0; b_inf=0; b_zero=0; result_sign=1; #10;
        if (is_special===1'b1 && special_result===32'h80000000)
            $display("TDES_PASS: test_id=spec_zero_result");
        else
            $display("TDES_FAIL: test_id=spec_zero_result | input=0*norm,s=1 | expected=80000000 | got=%h", special_result);

        // normal * normal → NOT special
        a_nan=0; a_inf=0; a_zero=0; b_nan=0; b_inf=0; b_zero=0; result_sign=0; #10;
        if (is_special===1'b0)
            $display("TDES_PASS: test_id=spec_not_special");
        else
            $display("TDES_FAIL: test_id=spec_not_special | input=norm*norm | expected=sp=0 | got=sp%b", is_special);

        $finish;
    end
    initial begin #5000; $display("TDES_FAIL: test_id=spec_timeout | input=timeout | expected=done | got=hang"); $finish; end
endmodule
