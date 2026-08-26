`timescale 1ns / 1ns

module instruction_mem(
    input  logic [31:0] addr,
    output logic [31:0] instruction
    );
    
    parameter DEPTH = 256;
    logic [31:0] mem [0:DEPTH-1]; 
    
    initial begin
        $readmemh("program.hex", mem);
    end

    assign instruction = addr[31:2] <= DEPTH-1 ? mem[addr[31:2]] : 0;
    
endmodule
