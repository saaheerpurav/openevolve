`timescale 1ns/1ps
module tb;
    reg  [47:0] product;
    reg  [9:0]  raw_exp;
    wire [22:0] norm_frac;
    wire [9:0]  norm_exp;
    wire        guard, sticky;

    fpm_normalize dut(
        .product(product), .raw_exp(raw_exp),
        .norm_frac(norm_frac), .norm_exp(norm_exp),
        .guard(guard), .sticky(sticky)
    );

    initial begin
        // product from 1.0*1.0 = 48'h400000000000 (bit47=0, bit46=1)
        // shifted<<1 = 48'h800000000000; frac=[46:24]=0, exp=127
        product = 48'h400000000000; raw_exp = 10'd127; #10;
        if (norm_frac===23'd0 && norm_exp===10'd127 && guard===1'b0 && sticky===1'b0)
            $display("TDES_PASS: test_id=norm_1x1");
        else
            $display("TDES_FAIL: test_id=norm_1x1 | input=400000000000,e127 | expected=f0,e127,g0,s0 | got=f%h,e%0d,g%b,s%b", norm_frac, norm_exp, guard, sticky);

        // product from 1.5*2.0 = 48'h600000000000 (bit47=0, bit46=1,bit45=1)
        // shifted<<1 = 48'hC00000000000; frac=[46:24]=23'h400000, exp=128
        product = 48'h600000000000; raw_exp = 10'd128; #10;
        if (norm_frac===23'h400000 && norm_exp===10'd128)
            $display("TDES_PASS: test_id=norm_1p5x2");
        else
            $display("TDES_FAIL: test_id=norm_1p5x2 | input=600000000000,e128 | expected=f400000,e128 | got=f%h,e%0d", norm_frac, norm_exp);

        // product with bit47=1 (needs right-shift, exp+1)
        // 48'hC00000000000: bit47=1 → no shift, frac=[46:24], exp=raw+1
        product = 48'hC00000000000; raw_exp = 10'd128; #10;
        if (norm_exp===10'd129)
            $display("TDES_PASS: test_id=norm_msb_set");
        else
            $display("TDES_FAIL: test_id=norm_msb_set | input=C00000000000,e128 | expected=e129 | got=e%0d", norm_exp);

        // guard and sticky bits: product where product[22]=1 and product[21:0]!=0
        // 48'h400000400001 → shifted<<1 = 48'h800000800002
        // shifted[23]=product[22]=1 → guard=1; shifted[22:0]=product[21:0]=1 → sticky=1
        product = 48'h400000400001; raw_exp = 10'd127; #10;
        if (guard===1'b1 && sticky===1'b1)
            $display("TDES_PASS: test_id=norm_guard_sticky");
        else
            $display("TDES_FAIL: test_id=norm_guard_sticky | input=400000400001 | expected=g1,s1 | got=g%b,s%b", guard, sticky);

        // guard=1, sticky=0: product with exactly bit 23 set after shift
        // 48'h400000400000 → shifted<<1 = 48'h800000800000
        // shifted[23]=1, shifted[22:0]=0
        product = 48'h400000400000; raw_exp = 10'd127; #10;
        if (guard===1'b1 && sticky===1'b0)
            $display("TDES_PASS: test_id=norm_guard_only");
        else
            $display("TDES_FAIL: test_id=norm_guard_only | input=400000400000 | expected=g1,s0 | got=g%b,s%b", guard, sticky);

        $finish;
    end
    initial begin #5000; $display("TDES_FAIL: test_id=norm_timeout | input=timeout | expected=done | got=hang"); $finish; end
endmodule
