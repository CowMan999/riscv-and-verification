`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 08/25/2026 08:34:45 PM
// Design Name: 
// Module Name: cpu_imp
// Project Name: 
// Target Devices: 
// Tool Versions: 
// Description: 
// 
// Dependencies: 
// 
// Revision:
// Revision 0.01 - File Created
// Additional Comments:
// 
//////////////////////////////////////////////////////////////////////////////////


module cpu_imp(input clk, input rst_n, output [1:0] leds);
    wire rst;
    assign rst = ~rst_n;
    cpu dut(.clk(clk), .rst(rst), .leds(leds));

endmodule
