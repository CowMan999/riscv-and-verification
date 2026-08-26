`timescale 1ns / 1ns
module decoder (
    input [31:0] instruction,
    
    output logic [6:0] opcode,
    output logic [2:0] funct3,
    output logic [6:0] funct7,
    output logic [4:0] rs1, rs2, rd,
    output logic [31:0] imm
    
    );
    
    always_comb begin
        opcode = instruction[6:0];
        case (opcode)
            7'b0110011: begin // r-type
                {funct7, rs2, rs1, funct3, rd} = instruction[31:7];
            end
        
            7'b0010011: begin // i-type
                imm = $signed(instruction[31:20]);
                {rs1, funct3, rd} = instruction[19:7];
                funct7 = instruction[31:25];
            end
        
            7'b0100011: begin // store type
                imm = $signed({instruction[31:25], instruction[11:7]});
                {rs2, rs1, funct3} = instruction[24:12];
            end
            
            7'b1100011: begin // branch type
                imm = $signed({instruction[31],instruction[7],instruction[30:25],instruction[11:8],1'b0});
                {rs2, rs1, funct3} = instruction[24:12];
            end
            
            7'b0110111: begin // u type
                imm = {instruction[31:12], 12'b0};
                rd = instruction[11:7];
            end
            7'b0010111: begin // u type 2
                imm = {instruction[31:12], 12'b0};
                rd = instruction[11:7];
            end
            
            7'b1101111: begin // j type
                imm = $signed({instruction[31], instruction[19:12], instruction[20], instruction[30:21],1'b0});
                rd = instruction[11:7];
            end
            
            7'b0000011: begin // load type 
                imm = $signed(instruction[31:20]);
                {rs1, funct3, rd} = instruction[19:7];
            end
            
            7'b1100111: begin // jalr
                imm = $signed(instruction[31:20]);
                {rs1, funct3, rd} = instruction[19:7];
            end
            
            default: begin
                funct3 = '0; funct7 = '0; rs1 = '0; rs2 = '0; rd = '0; imm = '0;
            end
            
        endcase
    end
    
endmodule
