`timescale 1ns/1ps
module tb;
    reg  [31:0] a, b;
    wire        a_sign, b_sign;
    wire [7:0]  a_exp, b_exp;
    wire [23:0] a_mant, b_mant;
    wire a_is_nan, a_is_inf, a_is_zero;
    wire b_is_nan, b_is_inf, b_is_zero;

    fpm_unpack dut(
        .a(a), .b(b),
        .a_sign(a_sign), .a_exp(a_exp), .a_mant(a_mant),
        .b_sign(b_sign), .b_exp(b_exp), .b_mant(b_mant),
        .a_is_nan(a_is_nan), .a_is_inf(a_is_inf), .a_is_zero(a_is_zero),
        .b_is_nan(b_is_nan), .b_is_inf(b_is_inf), .b_is_zero(b_is_zero)
    );

    initial begin
        // 1.0 → sign=0, exp=127, mant=24'h800000
        a = 32'h3F800000; b = 32'h00000000; #10;
        if (a_sign===1'b0 && a_exp===8'd127 && a_mant===24'h800000)
            $display("TDES_PASS: test_id=unpack_normal_pos");
        else
            $display("TDES_FAIL: test_id=unpack_normal_pos | input=a=3F800000 | expected=s0,e127,m800000 | got=s%b,e%0d,m%h", a_sign, a_exp, a_mant);

        // -2.0 → sign=1, exp=128, mant=24'h800000
        a = 32'hC0000000; b = 32'h00000000; #10;
        if (a_sign===1'b1 && a_exp===8'd128 && a_mant===24'h800000)
            $display("TDES_PASS: test_id=unpack_negative");
        else
            $display("TDES_FAIL: test_id=unpack_negative | input=a=C0000000 | expected=s1,e128,m800000 | got=s%b,e%0d,m%h", a_sign, a_exp, a_mant);

        // +0.0 → is_zero=1
        a = 32'h00000000; b = 32'h00000000; #10;
        if (a_is_zero===1'b1 && a_is_nan===1'b0 && a_is_inf===1'b0)
            $display("TDES_PASS: test_id=unpack_zero");
        else
            $display("TDES_FAIL: test_id=unpack_zero | input=a=00000000 | expected=zero=1 | got=z%b,n%b,i%b", a_is_zero, a_is_nan, a_is_inf);

        // NaN → is_nan=1
        a = 32'h7FC00000; b = 32'h00000000; #10;
        if (a_is_nan===1'b1)
            $display("TDES_PASS: test_id=unpack_nan");
        else
            $display("TDES_FAIL: test_id=unpack_nan | input=a=7FC00000 | expected=nan=1 | got=%b", a_is_nan);

        // +Inf → is_inf=1
        a = 32'h7F800000; b = 32'h00000000; #10;
        if (a_is_inf===1'b1 && a_is_nan===1'b0)
            $display("TDES_PASS: test_id=unpack_inf");
        else
            $display("TDES_FAIL: test_id=unpack_inf | input=a=7F800000 | expected=inf=1 | got=i%b,n%b", a_is_inf, a_is_nan);

        // -0.0 → sign=1, is_zero=1
        a = 32'h80000000; b = 32'h00000000; #10;
        if (a_sign===1'b1 && a_is_zero===1'b1)
            $display("TDES_PASS: test_id=unpack_neg_zero");
        else
            $display("TDES_FAIL: test_id=unpack_neg_zero | input=a=80000000 | expected=s1,z1 | got=s%b,z%b", a_sign, a_is_zero);

        // denorm 0x00000001 → exp=0, mant=24'h000001, not zero
        a = 32'h00000001; b = 32'h00000000; #10;
        if (a_exp===8'd0 && a_mant===24'h000001 && a_is_zero===1'b0)
            $display("TDES_PASS: test_id=unpack_denorm");
        else
            $display("TDES_FAIL: test_id=unpack_denorm | input=a=00000001 | expected=e0,m000001,!z | got=e%0d,m%h,z%b", a_exp, a_mant, a_is_zero);

        // verify b-channel: b=NaN
        a = 32'h00000000; b = 32'h7FC00000; #10;
        if (b_is_nan===1'b1)
            $display("TDES_PASS: test_id=unpack_b_nan");
        else
            $display("TDES_FAIL: test_id=unpack_b_nan | input=b=7FC00000 | expected=b_nan=1 | got=%b", b_is_nan);

        $finish;
    end
    initial begin #5000; $display("TDES_FAIL: test_id=unpack_timeout | input=timeout | expected=done | got=hang"); $finish; end
endmodule
