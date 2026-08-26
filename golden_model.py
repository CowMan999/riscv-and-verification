#!/usr/bin/env python3
"""
Golden reference model for the single-cycle RV32I CPU implemented in:
    pc.sv, instruction_mem.sv, decoder.sv, control_unit.sv, alu_control.sv,
    alu.sv, register_file.sv, data_mem.sv, cpu.sv

This is a *bit-accurate*, cycle-accurate, spec-accurate RV32I behavioral
model written in plain Python, meant to be used as a golden reference to
check the (fixed) SystemVerilog RTL against -- e.g. by comparing PC /
register file / memory / signal values cycle by cycle in a testbench, or
by cross-checking final architectural state after running a program.

This model implements spec-correct RV32I regardless of the current state
of the RTL. It assumes the following fixes (search "fixed:" below for
each spot):
    1. Loads (LB/LH/LBU/LHU) extract and sign/zero-extend the addressed
       byte/halfword instead of returning the raw word.
    2. funct7 is decoded for I-type instructions too, so SRLI vs. SRAI
       is selected correctly instead of depending on an inferred latch.
    3. JALR clears the LSB of the computed target address.
    4. Store data is shifted into the correct byte lane before being
       written, alongside ByteEnable, so SB/SH at a non-zero offset
       within a word write the *low* byte/halfword of rs2, not whatever
       raw bit-slice of rs2 happens to sit at that lane. (This is a
       distinct bug from #1: the original data_mem.sv always takes
       byte lane N from write_data[8N+7:8N] with no pre-shift, so e.g.
       `sb x3, 1(x0)` would write x3[15:8] into memory instead of
       x3[7:0].)

Remaining known simplifications relative to the full RV32I spec (kept
as-is, matching the DUT, since they're out of scope for this core):
    - No exceptions/traps (illegal opcode -> silent NOP, no illegal-
      instruction trap).
    - No misaligned-access detection/trapping; SH assumes natural
      halfword alignment (only checks addr[1], not addr[0]).
    - No ecall/ebreak/fence/Zicsr support.
See the comments next to each piece of logic for the corresponding RTL
file/line this was translated from.

Usage:
    python3 golden_model.py program.hex               # run to a fixed point (self-loop) or step limit
    python3 golden_model.py program.hex --steps 100 -v # verbose cycle-by-cycle trace
"""

from __future__ import annotations
import argparse
import sys
from dataclasses import dataclass, field


MASK32 = 0xFFFF_FFFF


def sext(value: int, bits: int) -> int:
    """Sign-extend `value` (an unsigned Python int holding `bits` bits) to 32 bits,
    then return it as an *unsigned* 32-bit Python int (mod 2**32)."""
    sign_bit = 1 << (bits - 1)
    value &= (1 << bits) - 1
    if value & sign_bit:
        value -= (1 << bits)
    return value & MASK32


def to_signed32(value: int) -> int:
    value &= MASK32
    if value & 0x8000_0000:
        value -= 1 << 32
    return value


# ---------------------------------------------------------------------------
# alu.sv
# ---------------------------------------------------------------------------
# 0000 ADD   0001 SUB   0010 AND   0011 OR   0100 XOR
# 0101 SLL   0110 SRL   0111 SRA   1000 SLT  1001 SLTU
def alu(a: int, b: int, alu_op: int):
    a &= MASK32
    b &= MASK32
    shamt = b & 0x1F  # b[4:0]

    if alu_op == 0b0000:      # ADD
        out = (a + b) & MASK32
    elif alu_op == 0b0001:    # SUB
        out = (a - b) & MASK32
    elif alu_op == 0b0010:    # AND
        out = a & b
    elif alu_op == 0b0011:    # OR
        out = a | b
    elif alu_op == 0b0100:    # XOR
        out = a ^ b
    elif alu_op == 0b0101:    # SLL
        out = (a << shamt) & MASK32
    elif alu_op == 0b0110:    # SRL
        out = (a >> shamt) & MASK32
    elif alu_op == 0b0111:    # SRA (arithmetic, sign-extended)
        out = ((to_signed32(a) >> shamt) if shamt else to_signed32(a)) & MASK32
    elif alu_op == 0b1000:    # SLT (signed)
        out = 1 if to_signed32(a) < to_signed32(b) else 0
    elif alu_op == 0b1001:    # SLTU (unsigned)
        out = 1 if a < b else 0
    else:
        out = 0

    zflag = 1 if out == 0 else 0
    lsflag = 1 if a < b else 0                              # unsigned a<b
    lssflag = 1 if to_signed32(a) < to_signed32(b) else 0    # signed a<b
    return out, zflag, lsflag, lssflag


# ---------------------------------------------------------------------------
# decoder.sv
# ---------------------------------------------------------------------------
@dataclass
class Decoded:
    opcode: int = 0
    funct3: int = 0
    funct7: int = 0
    rs1: int = 0
    rs2: int = 0
    rd: int = 0
    imm: int = 0


def decode(instruction: int) -> Decoded:
    instruction &= MASK32
    d = Decoded()
    d.opcode = instruction & 0x7F

    if d.opcode == 0b0110011:  # R-type
        d.funct7 = (instruction >> 25) & 0x7F
        d.rs2 = (instruction >> 20) & 0x1F
        d.rs1 = (instruction >> 15) & 0x1F
        d.funct3 = (instruction >> 12) & 0x7
        d.rd = (instruction >> 7) & 0x1F

    elif d.opcode == 0b0010011:  # I-type (ADDI, SLTI, SLLI/SRLI/SRAI, ...)
        d.imm = sext((instruction >> 20) & 0xFFF, 12)
        d.rs1 = (instruction >> 15) & 0x1F
        d.funct3 = (instruction >> 12) & 0x7
        d.rd = (instruction >> 7) & 0x1F
        # funct7 must be decoded here too so SRLI/SRAI can be told apart
        # (fixed: previously undriven -> inferred latch in the RTL)
        d.funct7 = (instruction >> 25) & 0x7F

    elif d.opcode == 0b0100011:  # Store (S-type)
        imm_hi = (instruction >> 25) & 0x7F
        imm_lo = (instruction >> 7) & 0x1F
        d.imm = sext((imm_hi << 5) | imm_lo, 12)
        d.rs2 = (instruction >> 20) & 0x1F
        d.rs1 = (instruction >> 15) & 0x1F
        d.funct3 = (instruction >> 12) & 0x7

    elif d.opcode == 0b1100011:  # Branch (B-type)
        b31 = (instruction >> 31) & 0x1
        b7 = (instruction >> 7) & 0x1
        b30_25 = (instruction >> 25) & 0x3F
        b11_8 = (instruction >> 8) & 0xF
        raw = (b31 << 12) | (b7 << 11) | (b30_25 << 5) | (b11_8 << 1)
        d.imm = sext(raw, 13)
        d.rs2 = (instruction >> 20) & 0x1F
        d.rs1 = (instruction >> 15) & 0x1F
        d.funct3 = (instruction >> 12) & 0x7

    elif d.opcode == 0b0110111:  # LUI (U-type)
        d.imm = (instruction & 0xFFFFF000) & MASK32
        d.rd = (instruction >> 7) & 0x1F

    elif d.opcode == 0b0010111:  # AUIPC (U-type)
        d.imm = (instruction & 0xFFFFF000) & MASK32
        d.rd = (instruction >> 7) & 0x1F

    elif d.opcode == 0b1101111:  # JAL (J-type)
        b31 = (instruction >> 31) & 0x1
        b19_12 = (instruction >> 12) & 0xFF
        b20 = (instruction >> 20) & 0x1
        b30_21 = (instruction >> 21) & 0x3FF
        raw = (b31 << 20) | (b19_12 << 12) | (b20 << 11) | (b30_21 << 1)
        d.imm = sext(raw, 21)
        d.rd = (instruction >> 7) & 0x1F

    elif d.opcode == 0b0000011:  # Load (I-type)
        d.imm = sext((instruction >> 20) & 0xFFF, 12)
        d.rs1 = (instruction >> 15) & 0x1F
        d.funct3 = (instruction >> 12) & 0x7
        d.rd = (instruction >> 7) & 0x1F

    elif d.opcode == 0b1100111:  # JALR (I-type)
        d.imm = sext((instruction >> 20) & 0xFFF, 12)
        d.rs1 = (instruction >> 15) & 0x1F
        d.funct3 = (instruction >> 12) & 0x7
        d.rd = (instruction >> 7) & 0x1F

    else:
        # default: everything zero (matches RTL default branch), opcode kept
        pass

    return d


# ---------------------------------------------------------------------------
# control_unit.sv
# ---------------------------------------------------------------------------
@dataclass
class Control:
    RegWrite: int = 0
    MemRead: int = 0
    MemWrite: int = 0
    MemtoReg: int = 0   # 2 bits
    ALUSrc: int = 0
    ALUOp: int = 0       # 2 bits
    Branch: int = 0
    Jump: int = 0


_CONTROL_TABLE = {
    0b0110011: Control(1, 0, 0, 0b00, 0, 0b10, 0, 0),  # R-type
    0b0010011: Control(1, 0, 0, 0b00, 1, 0b10, 0, 0),  # I-type arith
    0b0000011: Control(1, 1, 0, 0b01, 1, 0b00, 0, 0),  # Load
    0b0100011: Control(0, 0, 1, 0b00, 1, 0b00, 0, 0),  # Store
    0b1100011: Control(0, 0, 0, 0b00, 0, 0b01, 1, 0),  # Branch
    0b0110111: Control(1, 0, 0, 0b10, 1, 0b11, 0, 0),  # LUI
    0b0010111: Control(1, 0, 0, 0b00, 1, 0b00, 0, 0),  # AUIPC
    0b1101111: Control(1, 0, 0, 0b11, 0, 0b00, 0, 1),  # JAL
    0b1100111: Control(1, 0, 0, 0b11, 1, 0b00, 0, 1),  # JALR
}


def control_unit(opcode: int) -> Control:
    return _CONTROL_TABLE.get(opcode, Control())  # default: all-zero


# ---------------------------------------------------------------------------
# alu_control.sv
# ---------------------------------------------------------------------------
def alu_control(ALUOp: int, funct3: int, funct7: int) -> int:
    if ALUOp == 0b00:
        return 0b0000  # loads/stores/AUIPC/JALR -> ADD
    if ALUOp == 0b01:
        return 0b0001  # branches -> SUB
    if ALUOp == 0b10:
        if funct3 == 0b000:
            return 0b0001 if funct7 == 0b0100000 else 0b0000  # SUB / ADD(I)
        if funct3 == 0b001:
            return 0b0101  # SLL/SLLI
        if funct3 == 0b010:
            return 0b1000  # SLT/SLTI
        if funct3 == 0b011:
            return 0b1001  # SLTU/SLTIU
        if funct3 == 0b100:
            return 0b0100  # XOR/XORI
        if funct3 == 0b101:
            return 0b0111 if funct7 == 0b0100000 else 0b0110  # SRA / SRL
        if funct3 == 0b110:
            return 0b0011  # OR/ORI
        if funct3 == 0b111:
            return 0b0010  # AND/ANDI
        return 0b0000
    return 0b0000  # ALUOp==11 (LUI etc.) -> don't-care, default ADD


# ---------------------------------------------------------------------------
# register_file.sv
# ---------------------------------------------------------------------------
class RegisterFile:
    def __init__(self):
        self.regs = [0] * 32

    def read(self, rs1: int, rs2: int):
        rs1_data = self.regs[rs1] if rs1 != 0 else 0
        rs2_data = self.regs[rs2] if rs2 != 0 else 0
        return rs1_data, rs2_data

    def write(self, ws: int, rd: int, rd_data: int):
        """Synchronous write (posedge clk), mirrors always_ff block."""
        if ws and rd != 0:
            self.regs[rd] = rd_data & MASK32

    def reset(self):
        self.regs = [0] * 32


# ---------------------------------------------------------------------------
# data_mem.sv
# ---------------------------------------------------------------------------
class DataMem:
    """Byte-addressed, word-aligned memory: DEPTH words of 4 bytes each."""

    def __init__(self, depth_words: int = 2048):
        self.depth = depth_words
        self.mem = [0] * depth_words  # each entry: 32-bit word

    def read(self, addr: int, MemRead: int) -> int:
        if not MemRead:
            return 0
        location = (addr & MASK32) >> 2
        if location >= self.depth:
            return 0  # RTL would actually index out of bounds; guard for the model
        return self.mem[location]

    def write(self, addr: int, MemWrite: int, write_data: int, byte_enable: int):
        """Synchronous write (posedge clk), mirrors always_ff block."""
        if not MemWrite:
            return
        location = (addr & MASK32) >> 2
        if location >= self.depth:
            return
        word = self.mem[location]
        wd = write_data & MASK32
        b = list(word.to_bytes(4, "little"))
        src = list(wd.to_bytes(4, "little"))
        for i in range(4):
            if byte_enable & (1 << i):
                b[i] = src[i]
        self.mem[location] = int.from_bytes(bytes(b), "little")


# ---------------------------------------------------------------------------
# instruction_mem.sv
# ---------------------------------------------------------------------------
class InstructionMem:
    def __init__(self, depth_words: int = 256):
        self.depth = depth_words
        self.mem = [0] * depth_words

    def load_hex(self, path: str):
        words = []
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("//"):
                    continue
                words.append(int(line, 16) & MASK32)
        for i, w in enumerate(words):
            if i >= self.depth:
                break
            self.mem[i] = w

    def fetch(self, addr: int) -> int:
        location = (addr & MASK32) >> 2
        if location <= self.depth - 1:
            return self.mem[location]
        return 0


# ---------------------------------------------------------------------------
# cpu.sv -- top level single-cycle datapath
# ---------------------------------------------------------------------------
OPC_R      = 0b0110011
OPC_I      = 0b0010011
OPC_LOAD   = 0b0000011
OPC_STORE  = 0b0100011
OPC_BRANCH = 0b1100011
OPC_LUI    = 0b0110111
OPC_AUIPC  = 0b0010111
OPC_JAL    = 0b1101111
OPC_JALR   = 0b1100111


@dataclass
class CycleTrace:
    """Snapshot of interesting signals for one cycle, useful for RTL comparison."""
    pc: int = 0
    instruction: int = 0
    opcode: int = 0
    funct3: int = 0
    funct7: int = 0
    rs1: int = 0
    rs2: int = 0
    rd: int = 0
    imm: int = 0
    rs1_data: int = 0
    rs2_data: int = 0
    alu_a: int = 0
    alu_b: int = 0
    alu_op: int = 0
    alu_result: int = 0
    zflag: int = 0
    lsflag: int = 0
    lssflag: int = 0
    mem_data: int = 0
    load_data: int = 0
    rd_data: int = 0
    RegWrite: int = 0
    MemRead: int = 0
    MemWrite: int = 0
    MemtoReg: int = 0
    ALUSrc: int = 0
    ALUOp: int = 0
    Branch: int = 0
    Jump: int = 0
    ByteEnable: int = 0
    PCSrc: int = 0
    pc_next: int = 0


class CPU:
    def __init__(self, imem_depth=256, dmem_depth=2048):
        self.pc = 0
        self.imem = InstructionMem(imem_depth)
        self.dmem = DataMem(dmem_depth)
        self.rf = RegisterFile()

    def load_program(self, hex_path: str):
        self.imem.load_hex(hex_path)

    def reset(self):
        self.pc = 0
        self.rf.reset()

    # -- combinational logic for the current pc / register state -----------
    def _combinational(self) -> CycleTrace:
        t = CycleTrace()
        t.pc = self.pc

        instruction = self.imem.fetch(self.pc)
        t.instruction = instruction

        d = decode(instruction)
        t.opcode, t.funct3, t.funct7 = d.opcode, d.funct3, d.funct7
        t.rs1, t.rs2, t.rd, t.imm = d.rs1, d.rs2, d.rd, d.imm

        ctrl = control_unit(d.opcode)
        t.RegWrite, t.MemRead, t.MemWrite = ctrl.RegWrite, ctrl.MemRead, ctrl.MemWrite
        t.MemtoReg, t.ALUSrc, t.ALUOp = ctrl.MemtoReg, ctrl.ALUSrc, ctrl.ALUOp
        t.Branch, t.Jump = ctrl.Branch, ctrl.Jump

        alu_op = alu_control(ctrl.ALUOp, d.funct3, d.funct7)
        t.alu_op = alu_op

        rs1_data, rs2_data = self.rf.read(d.rs1, d.rs2)
        t.rs1_data, t.rs2_data = rs1_data, rs2_data

        # alu_a = pc for AUIPC, else rs1_data
        alu_a = self.pc if d.opcode == OPC_AUIPC else rs1_data
        alu_b = d.imm if ctrl.ALUSrc else rs2_data
        t.alu_a, t.alu_b = alu_a, alu_b

        alu_result, zflag, lsflag, lssflag = alu(alu_a, alu_b, alu_op)
        t.alu_result, t.zflag, t.lsflag, t.lssflag = alu_result, zflag, lsflag, lssflag

        # ByteEnable + store-data alignment.
        # ByteEnable selection mirrors cpu.sv (including its assumption of
        # natural alignment: SH only looks at alu_result[1], not [0]).
        # store_data is *shifted into the correct lane* before being handed
        # to data_mem (fixed: the original RTL wired rs2_data directly into
        # write_data with no pre-shift, so data_mem's fixed per-lane slice
        # of write_data picked up the wrong bits for any offset != 0).
        if ctrl.MemWrite:
            if d.funct3 == 0b010:          # SW
                byte_enable = 0b1111
                store_data = rs2_data & MASK32
            elif d.funct3 == 0b001:        # SH
                half_lane = alu_result & 0x2          # 0 or 2
                byte_enable = 0b0011 if half_lane == 0 else 0b1100
                store_data = ((rs2_data & 0xFFFF) << (8 * half_lane)) & MASK32
            elif d.funct3 == 0b000:        # SB
                byte_lane = alu_result & 0x3           # 0..3
                byte_enable = (0b0001 << byte_lane) & 0xF
                store_data = ((rs2_data & 0xFF) << (8 * byte_lane)) & MASK32
            else:
                byte_enable = 0b0000
                store_data = 0
        else:
            byte_enable = 0b0000
            store_data = 0
        t.ByteEnable = byte_enable

        mem_data = self.dmem.read(alu_result, ctrl.MemRead)
        t.mem_data = mem_data

        # Load data extraction/extension mux (fixed: LB/LH/LBU/LHU now
        # extract and extend the addressed byte/halfword instead of
        # returning the raw 32-bit word for every load).
        byte_off = alu_result & 0x3
        half_off = (alu_result >> 1) & 0x1  # which halfword within the word
        if d.opcode == OPC_LOAD:
            if d.funct3 == 0b000:      # LB
                byte = (mem_data >> (8 * byte_off)) & 0xFF
                load_data = sext(byte, 8)
            elif d.funct3 == 0b001:    # LH
                half = (mem_data >> (16 * half_off)) & 0xFFFF
                load_data = sext(half, 16)
            elif d.funct3 == 0b010:    # LW
                load_data = mem_data
            elif d.funct3 == 0b100:    # LBU
                load_data = (mem_data >> (8 * byte_off)) & 0xFF
            elif d.funct3 == 0b101:    # LHU
                load_data = (mem_data >> (16 * half_off)) & 0xFFFF
            else:
                load_data = mem_data
        else:
            load_data = mem_data
        t.load_data = load_data

        pc_plus4 = (self.pc + 4) & MASK32
        pc_branch = (self.pc + d.imm) & MASK32
        # JALR target has its LSB cleared per the RV32I spec (fixed: was
        # previously left un-masked, allowing odd/illegal PC values).
        pc_jump_target = (((rs1_data + d.imm) & MASK32) & ~1 & MASK32) if d.opcode == OPC_JALR else pc_branch

        if d.funct3 == 0b000:
            pcsrc = ctrl.Branch & zflag          # BEQ
        elif d.funct3 == 0b001:
            pcsrc = ctrl.Branch & (zflag ^ 1)    # BNE
        elif d.funct3 == 0b100:
            pcsrc = ctrl.Branch & lssflag        # BLT
        elif d.funct3 == 0b101:
            pcsrc = ctrl.Branch & (lssflag ^ 1)  # BGE
        elif d.funct3 == 0b110:
            pcsrc = ctrl.Branch & lsflag         # BLTU
        elif d.funct3 == 0b111:
            pcsrc = ctrl.Branch & (lsflag ^ 1)   # BGEU
        else:
            pcsrc = 0
        t.PCSrc = pcsrc

        if ctrl.Jump:
            pc_next = pc_jump_target
        elif pcsrc:
            pc_next = pc_branch
        else:
            pc_next = pc_plus4
        t.pc_next = pc_next

        if ctrl.MemtoReg == 0b00:
            rd_data = alu_result
        elif ctrl.MemtoReg == 0b01:
            rd_data = load_data
        elif ctrl.MemtoReg == 0b10:
            rd_data = d.imm
        else:  # 0b11
            rd_data = pc_plus4
        t.rd_data = rd_data

        # stash extra fields needed by step() that aren't in CycleTrace's dataclass repr
        t._alu_result_for_mem = alu_result
        t._store_data_for_mem = store_data
        return t

    def step(self) -> CycleTrace:
        """Advance the CPU by exactly one clock cycle (one posedge clk)."""
        t = self._combinational()

        # Synchronous updates (all happen "simultaneously" on posedge clk)
        self.dmem.write(t._alu_result_for_mem, t.MemWrite, t._store_data_for_mem, t.ByteEnable)
        self.rf.write(t.RegWrite, t.rd, t.rd_data)
        self.pc = t.pc_next & MASK32

        return t

    def run(self, max_steps: int = 10000, stop_on_self_loop: bool = True, verbose: bool = False):
        trace = []
        prev_pc = None
        for i in range(max_steps):
            t = self.step()
            trace.append(t)
            if verbose:
                self._print_cycle(i, t)
            if stop_on_self_loop and t.pc_next == t.pc:
                # e.g. `jal x0, 0` -- infinite self loop, treat as program end
                break
            prev_pc = t.pc
        return trace

    @staticmethod
    def _print_cycle(i: int, t: CycleTrace):
        print(f"[{i:4d}] pc={t.pc:#010x} instr={t.instruction:#010x} "
              f"opc={t.opcode:07b} rd=x{t.rd:<2d} rs1=x{t.rs1:<2d} rs2=x{t.rs2:<2d} "
              f"imm={to_signed32(t.imm):<8d} alu_op={t.alu_op:04b} "
              f"alu_res={t.alu_result:#010x} rd_data={t.rd_data:#010x} "
              f"RegWrite={t.RegWrite} MemWrite={t.MemWrite} MemRead={t.MemRead} "
              f"Branch={t.Branch} Jump={t.Jump} pc_next={t.pc_next:#010x}")

    def dump_regs(self):
        for i in range(0, 32, 4):
            row = "  ".join(f"x{i+j:<2d}={self.rf.regs[i+j]:#010x}" for j in range(4))
            print(row)

    def dump_mem(self, words: int = 16):
        for i in range(words):
            print(f"mem[{i:#06x}] = {self.dmem.mem[i]:#010x}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Golden reference model for the RV32I single-cycle CPU")
    ap.add_argument("hexfile", help="Path to program.hex ($readmemh-format instruction memory image)")
    ap.add_argument("--steps", type=int, default=10000, help="Max cycles to run")
    ap.add_argument("-v", "--verbose", action="store_true", help="Print a cycle-by-cycle trace")
    ap.add_argument("--no-stop", action="store_true", help="Don't stop automatically on a self-loop (jal x0,0)")
    ap.add_argument("--dump-mem-words", type=int, default=8, help="How many data-memory words to dump at the end")
    args = ap.parse_args()

    cpu = CPU()
    cpu.load_program(args.hexfile)
    cpu.reset()

    cpu.run(max_steps=args.steps, stop_on_self_loop=not args.no_stop, verbose=args.verbose)

    print("\n=== Final register file ===")
    cpu.dump_regs()
    print(f"\n=== Final PC === {cpu.pc:#010x}")
    print(f"\n=== First {args.dump_mem_words} data memory words ===")
    cpu.dump_mem(args.dump_mem_words)


if __name__ == "__main__":
    main()
