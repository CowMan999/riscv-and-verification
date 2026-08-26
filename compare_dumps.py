#!/usr/bin/env python3
"""
Compare two state dumps (as produced by golden_model's dump / gen_random_tests's
expected.txt, and tb_cpu.sv's actual.txt) and report any mismatches.

Format-agnostic about digit widths/leading zeros: every value is parsed as an
integer, so "REG 01 ..." and "REG 1 ..." are treated the same.

Usage:
    python3 compare_dumps.py expected.txt actual.txt
    python3 compare_dumps.py tests/ --actual-name actual.txt   # batch mode
"""
import argparse
import glob
import os
import sys


def parse_dump(path):
    """Returns dict: {'PC': int, 'REG': {idx:int -> val:int}, 'MEM': {idx:int -> val:int}, 'CYCLES': int}"""
    d = {"PC": None, "REG": {}, "MEM": {}, "CYCLES": None}
    with open(path) as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            tag = parts[0]
            if tag == "PC":
                d["PC"] = int(parts[1], 16)
            elif tag == "REG":
                d["REG"][int(parts[1])] = int(parts[2], 16)
            elif tag == "CYCLES":
                d["CYCLES"] = int(parts[1])
            elif tag == "MEM":
                d["MEM"][int(parts[1], 16)] = int(parts[2], 16)
            else:
                print(f"WARNING: {path}:{lineno}: unrecognized line: {line!r}", file=sys.stderr)
    return d


def diff_dumps(expected, actual):
    """Returns a list of human-readable mismatch strings; empty list == match."""
    mismatches = []

    if expected["PC"] is not None and actual["PC"] is not None:
        if expected["PC"] != actual["PC"]:
            mismatches.append(f"PC: expected {expected['PC']:#010x}, got {actual['PC']:#010x}")

    for idx in sorted(expected["REG"]):
        if idx not in actual["REG"]:
            mismatches.append(f"x{idx}: missing from actual dump")
            continue
        ev, av = expected["REG"][idx], actual["REG"][idx]
        if ev != av:
            mismatches.append(f"x{idx}: expected {ev:#010x}, got {av:#010x}")

    for idx in sorted(expected["MEM"]):
        if idx not in actual["MEM"]:
            mismatches.append(f"mem[{idx:#06x}]: missing from actual dump")
            continue
        ev, av = expected["MEM"][idx], actual["MEM"][idx]
        if ev != av:
            mismatches.append(f"mem[{idx:#06x}]: expected {ev:#010x}, got {av:#010x}")

    if expected["CYCLES"] is not None and actual["CYCLES"] is not None:
        if expected["CYCLES"] != actual["CYCLES"]:
            mismatches.append(f"CYCLES: expected {expected['CYCLES']}, got {actual['CYCLES']}")

    return mismatches


def compare_one(expected_path, actual_path, verbose=True):
    if not os.path.exists(actual_path):
        if verbose:
            print(f"FAIL {actual_path}: file not found (did the RTL sim run?)")
        return False
    expected = parse_dump(expected_path)
    actual = parse_dump(actual_path)
    mismatches = diff_dumps(expected, actual)
    if mismatches:
        if verbose:
            print(f"FAIL {actual_path} ({len(mismatches)} mismatch(es)):")
            for m in mismatches[:20]:
                print(f"    {m}")
            if len(mismatches) > 20:
                print(f"    ... and {len(mismatches) - 20} more")
        return False
    if verbose:
        print(f"PASS {actual_path}")
    return True


def main():
    ap = argparse.ArgumentParser(description="Compare golden-model and RTL state dumps")
    ap.add_argument("target", help="Either a single expected.txt file, or a tests/ directory for batch mode")
    ap.add_argument("actual", nargs="?", help="Single actual.txt file (non-batch mode only)")
    ap.add_argument("--actual-name", default="actual.txt", help="Filename to look for in each test subdir (batch mode)")
    ap.add_argument("--expected-name", default="expected.txt", help="Filename to look for in each test subdir (batch mode)")
    args = ap.parse_args()

    if os.path.isdir(args.target):
        test_dirs = sorted(glob.glob(os.path.join(args.target, "test_*")))
        if not test_dirs:
            print(f"No test_* subdirectories found in {args.target}", file=sys.stderr)
            sys.exit(2)
        n_pass = 0
        n_fail = 0
        for td in test_dirs:
            expected_path = os.path.join(td, args.expected_name)
            actual_path = os.path.join(td, args.actual_name)
            if not os.path.exists(expected_path):
                print(f"SKIP {td}: no {args.expected_name}")
                continue
            ok = compare_one(expected_path, actual_path)
            n_pass += ok
            n_fail += not ok
        print(f"\n{n_pass} passed, {n_fail} failed, {len(test_dirs)} total")
        sys.exit(1 if n_fail else 0)
    else:
        if not args.actual:
            print("Non-batch mode requires: compare_dumps.py expected.txt actual.txt", file=sys.stderr)
            sys.exit(2)
        ok = compare_one(args.target, args.actual)
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
