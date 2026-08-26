`timescale 1ns / 1ns
module alu_control (
    input logic [1:0] ALUOp,
    
    input logic [2:0] funct3,
    input logic [6:0] funct7,
    
    output logic [3:0] alu_op
    );
    
    always_comb begin
        case (ALUOp)
            2'b00: alu_op = 4'b0000; // loads/stores/AUIPC/JALR -> ADD

            2'b01: alu_op = 4'b0001; // branches -> SUB (for comparison/zero flag)

            2'b10: begin // R-type or I-type arithmetic, decode via funct3/funct7
                case (funct3)
                    3'b000: alu_op = (funct7 == 7'b0100000) ? 4'b0001 : 4'b0000; 
                            // funct3=000: SUB if funct7=0100000 (R-type SUB), else ADD (covers ADD and ADDI)
                    3'b001: alu_op = 4'b0101; // SLL / SLLI
                    3'b010: alu_op = 4'b1000; // SLT / SLTI
                    3'b011: alu_op = 4'b1001; // SLTU / SLTIU
                    3'b100: alu_op = 4'b0100; // XOR / XORI
                    3'b101: alu_op = (funct7 == 7'b0100000) ? 4'b0111 : 4'b0110; 
                            // funct3=101: SRA if funct7=0100000, else SRL (covers SRL/SRLI/SRA/SRAI)
                    3'b110: alu_op = 4'b0011; // OR / ORI
                    3'b111: alu_op = 4'b0010; // AND / ANDI
                    default: alu_op = 4'b0000;
                endcase
            end

            default: alu_op = 4'b0000; // ALUOp = 11 (LUI, etc.) -> don't-care, default to ADD
        endcase
    end

endmodule
