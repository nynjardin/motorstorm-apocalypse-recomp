"""Disassemble guest code of a title's EBOOT.elf.   dis.py <title> <addr hex> [n instructions=40] [...]

    python scripts/dis.py BCES00484_106 0xE9B9DC 30 0x63C1D4 50

Reads game/<title>/EBOOT.elf (PT_LOAD segments), capstone PPC64 big endian.
"""
import os, struct, sys
from capstone import Cs, CS_ARCH_PPC, CS_MODE_64, CS_MODE_BIG_ENDIAN

here = os.path.dirname(os.path.abspath(__file__))
title = sys.argv[1]
d = open(os.path.join(here, '..', 'game', title, 'EBOOT.elf'), 'rb').read()
ph = struct.unpack('>Q', d[0x20:0x28])[0]
n = struct.unpack('>H', d[0x38:0x3a])[0]
segs = []
for i in range(n):
    t, fl, off, va, pa, fs, ms, al = struct.unpack('>IIQQQQQQ', d[ph + i * 56:ph + i * 56 + 56])
    if t == 1 and fs:
        segs.append((va, off, fs))
md = Cs(CS_ARCH_PPC, CS_MODE_64 | CS_MODE_BIG_ENDIAN)
args = sys.argv[2:]
for a, cnt in zip(args[::2], args[1::2] if len(args) > 1 else []):
    addr, cnt = int(a, 0), int(cnt)
    for va, off, fs in segs:
        if va <= addr < va + fs:
            code = d[off + addr - va: off + addr - va + cnt * 4]
            print('----', hex(addr))
            for ins in md.disasm(code, addr):
                print('  %08X  %-8s %s' % (ins.address, ins.mnemonic, ins.op_str))
            break
