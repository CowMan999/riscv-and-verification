`timescale 1ns / 1ns

/*
    0000	ADD        A + B
    0001	SUB        A - B
    0010	AND        A & B
    0011	OR         A | B
    0100	XOR        A ^ B
    0101	SLL        Shift left logical
    0110	SRL        Shift right logical
    0111	SRA        Shift right arithmetic
    1000	SLT        Signed less than
    1001	SLTU       Unsigned less than
*/

module cpu(input logic clk, input logic rst, output logic [1:0] leds);
    
    logic [31:0] pc, pc_next;
    logic [31:0] instruction;
    
    pc u_pc(.clk(clk), .rst(rst), .pc_next(pc_next), .pc(pc));
    instruction_mem u_instruction_mem(.addr(pc), .instruction(instruction));
    
    logic [6:0] opcode;
    logic [2:0] funct3;
    logic [6:0] funct7;
    logic [4:0] rs1, rs2, rd;
    logic [31:0] imm;
    
    decoder u_decoder(.instruction(instruction), .opcode(opcode), .funct3(funct3), .funct7(funct7), .rs1(rs1), .rs2(rs2), .rd(rd), .imm(imm));
    
    logic RegWrite;
    logic MemRead;
    logic MemWrite;
    logic [1:0] MemtoReg;

    logic ALUSrc;
    logic [1:0] ALUOp;
    
    logic Branch;
    logic Jump;
    
    control_unit u_control_unit(.opcode(opcode), .funct3(funct3), .funct7(funct7),
        .RegWrite(RegWrite), .MemRead(MemRead), .MemWrite(MemWrite), .MemtoReg(MemtoReg), .ALUSrc(ALUSrc), .ALUOp(ALUOp), .Branch(Branch), .Jump(Jump));
    
    logic [3:0] alu_op;
    alu_control u_alu_control(.ALUOp(ALUOp), .funct3(funct3), .funct7(funct7), .alu_op(alu_op)); 
    
    logic ws;
    assign ws = RegWrite;
    logic [31:0] rs1_data, rs2_data, rd_data;
   
    
    register_file u_register_file(.clk(clk), .rst(rst), .ws(ws), .rs1(rs1), .rs2(rs2), .rd(rd), .rs1_data(rs1_data), .rs2_data(rs2_data), .rd_data(rd_data), .leds(leds));
    
    logic [31:0] alu_a, alu_b, alu_result;
    logic zflag, lsflag, lssflag;
    
    assign alu_a = (opcode == 7'b0010111) ? pc : rs1_data;
    assign alu_b = ALUSrc ? imm : rs2_data;
    
    alu m_alu(.a(alu_a), .b(alu_b), .alu_op(alu_op), .out(alu_result), .zflag(zflag), .lsflag(lsflag), .lssflag(lssflag));
    
    logic [3:0] ByteEnable;
    
    always_comb begin
        if(MemWrite) begin
            if(funct3 == 3'b010)
                ByteEnable = 4'b1111;
            else if(funct3 == 3'b001) begin
                if(alu_result[1] == 0) ByteEnable = 4'b0011;
                else ByteEnable = 4'b1100;
            end else if(funct3 == 3'b000) begin
                ByteEnable = 4'b0001<<alu_result[1:0];
            end else ByteEnable = 4'b0000;
        end else ByteEnable = 4'b0000;
    end

    logic [31:0] mem_data;
    
    data_mem u_data_mem(.clk(clk), .addr(alu_result), .MemRead(MemRead), .MemWrite(MemWrite), .write_data(rs2_data), .ByteEnable(ByteEnable), .read_data(mem_data));

    logic [31:0] pc_plus4, pc_branch, pc_jump_target;
    logic PCSrc;
    
    assign pc_plus4 = pc + 32'd4;
    assign pc_branch = pc + imm;
    assign pc_jump_target = (opcode == 7'b1100111) ? (rs1_data + imm) & ~1 : (pc + imm); // JALR vs JAL
    
    always_comb begin
        case (funct3)
            'b000: PCSrc = Branch & zflag;
            'b001: PCSrc = Branch & ~zflag;
            'b100: PCSrc = Branch & lssflag;
            'b101: PCSrc = Branch & ~lssflag;
            'b110: PCSrc = Branch & lsflag;
            'b111: PCSrc = Branch & ~lsflag;
            default: PCSrc = 'b0;
        endcase
    end
    
    always_comb begin
        if (Jump)       pc_next = pc_jump_target;
        else if (PCSrc) pc_next = pc_branch;
        else            pc_next = pc_plus4;
    end

    logic [31:0] load_data;
    always_comb begin
        case (funct3)
            3'b000: load_data = {{24{mem_data[7 + 8*alu_result[1:0]]}}, mem_data[8*alu_result[1:0] +: 8]};   // LB
            3'b001: load_data = {{16{mem_data[15 + 16*alu_result[1]]}}, mem_data[16*alu_result[1] +: 16]};   // LH
            3'b010: load_data = mem_data;                                                                     // LW
            3'b100: load_data = {24'b0, mem_data[8*alu_result[1:0] +: 8]};                                    // LBU
            3'b101: load_data = {16'b0, mem_data[16*alu_result[1] +: 16]};                                    // LHU
            default: load_data = mem_data;
        endcase
    end

    always_comb begin
        case (MemtoReg)
            2'b00: rd_data = alu_result;
            2'b01: rd_data = load_data;
            2'b10: rd_data = imm;
            2'b11: rd_data = pc_plus4;
        endcase
    end    
    
endmodule