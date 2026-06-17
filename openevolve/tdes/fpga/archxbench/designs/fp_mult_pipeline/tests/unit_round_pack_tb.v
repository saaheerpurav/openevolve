`timescale 1ns/1ps
module tb;
    reg         sign;
    reg  [22:0] norm_frac;
    reg  [9:0]  norm_exp;
    reg         guard, sticky;
    wire [31:0] result;
    wire        overflow, underflow;

    fpm_round_pack dut(
        .sign(sign), .norm_frac(norm_frac), .norm_exp(norm_exp),
        .guard(guard), .sticky(sticky),
        .result(result), .overflow(overflow), .underflow(underflow)
    );

    initial begin
        // 1.0: sign=0, frac=0, exp=127, g=0, s=0 → 3F800000
        sign=0; norm_frac=23'd0; norm_exp=10'd127; guard=0; sticky=0; #10;
        if (result===32'h3F800000 && overflow===1'b0 && underflow===1'b0)
            $display("TDES_PASS: test_id=rpack_one");
        else
            $display("TDES_FAIL: test_id=rpack_one | input=s0,f0,e127,g0,s0 | expected=3F800000 | got=%h,ov%b,un%b", result, overflow, underflow);

        // 3.0: sign=0, frac=23'h400000, exp=128 → 40400000
        sign=0; norm_frac=23'h400000; norm_exp=10'd128; guard=0; sticky=0; #10;
        if (result===32'h40400000)
            $display("TDES_PASS: test_id=rpack_three");
        else
            $display("TDES_FAIL: test_id=rpack_three | input=s0,f400000,e128 | expected=40400000 | got=%h", result);

        // negative: -2.0 = sign=1, frac=0, exp=128 → C0000000
        sign=1; norm_frac=23'd0; norm_exp=10'd128; guard=0; sticky=0; #10;
        if (result===32'hC0000000)
            $display("TDES_PASS: test_id=rpack_neg");
        else
            $display("TDES_FAIL: test_id=rpack_neg | input=s1,f0,e128 | expected=C0000000 | got=%h", result);

        // overflow: exp=255 → +Inf (7F800000)
        sign=0; norm_frac=23'd0; norm_exp=10'd255; guard=0; sticky=0; #10;
        if (result===32'h7F800000 && overflow===1'b1)
            $display("TDES_PASS: test_id=rpack_overflow");
        else
            $display("TDES_FAIL: test_id=rpack_overflow | input=e255 | expected=7F800000,ov=1 | got=%h,ov%b", result, overflow);

        // underflow: exp=0 → flush to zero
        sign=0; norm_frac=23'h123456; norm_exp=10'd0; guard=0; sticky=0; #10;
        if (result===32'h00000000 && underflow===1'b1)
            $display("TDES_PASS: test_id=rpack_underflow");
        else
            $display("TDES_FAIL: test_id=rpack_underflow | input=e0 | expected=00000000,un=1 | got=%h,un%b", result, underflow);

        // round-to-nearest-even: guard=1, sticky=1 → round up
        // frac=0, exp=127, g=1, s=1 → frac becomes 1, result = {0, 127, 23'h000001}
        sign=0; norm_frac=23'd0; norm_exp=10'd127; guard=1; sticky=1; #10;
        if (result===32'h3F800001)
            $display("TDES_PASS: test_id=rpack_round_up");
        else
            $display("TDES_FAIL: test_id=rpack_round_up | input=f0,e127,g1,s1 | expected=3F800001 | got=%h", result);

        // ties-to-even: guard=1, sticky=0, frac[0]=0 → no round (even already)
        sign=0; norm_frac=23'd0; norm_exp=10'd127; guard=1; sticky=0; #10;
        if (result===32'h3F800000)
            $display("TDES_PASS: test_id=rpack_ties_even");
        else
            $display("TDES_FAIL: test_id=rpack_ties_even | input=f0,e127,g1,s0 | expected=3F800000 | got=%h", result);

        // ties-to-even: guard=1, sticky=0, frac[0]=1 → round up
        sign=0; norm_frac=23'd1; norm_exp=10'd127; guard=1; sticky=0; #10;
        if (result===32'h3F800002)
            $display("TDES_PASS: test_id=rpack_ties_odd");
        else
            $display("TDES_FAIL: test_id=rpack_ties_odd | input=f1,e127,g1,s0 | expected=3F800002 | got=%h", result);

        $finish;
    end
    initial begin #5000; $display("TDES_FAIL: test_id=rpack_timeout | input=timeout | expected=done | got=hang"); $finish; end
endmodule
