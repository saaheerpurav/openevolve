`timescale 1ns/1ps
// IEEE-754 single-precision FP adder core — combinational reference.
// Handles normal and denormal operands only (NaN/Inf/zero: see fp_special_case).
module fp_adder_core #(parameter WIDTH = 32) (
    input  [WIDTH-1:0] a,
    input  [WIDTH-1:0] b,
    input  [2:0]       rnd_mode,   // 000=RNE,001=RTZ,010=RTP,011=RTN
    output reg [WIDTH-1:0] result,
    output reg [2:0]   flags       // [2]=invalid,[1]=overflow,[0]=underflow/inexact
);
    // ---- Unpack ----------------------------------------------------------------
    wire        sa = a[31], sb = b[31];
    wire [7:0]  ea = a[30:23], eb = b[30:23];
    wire [22:0] ma = a[22:0],  mb = b[22:0];

    wire a_den = (ea == 8'h00);
    wire b_den = (eb == 8'h00);

    // 24-bit significand (implicit leading 1 for normals, 0 for denormals)
    wire [23:0] sigA = a_den ? {1'b0, ma} : {1'b1, ma};
    wire [23:0] sigB = b_den ? {1'b0, mb} : {1'b1, mb};

    // Effective exponents (denormals use eff_exp=1)
    wire [8:0] eA = a_den ? 9'd1 : {1'b0, ea};
    wire [8:0] eB = b_den ? 9'd1 : {1'b0, eb};

    // ---- Step 1: Identify larger magnitude ----------------------------------------
    // Swap so L always has the larger-or-equal exponent (tie: larger significand is L)
    wire a_big = (eA > eB) || (eA == eB && sigA >= sigB);
    wire [8:0]  eL   = a_big ? eA   : eB;
    wire [23:0] sigL = a_big ? sigA : sigB;
    wire [23:0] sigS = a_big ? sigB : sigA;
    wire        sgnL = a_big ? sa   : sb;
    wire        sgnS = a_big ? sb   : sa;
    wire [8:0]  ediff = eL - (a_big ? eB : eA);

    // ---- Step 2: Align smaller significand ----------------------------------------
    // Extended representation: 30 bits = {24-bit sig, 6-bit guard/GRS region}
    // Leading 1 of sL_ext is at bit 29 for normal numbers.
    wire [29:0] sL_ext = {sigL, 6'b0};

    reg  [29:0] sS_shifted;
    reg         sticky_acc;
    always @(*) begin
        sticky_acc = 1'b0;
        sS_shifted = {sigS, 6'b0};
        if (ediff >= 30) begin
            sticky_acc = |sigS;
            sS_shifted = 30'b0;
        end else if (ediff > 0) begin
            // Sticky: any bit shifted past bit 0
            sticky_acc = |({sigS, 6'b0} << (30 - ediff));
            sS_shifted = {sigS, 6'b0} >> ediff;
        end
        // Fold sticky into bit 0 of sS_shifted
        sS_shifted[0] = sS_shifted[0] | sticky_acc;
    end

    // ---- Step 3: Add or subtract --------------------------------------------------
    wire eff_sub = sgnL ^ sgnS;   // Different signs → subtract magnitudes

    // 31-bit to capture carry out of bit 29
    wire [30:0] sum31 = eff_sub ?
        ({1'b0, sL_ext} - {1'b0, sS_shifted}) :
        ({1'b0, sL_ext} + {1'b0, sS_shifted});

    wire        ovf_bit = sum31[30];   // Addition produced carry into bit 30
    wire [29:0] sum30   = sum31[29:0]; // Lower 30 bits

    wire res_zero = ~|sum31;  // Exact cancellation

    // ---- Step 4: Normalize --------------------------------------------------------
    // Find leading 1 in sum30[29:0]. Leading 1 should be at bit 29 after shift.
    // lz = number of positions to left-shift so leading 1 reaches bit 29.
    // Default 5'd30 means no leading 1 found (sum30 == 0).
    reg [4:0] lz;
    integer   ii;
    always @(*) begin
        lz = 5'd30;
        for (ii = 29; ii >= 0; ii = ii - 1)
            if (sum30[ii] && lz == 5'd30)
                lz = 5'd29 - ii[4:0];
    end

    // Normalized 30-bit sum: leading 1 at bit 29.
    // For ovf_bit: right-shift by 1 (sum31[30:1]), leading 1 at bit 29.
    // For normal: left-shift sum30 by lz.
    wire [29:0] norm_sum = ovf_bit ? sum31[30:1] : (sum30 << lz);

    // Updated exponent
    wire [9:0] eR_pre =
        ovf_bit ? ({1'b0, eL} + 10'd1) : ({1'b0, eL} - {5'b0, lz});

    // ---- Step 5: Extract mantissa and GRS bits ------------------------------------
    // Layout of norm_sum after normalization:
    //   bit 29      = implicit leading 1 (not stored in result)
    //   bits [28:6] = 23-bit mantissa
    //   bit  5      = guard bit G
    //   bit  4      = round bit R
    //   bits [3:0]  = sticky accumulator S
    wire [22:0] mant23 = norm_sum[28:6];
    wire G = norm_sum[5];
    wire R = norm_sum[4];
    wire S = |norm_sum[3:0];

    // ---- Step 6: Round ------------------------------------------------------------
    wire round_up;
    assign round_up =
        (rnd_mode == 3'd0) ? (G & (R | S | mant23[0])) :  // RNE: > 0.5 ulp, or =0.5 & odd
        (rnd_mode == 3'd1) ? 1'b0 :                         // RTZ: truncate
        (rnd_mode == 3'd2) ? ((G | R | S) & ~sgnL) :        // RTP: toward +Inf
        (rnd_mode == 3'd3) ? ((G | R | S) &  sgnL) :        // RTN: toward -Inf
        1'b0;

    wire [23:0] mant_plus  = {1'b0, mant23} + {23'b0, round_up};
    wire        rnd_carry  = mant_plus[23];
    wire [22:0] mant_final = rnd_carry ? 23'b0 : mant_plus[22:0];
    wire [10:0] eR         = {1'b0, eR_pre} + {10'b0, rnd_carry};

    // ---- Step 7: Pack result ------------------------------------------------------
    always @(*) begin
        flags  = 3'b000;
        result = 32'b0;

        if (res_zero) begin
            // Complete cancellation — produce signed zero
            // RTN: result = -0 if either operand was negative; else +0
            result = (rnd_mode == 3'd3 && (sa | sb)) ?
                     {1'b1, 31'b0} : 32'b0;
        end else if (eR >= 11'd255) begin
            // Exponent overflow → infinity (with mode-specific clamping)
            flags[1] = 1'b1;
            case (rnd_mode)
                3'd1: result = {sgnL, 8'hFE, 23'h7FFFFF}; // RTZ → max normal
                3'd2: result = sgnL ? {1'b1, 8'hFE, 23'h7FFFFF}
                                    : {1'b0, 8'hFF, 23'b0};
                3'd3: result = sgnL ? {1'b1, 8'hFF, 23'b0}
                                    : {1'b0, 8'hFE, 23'h7FFFFF};
                default: result = {sgnL, 8'hFF, 23'b0};    // RNE → Inf
            endcase
        end else if (eR[10] || eR == 11'd0) begin
            // Exponent underflow → flush to signed zero
            flags[0] = 1'b1;
            result   = {sgnL, 31'b0};
        end else begin
            result = {sgnL, eR[7:0], mant_final};
            // Denormal operands that produced a valid result still flag underflow
            if (a_den || b_den) flags[0] = 1'b1;
        end
    end
endmodule
