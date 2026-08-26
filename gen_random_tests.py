#!/usr/bin/env python3
"""
Random RV32I instruction/program generator for cross-checking the RTL
against golden_model.py.

For each generated test case this script writes:
    tests/<name>/program.hex    -- $readmemh-format instruction image
    tests/<name>/expected.txt   -- architectural state after running the
                                    golden model to completion (see DUMP
                                    FORMAT below)

Run the exact same program.hex through the RTL (see tb_cpu.sv), have the
testbench emit an actual.txt in the same format, then use compare_dumps.py
to diff expected.txt vs actual.txt.

-----------------------------------------------------------------------
SAFETY GUARANTEES (so RTL and golden model can't diverge for reasons
that have nothing to do with a real bug):
  - All branches / JAL / JALR targets are chosen FORWARD-ONLY within the
    program, so every generated program is guaranteed to terminate by
    falling into the trailing `jal x0,0` self-loop -- no infinite loops,
    no need to guess a cycle budget.
  - Loads/stores always use `x0 + offset` as the address (x0 is
    architecturally hard-wired to 0), with the offset kept within a
    small SAFE_MEM_BYTES window and naturally aligned for its width.
    This means addresses are always in-bounds and reproducible without
    needing to track live register values through the program.
  - x30 is reserved as a scratch "jump target" register for JALR (it is
    loaded with `addi x30, x0, T` immediately before every JALR) and is
    excluded from the general random operand pool so nothing else can
    clobber it.
  - x0 is occasionally (deliberately, at low probability) chosen as an
    ALU destination register, to test that writes to x0 are correctly
    discarded by both implementations.
-----------------------------------------------------------------------

DUMP FORMAT (expected.txt / actual.txt), one record per line:
    PC <8 hex digits>
    REG <2 decimal digits, 00-31> <8 hex digits>     (32 lines, x0..x31)
    MEM <4 hex digits (word index)> <8 hex digits>   (DUMP_MEM_WORDS lines)
    CYCLES <decimal>
"""

from __future__ import annotations
import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from golden_model import CPU, MASK32, to_signed32  # noqa: E402

MASK32_ = 0xFFFFFFFF

# ---------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------
SAFE_MEM_BYTES = 256          # loads/stores confined to [0, SAFE_MEM_BYTES)
RESERVED_REGS = {30}          # excluded from the random operand pool
DUMP_MEM_WORDS = SAFE_MEM_BYTES // 4

OPC_R, OPC_I, OPC_LOAD, OPC_STORE = 0b0110011, 0b0010011, 0b0000011, 0b0100011
OPC_BRANCH, OPC_LUI, OPC_AUIPC, OPC_JAL, OPC_JALR = (
    0b1100011, 0b0110111, 0b0010111, 0b1101111, 0b1100111,
)


# ---------------------------------------------------------------------
# Encoders
# ---------------------------------------------------------------------
def enc_r(funct7, rs2, rs1, funct3, rd, opcode=OPC_R):
    return (funct7 << 25) | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode


def enc_i(imm, rs1, funct3, rd, opcode=OPC_I):
    return ((imm & 0xFFF) << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode


def enc_i_shift(shamt, funct7, rs1, funct3, rd, opcode=OPC_I):
    return (funct7 << 25) | ((shamt & 0x1F) << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode


def enc_s(imm, rs2, rs1, funct3, opcode=OPC_STORE):
    imm &= 0xFFF
    return ((imm >> 5) << 25) | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | ((imm & 0x1F) << 7) | opcode


def enc_b(imm, rs2, rs1, funct3, opcode=OPC_BRANCH):
    imm &= 0x1FFF
    b12 = (imm >> 12) & 1
    b11 = (imm >> 11) & 1
    b10_5 = (imm >> 5) & 0x3F
    b4_1 = (imm >> 1) & 0xF
    return (b12 << 31) | (b10_5 << 25) | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | (b4_1 << 8) | (b11 << 7) | opcode


def enc_u(imm20, rd, opcode):
    return ((imm20 & 0xFFFFF) << 12) | (rd << 7) | opcode


def enc_j(imm, rd, opcode=OPC_JAL):
    imm &= 0x1FFFFF
    b20 = (imm >> 20) & 1
    b19_12 = (imm >> 12) & 0xFF
    b11 = (imm >> 11) & 1
    b10_1 = (imm >> 1) & 0x3FF
    return (b20 << 31) | (b10_1 << 21) | (b11 << 20) | (b19_12 << 12) | (rd << 7) | opcode


def nop():
    return enc_i(0, 0, 0b000, 0, OPC_I)  # addi x0, x0, 0


def jal_self_loop():
    return enc_j(0, 0, OPC_JAL)


# ---------------------------------------------------------------------
# Random operand helpers
# ---------------------------------------------------------------------
def rand_reg(rng: random.Random, allow_x0_bias=0.05) -> int:
    """A random register 1..31, excluding RESERVED_REGS, with a small
    chance of x0 (to test writes-to-x0-are-discarded)."""
    if rng.random() < allow_x0_bias:
        return 0
    pool = [r for r in range(1, 32) if r not in RESERVED_REGS]
    return rng.choice(pool)


def rand_imm12(rng: random.Random) -> int:
    return rng.randint(-2048, 2047)


# ---------------------------------------------------------------------
# Instruction generators (each returns a list of 1+ 32-bit words)
# ---------------------------------------------------------------------
R_OPS = [  # (funct3, funct7, name)
    (0b000, 0b0000000, "add"), (0b000, 0b0100000, "sub"),
    (0b001, 0b0000000, "sll"), (0b010, 0b0000000, "slt"),
    (0b011, 0b0000000, "sltu"), (0b100, 0b0000000, "xor"),
    (0b101, 0b0000000, "srl"), (0b101, 0b0100000, "sra"),
    (0b110, 0b0000000, "or"), (0b111, 0b0000000, "and"),
]

I_ARITH_OPS = [  # (funct3, name) -- non-shift I-type arithmetic
    (0b000, "addi"), (0b010, "slti"), (0b011, "sltiu"),
    (0b100, "xori"), (0b110, "ori"), (0b111, "andi"),
]

BRANCH_OPS = [0b000, 0b001, 0b100, 0b101, 0b110, 0b111]  # beq bne blt bge bltu bgeu

LOAD_WIDTHS = [(0b010, 4, "lw"), (0b001, 2, "lh"), (0b101, 2, "lhu"),
               (0b000, 1, "lb"), (0b100, 1, "lbu")]
STORE_WIDTHS = [(0b010, 4, "sw"), (0b001, 2, "sh"), (0b000, 1, "sb")]


def gen_r_type(rng):
    funct3, funct7, _ = rng.choice(R_OPS)
    rd, rs1, rs2 = rand_reg(rng), rand_reg(rng), rand_reg(rng)
    return [enc_r(funct7, rs2, rs1, funct3, rd)]


def gen_i_arith(rng):
    funct3, _ = rng.choice(I_ARITH_OPS)
    rd, rs1 = rand_reg(rng), rand_reg(rng)
    imm = rand_imm12(rng)
    return [enc_i(imm, rs1, funct3, rd)]


def gen_shift_imm(rng):
    is_sra = rng.random() < 0.5
    rd, rs1 = rand_reg(rng), rand_reg(rng)
    shamt = rng.randint(0, 31)
    funct3 = 0b101 if rng.random() < 0.5 else 0b001  # srli/srai vs slli
    funct7 = 0b0100000 if (funct3 == 0b101 and is_sra) else 0b0000000
    return [enc_i_shift(shamt, funct7, rs1, funct3, rd)]


def gen_lui_auipc(rng):
    opcode = rng.choice([OPC_LUI, OPC_AUIPC])
    rd = rand_reg(rng)
    imm20 = rng.randint(0, 0xFFFFF)
    return [enc_u(imm20, rd, opcode)]


def gen_store(rng):
    funct3, width, _ = rng.choice(STORE_WIDTHS)
    rs2 = rand_reg(rng)
    max_off = SAFE_MEM_BYTES - width
    off = rng.randrange(0, max_off + 1, width)  # naturally aligned
    return [enc_s(off, rs2, 0, funct3)]  # rs1 = x0 (always 0) -> safe address


def gen_load(rng):
    funct3, width, _ = rng.choice(LOAD_WIDTHS)
    rd = rand_reg(rng)
    max_off = SAFE_MEM_BYTES - width
    off = rng.randrange(0, max_off + 1, width)
    return [enc_i(off, 0, funct3, rd, OPC_LOAD)]  # rs1 = x0 -> safe address


def gen_branch(rng, cur_idx: int, valid_targets: list):
    """Forward-only branch: target must be the start index of some real
    instruction (never the interior word of a multi-word instruction)."""
    funct3 = rng.choice(BRANCH_OPS)
    rs1, rs2 = rand_reg(rng), rand_reg(rng)
    target_idx = rng.choice(valid_targets)
    imm = (target_idx - cur_idx) * 4
    return [enc_b(imm, rs2, rs1, funct3)]


def gen_jal(rng, cur_idx: int, valid_targets: list):
    rd = rand_reg(rng)
    target_idx = rng.choice(valid_targets)
    imm = (target_idx - cur_idx) * 4
    return [enc_j(imm, rd)]


def gen_jalr(rng, cur_idx: int, valid_targets: list):
    """Set x30 = target*4 (occasionally +1, to exercise LSB-clearing),
    then jalr through it. Two instructions."""
    rd = rand_reg(rng)
    target_idx = rng.choice(valid_targets)
    target_addr = target_idx * 4
    make_odd = rng.random() < 0.3
    load_val = target_addr + 1 if make_odd else target_addr
    setup = enc_i(load_val, 0, 0b000, 30)             # addi x30, x0, load_val
    jump = enc_i(0, 30, 0b000, rd, OPC_JALR)          # jalr rd, 0(x30)
    return [setup, jump]


# ---------------------------------------------------------------------
# Program assembly
# ---------------------------------------------------------------------
# Weighted mix of instruction-generator "kinds". Branch/jal/jalr are
# handled specially since they need to know their own index and the
# total instruction count, which isn't known until the whole skeleton
# is laid out -- see build_program().
KIND_WEIGHTS = {
    "r": 5, "i_arith": 5, "shift": 2, "lui_auipc": 1,
    "load": 3, "store": 3, "branch": 2, "jal": 1, "jalr": 1,
}


def build_program(rng: random.Random, n_body_instrs: int):
    """Build a list of 32-bit words. Control-flow instructions are
    inserted as placeholders first (so we know how many *word slots*
    the whole program occupies including multi-word jalr sequences),
    then resolved to real encodings once final indices are fixed.

    Crucially, branch/jal/jalr targets are restricted to the *start*
    index of some real instruction -- never the interior word of a
    multi-word instruction (only jalr is 2 words: `addi x30,..` then
    `jalr`). Landing on the bare `jalr` word alone would execute it
    against a stale/garbage x30 and could jump backward, breaking the
    forward-only termination guarantee.
    """
    kinds = list(KIND_WEIGHTS.keys())
    weights = list(KIND_WEIGHTS.values())

    # First pass: decide the sequence of kinds and how many words each
    # takes (jalr = 2 words, everything else = 1), to fix instruction
    # boundaries up front.
    plan = []
    total_words = 0
    while total_words < n_body_instrs:
        kind = rng.choices(kinds, weights=weights, k=1)[0]
        words_used = 2 if kind == "jalr" else 1
        if total_words + words_used > n_body_instrs:
            continue
        plan.append((kind, total_words))
        total_words += words_used

    self_loop_idx = total_words  # index (in words) of the trailing jal x0,0

    # Valid jump targets: the start of every planned instruction, plus
    # the trailing self-loop itself. Sorted ascending so "forward from
    # cur_idx" is a simple filter.
    valid_starts = sorted([idx for _, idx in plan] + [self_loop_idx])

    def forward_targets(cur_idx):
        opts = [t for t in valid_starts if t > cur_idx]
        return opts if opts else [self_loop_idx]

    program = []
    for kind, idx in plan:
        if kind == "r":
            program += gen_r_type(rng)
        elif kind == "i_arith":
            program += gen_i_arith(rng)
        elif kind == "shift":
            program += gen_shift_imm(rng)
        elif kind == "lui_auipc":
            program += gen_lui_auipc(rng)
        elif kind == "load":
            program += gen_load(rng)
        elif kind == "store":
            program += gen_store(rng)
        elif kind == "branch":
            program += gen_branch(rng, idx, forward_targets(idx))
        elif kind == "jal":
            program += gen_jal(rng, idx, forward_targets(idx))
        elif kind == "jalr":
            # jalr occupies idx and idx+1 (addi, jalr); the jump itself
            # is "at" idx+1 for forward-target purposes, but must not
            # target idx+1 (itself) or anything <= idx+1.
            program += gen_jalr(rng, idx, forward_targets(idx + 1))

    assert len(program) == self_loop_idx, (len(program), self_loop_idx)
    program.append(jal_self_loop())
    return program


# ---------------------------------------------------------------------
# Golden-model execution + dump
# ---------------------------------------------------------------------
def run_golden_and_dump(words, dump_path, imem_depth=256, dmem_depth=2048, max_steps=100000):
    cpu = CPU(imem_depth=imem_depth, dmem_depth=dmem_depth)
    cpu.imem.mem[:len(words)] = words
    cpu.reset()

    trace = cpu.run(max_steps=max_steps, stop_on_self_loop=True, verbose=False)

    with open(dump_path, "w") as f:
        f.write(f"PC {cpu.pc:08x}\n")
        for i in range(32):
            f.write(f"REG {i:02d} {cpu.rf.regs[i] & MASK32_:08x}\n")
        for i in range(DUMP_MEM_WORDS):
            f.write(f"MEM {i:04x} {cpu.dmem.mem[i] & MASK32_:08x}\n")
        f.write(f"CYCLES {len(trace)}\n")

    return cpu, trace


def write_hex(words, path):
    with open(path, "w") as f:
        for w in words:
            f.write(f"{w & MASK32_:08x}\n")


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Generate random RV32I test programs + golden-model reference dumps")
    ap.add_argument("--count", type=int, default=20, help="Number of test programs to generate")
    ap.add_argument("--instrs", type=int, default=40, help="Approx. body instructions per program (excludes trailing self-loop)")
    ap.add_argument("--seed", type=int, default=None, help="Base RNG seed (for reproducibility). Each test uses seed+i.")
    ap.add_argument("--outdir", default="tests", help="Output directory")
    ap.add_argument("--max-steps", type=int, default=100000, help="Golden-model step budget per test (safety net)")
    args = ap.parse_args()

    base_seed = args.seed if args.seed is not None else random.randint(0, 2**31 - 1)
    os.makedirs(args.outdir, exist_ok=True)
    manifest = {"base_seed": base_seed, "count": args.count, "instrs": args.instrs, "tests": []}

    for i in range(args.count):
        seed = base_seed + i
        rng = random.Random(seed)
        name = f"test_{i:04d}"
        test_dir = os.path.join(args.outdir, name)
        os.makedirs(test_dir, exist_ok=True)

        words = build_program(rng, args.instrs)
        hex_path = os.path.join(test_dir, "program.hex")
        write_hex(words, hex_path)

        expected_path = os.path.join(test_dir, "expected.txt")
        cpu, trace = run_golden_and_dump(words, expected_path, max_steps=args.max_steps)

        manifest["tests"].append({
            "name": name, "seed": seed, "n_words": len(words),
            "cycles": len(trace), "final_pc": f"{cpu.pc:08x}",
        })
        print(f"[{name}] seed={seed} words={len(words)} cycles={len(trace)} final_pc={cpu.pc:#010x}")

    with open(os.path.join(args.outdir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\nWrote {args.count} test cases to {args.outdir}/ (see manifest.json)")


if __name__ == "__main__":
    main()
