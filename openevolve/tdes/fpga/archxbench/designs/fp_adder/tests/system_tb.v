`timescale 1ns/1ps
// TDES SYSTEM testbench — all 36 ArchXBench fp_adder test vectors.
// Adapted from ArchXBench tb.v to emit TDES_PASS/TDES_FAIL per test.
module tb;
    localparam integer WIDTH = 32;
    localparam integer N = 36;

    reg clk, rst;
    reg  [WIDTH-1:0] a, b;
    reg  [2:0] rnd_mode;
    wire [WIDTH-1:0] sum;
    wire [2:0] exception_flags;

    floating_point_adder #(.WIDTH(WIDTH)) dut (
        .clk(clk), .rst(rst), .a(a), .b(b), .rnd_mode(rnd_mode),
        .sum(sum), .exception_flags(exception_flags)
    );

    initial clk = 0;
    always #5 clk = ~clk;
    initial begin rst = 1; #12 rst = 0; end

    reg [WIDTH-1:0] stim_a[0:N-1], stim_b[0:N-1], exp_sum[0:N-1];
    reg [2:0]       stim_rnd[0:N-1], exp_flags[0:N-1];
    integer i;

    initial begin
        stim_a[0]=32'h3F800000;stim_b[0]=32'h40000000;stim_rnd[0]=0;exp_sum[0]=32'h40400000;exp_flags[0]=3'b000;
        stim_a[1]=32'h3F800000;stim_b[1]=32'h3F000000;stim_rnd[1]=0;exp_sum[1]=32'h3FC00000;exp_flags[1]=3'b000;
        stim_a[2]=32'h00000000;stim_b[2]=32'h40A00000;stim_rnd[2]=0;exp_sum[2]=32'h40A00000;exp_flags[2]=3'b000;
        stim_a[3]=32'hBFC00000;stim_b[3]=32'hC0200000;stim_rnd[3]=0;exp_sum[3]=32'hC0800000;exp_flags[3]=3'b000;
        stim_a[4]=32'h3F800000;stim_b[4]=32'h3F800000;stim_rnd[4]=0;exp_sum[4]=32'h40000000;exp_flags[4]=3'b000;
        stim_a[5]=32'h3E800000;stim_b[5]=32'h3E800000;stim_rnd[5]=0;exp_sum[5]=32'h3F000000;exp_flags[5]=3'b000;
        stim_a[6]=32'h40400000;stim_b[6]=32'h40800000;stim_rnd[6]=0;exp_sum[6]=32'h40E00000;exp_flags[6]=3'b000;
        stim_a[7]=32'h41200000;stim_b[7]=32'h40A00000;stim_rnd[7]=0;exp_sum[7]=32'h41700000;exp_flags[7]=3'b000;
        stim_a[8]=32'hC0000000;stim_b[8]=32'h3F800000;stim_rnd[8]=0;exp_sum[8]=32'hBF800000;exp_flags[8]=3'b000;
        // Special values
        stim_a[9]=32'h7F800000;stim_b[9]=32'h3F800000;stim_rnd[9]=0;exp_sum[9]=32'h7F800000;exp_flags[9]=3'b000;
        stim_a[10]=32'h7FC00000;stim_b[10]=32'h3F800000;stim_rnd[10]=0;exp_sum[10]=32'h7FC00000;exp_flags[10]=3'b100;
        stim_a[11]=32'h7F800000;stim_b[11]=32'hFF800000;stim_rnd[11]=0;exp_sum[11]=32'h7FC00000;exp_flags[11]=3'b100;
        stim_a[12]=32'h7F800000;stim_b[12]=32'h7F800000;stim_rnd[12]=0;exp_sum[12]=32'h7F800000;exp_flags[12]=3'b000;
        stim_a[13]=32'hFF800000;stim_b[13]=32'hFF800000;stim_rnd[13]=0;exp_sum[13]=32'hFF800000;exp_flags[13]=3'b000;
        // Zero handling
        stim_a[14]=32'h00000000;stim_b[14]=32'h00000000;stim_rnd[14]=0;exp_sum[14]=32'h00000000;exp_flags[14]=3'b000;
        stim_a[15]=32'h00000000;stim_b[15]=32'h80000000;stim_rnd[15]=0;exp_sum[15]=32'h00000000;exp_flags[15]=3'b000;
        stim_a[16]=32'h00000000;stim_b[16]=32'h80000000;stim_rnd[16]=3;exp_sum[16]=32'h80000000;exp_flags[16]=3'b000;
        stim_a[17]=32'h00000000;stim_b[17]=32'h40400000;stim_rnd[17]=0;exp_sum[17]=32'h40400000;exp_flags[17]=3'b000;
        stim_a[18]=32'h80000000;stim_b[18]=32'h3F800000;stim_rnd[18]=0;exp_sum[18]=32'h3F800000;exp_flags[18]=3'b000;
        // Cancellation
        stim_a[19]=32'h3F800000;stim_b[19]=32'hBF800000;stim_rnd[19]=0;exp_sum[19]=32'h00000000;exp_flags[19]=3'b000;
        stim_a[20]=32'h3F800000;stim_b[20]=32'hBF800000;stim_rnd[20]=3;exp_sum[20]=32'h80000000;exp_flags[20]=3'b000;
        stim_a[21]=32'h40000000;stim_b[21]=32'hC0000000;stim_rnd[21]=0;exp_sum[21]=32'h00000000;exp_flags[21]=3'b000;
        stim_a[22]=32'h3F000000;stim_b[22]=32'hBF000000;stim_rnd[22]=0;exp_sum[22]=32'h00000000;exp_flags[22]=3'b000;
        stim_a[23]=32'h41200000;stim_b[23]=32'hC1200000;stim_rnd[23]=0;exp_sum[23]=32'h00000000;exp_flags[23]=3'b000;
        // Overflow
        stim_a[24]=32'h7F7FFFFF;stim_b[24]=32'h7F7FFFFF;stim_rnd[24]=0;exp_sum[24]=32'h7F800000;exp_flags[24]=3'b010;
        stim_a[25]=32'h7F000000;stim_b[25]=32'h7F000000;stim_rnd[25]=0;exp_sum[25]=32'h7F800000;exp_flags[25]=3'b010;
        stim_a[26]=32'hFF7FFFFF;stim_b[26]=32'hFF7FFFFF;stim_rnd[26]=0;exp_sum[26]=32'hFF800000;exp_flags[26]=3'b010;
        // Denormal/underflow
        stim_a[27]=32'h00400000;stim_b[27]=32'h00400000;stim_rnd[27]=0;exp_sum[27]=32'h00800000;exp_flags[27]=3'b001;
        // Rounding
        stim_a[28]=32'h3F800000;stim_b[28]=32'h33800000;stim_rnd[28]=2;exp_sum[28]=32'h3F800001;exp_flags[28]=3'b000;
        stim_a[29]=32'hBF800000;stim_b[29]=32'hB3800000;stim_rnd[29]=3;exp_sum[29]=32'hBF800001;exp_flags[29]=3'b000;
        stim_a[30]=32'h40400000;stim_b[30]=32'h33800001;stim_rnd[30]=1;exp_sum[30]=32'h40400000;exp_flags[30]=3'b000;
        stim_a[31]=32'h3F800000;stim_b[31]=32'h33800000;stim_rnd[31]=0;exp_sum[31]=32'h3F800000;exp_flags[31]=3'b000;
        stim_a[32]=32'h3F800001;stim_b[32]=32'h33FFFFFF;stim_rnd[32]=0;exp_sum[32]=32'h3F800002;exp_flags[32]=3'b000;
        // Edge
        stim_a[33]=32'h00800000;stim_b[33]=32'h00800000;stim_rnd[33]=0;exp_sum[33]=32'h01000000;exp_flags[33]=3'b000;
        stim_a[34]=32'h5F000000;stim_b[34]=32'h3F800000;stim_rnd[34]=0;exp_sum[34]=32'h5F000000;exp_flags[34]=3'b000;
        stim_a[35]=32'h3F800000;stim_b[35]=32'hBF7FFFFF;stim_rnd[35]=0;exp_sum[35]=32'h33800000;exp_flags[35]=3'b000;

        @(negedge rst);
        @(posedge clk);

        for (i = 0; i < N; i = i + 1) begin
            a = stim_a[i]; b = stim_b[i]; rnd_mode = stim_rnd[i];
            @(posedge clk); #1;
            if (sum === exp_sum[i] && exception_flags === exp_flags[i])
                $display("TDES_PASS: test_id=system_t%0d", i);
            else
                $display("TDES_FAIL: test_id=system_t%0d | input=a=%h,b=%h | expected=%h flags=%0b | got=%h flags=%0b",
                    i, stim_a[i], stim_b[i], exp_sum[i], exp_flags[i], sum, exception_flags);
        end
        $finish;
    end

    initial begin #40000; $display("TDES_FAIL: test_id=system_timeout | input=timeout | expected=completion | got=timeout"); $finish; end
endmodule
