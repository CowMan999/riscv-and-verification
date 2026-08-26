`timescale 1ns / 1ns
module control_unit(
    input logic [6:0] opcode,
    input logic [2:0] funct3,

    input logic [6:0] funct7,
    
    output logic RegWrite,
    output logic MemRead,
    output logic MemWrite,
    output logic [1:0] MemtoReg,

    output logic ALUSrc,
    output logic [1:0] ALUOp,
    
    output logic Branch,
    output logic Jump
    );
    
    always_comb begin
        case (opcode) 
            7'b0110011: {RegWrite, MemRead, MemWrite, MemtoReg, ALUSrc, Branch, Jump, ALUOp} 
                      = {1'b1,    1'b0,    1'b0,     2'b00,   1'b0,   1'b0,   1'b0, 2'b10}; // R-type

            7'b0010011: {RegWrite, MemRead, MemWrite, MemtoReg, ALUSrc, Branch, Jump, ALUOp}
                      = {1'b1,    1'b0,    1'b0,     2'b00,   1'b1,   1'b0,   1'b0, 2'b10}; // I-type (ADDI etc.)

            7'b0000011: {RegWrite, MemRead, MemWrite, MemtoReg, ALUSrc, Branch, Jump, ALUOp}
                      = {1'b1,    1'b1,    1'b0,     2'b01,   1'b1,   1'b0,   1'b0, 2'b00}; // Load

            7'b0100011: {RegWrite, MemRead, MemWrite, MemtoReg, ALUSrc, Branch, Jump, ALUOp}
                      = {1'b0,    1'b0,    1'b1,     2'b00,   1'b1,   1'b0,   1'b0, 2'b00}; // Store

            7'b1100011: {RegWrite, MemRead, MemWrite, MemtoReg, ALUSrc, Branch, Jump, ALUOp}
                      = {1'b0,    1'b0,    1'b0,     2'b00,   1'b0,   1'b1,   1'b0, 2'b01}; // Branch

            7'b0110111: {RegWrite, MemRead, MemWrite, MemtoReg, ALUSrc, Branch, Jump, ALUOp}
                      = {1'b1,    1'b0,    1'b0,     2'b10,   1'b1,   1'b0,   1'b0, 2'b11}; // LUI

            7'b0010111: {RegWrite, MemRead, MemWrite, MemtoReg, ALUSrc, Branch, Jump, ALUOp}
                      = {1'b1,    1'b0,    1'b0,     2'b00,   1'b1,   1'b0,   1'b0, 2'b00}; // AUIPC

            7'b1101111: {RegWrite, MemRead, MemWrite, MemtoReg, ALUSrc, Branch, Jump, ALUOp}
                      = {1'b1,    1'b0,    1'b0,     2'b11,   1'b0,   1'b0,   1'b1, 2'b00}; // JAL

            7'b1100111: {RegWrite, MemRead, MemWrite, MemtoReg, ALUSrc, Branch, Jump, ALUOp}
                      = {1'b1,    1'b0,    1'b0,     2'b11,   1'b1,   1'b0,   1'b1, 2'b00}; // JALR

            default:   {RegWrite, MemRead, MemWrite, MemtoReg, ALUSrc, Branch, Jump, ALUOp}
                      = {1'b0,    1'b0,    1'b0,     2'b00,   1'b0,   1'b0,   1'b0, 2'b00}; // safe default
        endcase
    end

endmodule
