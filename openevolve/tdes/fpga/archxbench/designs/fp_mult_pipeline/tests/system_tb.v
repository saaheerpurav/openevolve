`timescale 1ns/1ps
// System testbench: full pipeline against ArchXBench test vectors.
// The golden fp_mult_pipeline top module is prepended by the loader;
// only the 5 sub-modules come from the candidate.
module tb;
    reg clk, rst;
    reg [31:0] a, b;
    reg valid_in;
    wire [31:0] result;
    wire valid_out;
    integer test_num;

    fp_mult_pipeline #(.LATENCY(5)) DUT(
        .clk(clk), .rst(rst),
        .a(a), .b(b), .valid_in(valid_in),
        .result(result), .valid_out(valid_out)
    );

    always #5 clk = ~clk;

    task check;
        input [255:0] tid;
        input [31:0] op_a, op_b, expected;
        begin
            @(posedge clk);
            a = op_a; b = op_b; valid_in = 1;
            test_num = test_num + 1;
            @(posedge clk);
            valid_in = 0;
            @(posedge valid_out);
            @(posedge clk);
            #1;
            if (result === expected)
                $display("TDES_PASS: test_id=%0s", tid);
            else
                $display("TDES_FAIL: test_id=%0s | input=a=%h,b=%h | expected=%h | got=%h",
                    tid, op_a, op_b, expected, result);
        end
    endtask

    initial begin
        clk = 0; rst = 1; valid_in = 0; a = 0; b = 0; test_num = 0;
        repeat(10) @(posedge clk);
        rst = 0;
        repeat(5) @(posedge clk);

        check("sys_1x2",      32'h3F800000, 32'h40000000, 32'h40000000);
        check("sys_2x3",      32'h40000000, 32'h40400000, 32'h40C00000);
        check("sys_0p5x0p5",  32'h3F000000, 32'h3F000000, 32'h3E800000);
        check("sys_4x0p25",   32'h40800000, 32'h3E800000, 32'h3F800000);
        check("sys_neg1x2",   32'hBF800000, 32'h40000000, 32'hC0000000);
        check("sys_negxneg",  32'hBF800000, 32'hC0000000, 32'h40000000);
        check("sys_1xneg2",   32'h3F800000, 32'hC0000000, 32'hC0000000);
        check("sys_neg1xneg1",32'hBF800000, 32'hBF800000, 32'h3F800000);
        check("sys_32x1",     32'h42000000, 32'h3F800000, 32'h42000000);
        check("sys_large_sm", 32'h47000000, 32'h38000000, 32'h3F800000);
        check("sys_sm_large", 32'h33800000, 32'h4B000000, 32'h3F000000);
        check("sys_nan_a",    32'h7FC00000, 32'h3F800000, 32'h7FC00000);
        check("sys_nan_b",    32'h3F800000, 32'h7FC00000, 32'h7FC00000);
        check("sys_zero_a",   32'h00000000, 32'h3F800000, 32'h00000000);
        check("sys_negz_a",   32'h80000000, 32'h3F800000, 32'h80000000);
        check("sys_zeroxinf", 32'h00000000, 32'h7F800000, 32'h7FC00000);
        check("sys_inf_pos",  32'h7F800000, 32'h3F800000, 32'h7F800000);
        check("sys_inf_neg",  32'h7F800000, 32'hBF800000, 32'hFF800000);
        check("sys_denorm",   32'h00800000, 32'h3F800000, 32'h00800000);
        check("sys_overflow", 32'h7F000000, 32'h7F000000, 32'h7F800000);
        check("sys_underflow",32'h00800000, 32'h00800000, 32'h00000000);
        check("sys_tiny_sq",  32'h33800000, 32'h33800000, 32'h27800000);
        check("sys_third_x2", 32'h3EAAAAAB, 32'h40000000, 32'h3F2AAAAB);
        check("sys_1x1",      32'h3F800000, 32'h3F800000, 32'h3F800000);
        check("sys_2x2",      32'h40000000, 32'h40000000, 32'h40800000);

        repeat(10) @(posedge clk);
        $finish;
    end
    initial begin #50000; $display("TDES_FAIL: test_id=sys_timeout | input=timeout | expected=done | got=hang"); $finish; end
endmodule
