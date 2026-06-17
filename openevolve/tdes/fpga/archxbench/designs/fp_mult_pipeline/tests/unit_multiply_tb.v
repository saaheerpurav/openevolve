`timescale 1ns/1ps
module tb;
    reg         a_sign, b_sign;
    reg  [7:0]  a_exp, b_exp;
    reg  [23:0] a_mant, b_mant;
    wire        result_sign;
    wire [47:0] product;
    wire [9:0]  raw_exp;

    fpm_multiply dut(
        .a_sign(a_sign), .a_exp(a_exp), .a_mant(a_mant),
        .b_sign(b_sign), .b_exp(b_exp), .b_mant(b_mant),
        .result_sign(result_sign), .product(product), .raw_exp(raw_exp)
    );

    initial begin
        // 1.0 * 1.0: sign=0^0=0, product=800000*800000=400000000000, exp=127+127-127=127
        a_sign=0; a_exp=127; a_mant=24'h800000;
        b_sign=0; b_exp=127; b_mant=24'h800000; #10;
        if (result_sign===1'b0 && product===48'h400000000000 && raw_exp===10'd127)
            $display("TDES_PASS: test_id=mult_1x1");
        else
            $display("TDES_FAIL: test_id=mult_1x1 | input=1.0*1.0 | expected=s0,p=400000000000,e=127 | got=s%b,p=%h,e=%0d", result_sign, product, raw_exp);

        // 1.5 * 2.0: sign=0, product=C00000*800000=600000000000, exp=127+128-127=128
        a_sign=0; a_exp=127; a_mant=24'hC00000;
        b_sign=0; b_exp=128; b_mant=24'h800000; #10;
        if (result_sign===1'b0 && product===48'h600000000000 && raw_exp===10'd128)
            $display("TDES_PASS: test_id=mult_1p5x2");
        else
            $display("TDES_FAIL: test_id=mult_1p5x2 | input=1.5*2.0 | expected=s0,p=600000000000,e=128 | got=s%b,p=%h,e=%0d", result_sign, product, raw_exp);

        // -1.0 * 1.0: sign=1^0=1
        a_sign=1; a_exp=127; a_mant=24'h800000;
        b_sign=0; b_exp=127; b_mant=24'h800000; #10;
        if (result_sign===1'b1)
            $display("TDES_PASS: test_id=mult_neg_sign");
        else
            $display("TDES_FAIL: test_id=mult_neg_sign | input=-1.0*1.0 | expected=s1 | got=s%b", result_sign);

        // -1.0 * -1.0: sign=1^1=0
        a_sign=1; a_exp=127; a_mant=24'h800000;
        b_sign=1; b_exp=127; b_mant=24'h800000; #10;
        if (result_sign===1'b0)
            $display("TDES_PASS: test_id=mult_neg_neg");
        else
            $display("TDES_FAIL: test_id=mult_neg_neg | input=-1.0*-1.0 | expected=s0 | got=s%b", result_sign);

        // 2.0 * 3.0: product=800000*C00000=600000000000, exp=128+128-127=129
        a_sign=0; a_exp=128; a_mant=24'h800000;
        b_sign=0; b_exp=128; b_mant=24'hC00000; #10;
        if (product===48'h600000000000 && raw_exp===10'd129)
            $display("TDES_PASS: test_id=mult_2x3");
        else
            $display("TDES_FAIL: test_id=mult_2x3 | input=2.0*3.0 | expected=p=600000000000,e=129 | got=p=%h,e=%0d", product, raw_exp);

        // large exponents: exp=254+254-127=381 (overflow territory, but multiply is just arithmetic)
        a_sign=0; a_exp=254; a_mant=24'h800000;
        b_sign=0; b_exp=254; b_mant=24'h800000; #10;
        if (raw_exp===10'd381)
            $display("TDES_PASS: test_id=mult_large_exp");
        else
            $display("TDES_FAIL: test_id=mult_large_exp | input=e254*e254 | expected=e=381 | got=e=%0d", raw_exp);

        $finish;
    end
    initial begin #5000; $display("TDES_FAIL: test_id=mult_timeout | input=timeout | expected=done | got=hang"); $finish; end
endmodule
