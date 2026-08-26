`timescale 1ns / 1ns

module register_file(
    input logic clk,
    input logic rst,
    
    input logic ws, // write signal
    input logic [4:0] rs1, // read 1
    input logic [4:0] rs2, // read 2

    input logic [4:0] rd, // write
    input logic [31:0] rd_data, // write data

    output logic [31:0] rs1_data, // read 1 data
    output logic [31:0] rs2_data, // read 2 data
    output logic [1:0] leds

    );
    
    logic [31:0] regs [31:0];
    
    always_comb begin
        if(rs1 != 0)
            rs1_data = regs[rs1];
        else rs1_data = 32'b0;
        if(rs2 != 0)
            rs2_data = regs[rs2];
        else rs2_data = 32'b0;
    end
    
    integer i;
    always_ff @(posedge clk) begin
        if(rst) begin
            for(i=0;i<32;i++) regs[i]<=32'b0;
        end else if(ws && (rd != 0) ) begin
            regs[rd] <= rd_data;
        end
    end
    
    assign leds = regs[1][1:0];
    
endmodule
