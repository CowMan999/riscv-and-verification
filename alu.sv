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

module alu(input logic [31:0] a, input logic [31:0] b, input logic [3:0] alu_op, output logic [31:0] out, output logic zflag, output logic lsflag,  output logic lssflag);
    
    always_comb begin
    
        case(alu_op) 
            4'b0000: out = a+b;
            4'b0001: out = a-b;
            4'b0010: out = a&b;
            4'b0011: out = a|b;
            4'b0100: out = a^b;
            4'b0101: out = a<<b[4:0];
            4'b0110: out = a>>b[4:0];
            4'b0111: out = a>>>b[4:0];
            4'b1000: out = $signed(a)<$signed(b);
            4'b1001: out = a<b;
            default: out = 32'b0;
        endcase
        
        if(out ==  32'b0) zflag = 1'b1;
        else zflag = 1'b0;
        
        if(a<b) lsflag = 'b1;
        else lsflag = 'b0;
        if($signed(a)<$signed(b)) lssflag = 'b1;
        else lssflag = 'b0;
    end

endmodule
