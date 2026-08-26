`timescale 1ns / 1ns


module pc(input logic clk, input logic rst, input logic [31:0] pc_next, output logic [31:0] pc);

    always_ff @(posedge clk) begin
        if(rst) pc <= 0;
        else pc <= pc_next;
    end
endmodule
