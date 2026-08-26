`timescale 1ns / 1ns

module data_mem(
    input logic clk,
    input logic [31:0] addr,
    input logic MemRead,
    input logic MemWrite,
    input logic [31:0] write_data,
    input logic [3:0] ByteEnable,
    
    output logic [31:0] read_data
    );
    
    parameter DEPTH = 128;
    logic [3:0][7:0] mem [0:DEPTH-1];
    
    logic [31:0] location;
    assign location = addr[31:2];
    always_ff @(posedge clk) begin
        if(MemWrite) begin
            if (ByteEnable[0]) mem[location][0] <= write_data[7:0];
            if (ByteEnable[1]) mem[location][1] <= write_data[15:8];
            if (ByteEnable[2]) mem[location][2] <= write_data[23:16];
            if (ByteEnable[3]) mem[location][3] <= write_data[31:24];
        end
    end
    
    //always_comb begin
    //    if(MemRead) read_data = mem[location];
    //    else read_data = 'b0;
    //end
    // causes ram to be instanciated as flip-flops
    assign read_data = mem[location];
    
endmodule
