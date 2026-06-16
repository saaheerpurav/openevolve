`timescale 1ns/1ps
// TDES SYSTEM testbench — all 10 ArchXBench fp_multiplier test vectors.
module tb;
    localparam EXP_WIDTH  = 8;
    localparam MANT_WIDTH = 23;
    localparam WIDTH      = 1 + EXP_WIDTH + MANT_WIDTH;
    localparam N = 10;

    reg clk, rst;
    reg  [WIDTH-1:0] a, b;
    reg  [2:0] rnd_mode;
    wire [WIDTH-1:0] product;
    wire [2:0] exception_flags;

    floating_point_multiplier #(.EXP_WIDTH(EXP_WIDTH), .MANT_WIDTH(MANT_WIDTH)) dut (
        .clk(clk), .rst(rst), .a(a), .b(b), .rnd_mode(rnd_mode),
        .product(product), .exception_flags(exception_flags)
    );

    initial clk = 0;
    always #5 clk = ~clk;
    initial begin rst = 1; #12 rst = 0; end

    reg [WIDTH-1:0] tv_a[0:N-1], tv_b[0:N-1], tv_exp[0:N-1];
    reg [2:0]       tv_flg[0:N-1];
    integer i;

    initial begin
        rnd_mode = 3'b000;
        // ArchXBench test vectors (exact from tb.v)
        tv_a[0]=32'h00000000; tv_b[0]=32'h00000000; tv_exp[0]=32'h00000000; tv_flg[0]=3'b001;
        tv_a[1]=32'h00000000; tv_b[1]=32'h3f800000; tv_exp[1]=32'h00000000; tv_flg[1]=3'b001;
        tv_a[2]=32'h7f800000; tv_b[2]=32'h3f800000; tv_exp[2]=32'h7f800000; tv_flg[2]=3'b010;
        tv_a[3]=32'h7f800000; tv_b[3]=32'h00000000; tv_exp[3]=32'h7fc00000; tv_flg[3]=3'b100;
        tv_a[4]=32'h7fc00000; tv_b[4]=32'h3f800000; tv_exp[4]=32'h7fc00000; tv_flg[4]=3'b100;
        tv_a[5]=32'h3fc00000; tv_b[5]=32'h40000000; tv_exp[5]=32'h40400000; tv_flg[5]=3'b000;
        tv_a[6]=32'hc0200000; tv_b[6]=32'hbf000000; tv_exp[6]=32'h3fa00000; tv_flg[6]=3'b000;
        tv_a[7]=32'h7f7fffff; tv_b[7]=32'h40000000; tv_exp[7]=32'h7f800000; tv_flg[7]=3'b010;
        tv_a[8]=32'h00000001; tv_b[8]=32'h00000002; tv_exp[8]=32'h00000000; tv_flg[8]=3'b001;
        tv_a[9]=32'hbf800000; tv_b[9]=32'hbf800000; tv_exp[9]=32'h3f800000; tv_flg[9]=3'b000;

        @(negedge rst);
        @(posedge clk);

        for (i = 0; i < N; i = i + 1) begin
            a = tv_a[i]; b = tv_b[i];
            @(posedge clk); #1;
            if (product === tv_exp[i] && exception_flags === tv_flg[i])
                $display("TDES_PASS: test_id=system_t%0d", i);
            else
                $display("TDES_FAIL: test_id=system_t%0d | input=a=%h,b=%h | expected=%h flags=%0b | got=%h flags=%0b",
                    i, tv_a[i], tv_b[i], tv_exp[i], tv_flg[i], product, exception_flags);
        end
        $finish;
    end
    initial begin #20000; $display("TDES_FAIL: test_id=system_timeout | input=timeout | expected=completion | got=timeout"); $finish; end
endmodule
