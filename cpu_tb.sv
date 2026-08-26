`timescale 1ns / 1ns

module cpu_tb;
    
    logic clk = 0, rst = 0;
    cpu dut(.clk(clk), .rst(rst));
    
    initial forever #5 clk = ~clk;
    
    // Driver: reset task
    task reset_cpu();
        rst = 1;
        repeat(2) @(posedge clk);
        rst = 0;
        $display("[DRIVER] Reset complete at t=%0t", $time);
    endtask

    // Driver: run for N cycles
    task run_cycles(input int n);
        repeat(n) @(posedge clk);
    endtask
    
    integer logfile;
    initial logfile = $fopen("rtl_trace.log", "w");
    
    // write to logfile to compare against python sim
    always @(posedge clk) begin
        if (!rst && dut.RegWrite && dut.rd != 0)
            $fwrite(logfile, "REG %0d %h\n", dut.rd, dut.rd_data);
        if (!rst && dut.MemWrite)
            $fwrite(logfile, "MEM %h %h\n", dut.alu_result, dut.rs2_data);
    end
    
    
    // Monitor: log every register write
    always @(posedge clk) begin
        if (!rst && dut.RegWrite && dut.rd != 0) begin
            $display("[MONITOR] t=%0t PC=%h WRITE x%0d = %h",
                      $time, dut.pc, dut.rd, dut.rd_data);
        end
    
        // Monitor: log every memory write
        if (!rst && dut.MemWrite) begin
            $display("[MONITOR] t=%0t MEM WRITE addr=%h data=%h",
                      $time, dut.alu_result, dut.rs2_data);
        end
        // Monitor: log every jump
        if (!rst && dut.PCSrc) begin
            $display("[MONITOR] t=%0t COMD JUMP pc=%h pc_next=%h",
                      $time, dut.pc, dut.pc_next);
        end
        // Monitor: log every cond jump
        if (!rst && dut.Jump) begin
            $display("[MONITOR] t=%0t JUMP pc=%h pc_next=%h",
                      $time, dut.pc, dut.pc_next);
        end
    end 
    
    initial begin 
        reset_cpu();
        run_cycles(20);
        $finish;
    end
    
endmodule
