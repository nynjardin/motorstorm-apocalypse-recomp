"""Walk a raw RSX fragment program (NV40 ucode) the way the toolkit does, offline.

    python scripts/fp_walk.py <file.bin> [--list]
    python scripts/fp_walk.py --live <guest ea> [--save <file.bin>] [--list]

--live reads 64 KB of the running game (the backend walks up to 0x10000 bytes since patch #57) (scripts/guest_peek.py machinery); a program in local
memory (SET_SHADER_PROGRAM value 0x0C40B3C1) lives at guest 0xC0000000 + (value & ~3).

Prints, for the three walks of rsx_fp_decompiler.c that must agree:
  units   rsx_fp_texture_units()  (constant skipped unless the instruction is a branch)
  decomp  the decompiler          (constant skipped whenever a source is CONST)
  hash    rsx_fp_code_hash()      (as units)
the texture units each one sees, the program size, and the first instruction where they part.
--list prints every instruction (offset, opcode, unit, constant, END).
"""
import struct, sys

OPS = {0x00: "NOP", 0x01: "MOV", 0x02: "MUL", 0x03: "ADD", 0x04: "MAD", 0x05: "DP3", 0x06: "DP4",
       0x07: "DST", 0x08: "MIN", 0x09: "MAX", 0x0A: "SLT", 0x0B: "SGE", 0x0C: "SLE", 0x0D: "SGT",
       0x0E: "SNE", 0x0F: "SEQ", 0x10: "FRC", 0x11: "FLR", 0x12: "KIL", 0x13: "PK4B", 0x14: "UP4B",
       0x15: "DDX", 0x16: "DDY", 0x17: "TEX", 0x18: "TXP", 0x19: "TXD", 0x1A: "RCP", 0x1B: "RSQ",
       0x1C: "EX2", 0x1D: "LG2", 0x1E: "LIT", 0x1F: "LRP", 0x20: "STR", 0x21: "SFL", 0x22: "COS",
       0x23: "SIN", 0x24: "PK2H", 0x25: "UP2H", 0x26: "POW", 0x27: "PK4UB", 0x28: "UP4UB",
       0x29: "PK2US", 0x2A: "UP2US", 0x2C: "PKG", 0x2D: "UPG", 0x2E: "DP2A", 0x2F: "TXL",
       0x31: "TXB", 0x33: "TEXBEM", 0x34: "TXPBEM", 0x36: "RFL", 0x38: "DP2", 0x39: "NRM",
       0x3A: "DIV", 0x3B: "DIVSQ", 0x3C: "LIF", 0x3D: "FENCT", 0x3E: "FENCB"}
TEXOPS = {0x17, 0x18, 0x31, 0x2F, 0x19, 0x33, 0x34}


def word(b, off):
    be = struct.unpack_from(">I", b, off)[0]
    return ((be << 16) | (be >> 16)) & 0xFFFFFFFF


def walk(b, skip_on_branch, limit=0x10000):
    """-> (units, size, [(off, w0, w1, w2, w3, has_k)])"""
    units, off, ins = 0, 0, []
    while off + 16 <= min(limit, len(b)):
        w0, w1, w2, w3 = (word(b, off + 4 * i) for i in range(4))
        op = (w0 >> 24) & 63
        branch = (w2 >> 31) & 1
        if not branch and op in TEXOPS:
            units |= 1 << ((w0 >> 17) & 15)
        k = (w1 & 3) == 2 or (w2 & 3) == 2 or (w3 & 3) == 2
        has_k = k and (skip_on_branch or not branch)
        ins.append((off, w0, w1, w2, w3, has_k))
        off += 16
        if has_k:
            off += 16
        if w0 & 1:
            return units, off, ins
    return units, 0, ins


def main():
    a = sys.argv[1:]
    lst = "--list" in a
    if lst:
        a.remove("--list")
    save = None
    if "--save" in a:
        i = a.index("--save"); save = a[i + 1]; del a[i:i + 2]
    if a and a[0] == "--scan":
        # --scan <start ea> <end ea> <units hex>[,<units hex>...] : programs of the running game
        # (0x40-aligned, >= 20 instructions) whose units, by either walk, are in the list.
        sys.path.insert(0, __import__("os").path.dirname(__file__))
        import guest_peek as gp
        import ctypes
        lo, hi = int(a[1], 0), int(a[2], 0)
        want = {int(x, 16) for x in a[3].split(",")}
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(gp.PROCESS_VM_READ | gp.PROCESS_QUERY_INFORMATION, False, gp.find_pid())
        base = gp.find_vm_base(h)
        CH = 1 << 20
        buf = (ctypes.c_ubyte * (CH + 4096))()
        got = ctypes.c_size_t()
        for ea in range(lo, hi, CH):
            if not k32.ReadProcessMemory(h, ctypes.c_void_p(base + ea), buf, CH + 4096, ctypes.byref(got)):
                if not k32.ReadProcessMemory(h, ctypes.c_void_p(base + ea), buf, CH, ctypes.byref(got)):
                    continue
            mem = bytes(buf[:got.value])
            for o in range(0, min(CH, len(mem)), 0x40):
                if mem[o:o + 16] == bytes(16):
                    continue
                u1, s1, i1 = walk(mem[o:o + 4096], False)
                if not s1 or len(i1) < 20:
                    continue
                u2, s2, i2 = walk(mem[o:o + 4096], True)
                if u1 in want or u2 in want:
                    print(f"0x{ea + o:08X}: units walk 0x{u1:04X} size {s1} / decomp walk 0x{u2:04X} size {s2}")
        return
    if a and a[0] == "--live":
        sys.path.insert(0, __import__("os").path.dirname(__file__))
        import guest_peek as gp
        import ctypes
        ea = int(a[1], 0)
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(gp.PROCESS_VM_READ | gp.PROCESS_QUERY_INFORMATION, False, gp.find_pid())
        if not h:
            sys.exit("OpenProcess failed")
        buf = (ctypes.c_ubyte * 0x10000)()
        got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(h, ctypes.c_void_p(gp.find_vm_base(h) + ea), buf, 0x10000, ctypes.byref(got)):
            sys.exit(f"0x{ea:08X}: unreadable")
        data = bytes(buf[:got.value])
        if save:
            open(save, "wb").write(data)
    else:
        data = open(a[0], "rb").read()
    u1, s1, i1 = walk(data, False)
    u2, s2, i2 = walk(data, True)
    # rsx_fp_structural_hash(ucode, 0x10000, FNV offset basis): the hash RSX_FP_DEBUG=<hash>:<n>:<reg> takes
    M = (1 << 64) - 1
    sh = 1469598103934665603
    def fnv(bs, hsh):
        for c in bs:
            hsh = ((hsh ^ c) * 1099511628211) & M
        return hsh
    sh = fnv(struct.pack("<I", 0x31535046), sh)
    for off, *_ in i2:
        sh = fnv(data[off:off + 16], sh)
    sh = fnv(struct.pack("<I", len(i2)), sh)
    sh = fnv(struct.pack("<I", sum(1 for i in i2 if i[5])), sh)
    print(f"structural hash (RSX_FP_DEBUG): {sh:016X}" if s2 else "structural hash: none (no END)")
    print(f"units  walk: units=0x{u1:04X} size={s1} instrs={len(i1)}")
    print(f"decomp walk: units=0x{u2:04X} size={s2} instrs={len(i2)}")
    for n, (x, y) in enumerate(zip(i1, i2)):
        if x != y:
            print(f"walks part at instruction {n}: units off=0x{x[0]:X} k={x[5]}, decomp off=0x{y[0]:X} k={y[5]}")
            break
    if lst:
        for off, w0, w1, w2, w3, k in i2:
            op = (w0 >> 24) & 63
            br = (w2 >> 31) & 1
            name = OPS.get(op, f"op{op:02X}") if not br else f"BR{op:02X}"
            unit = f" unit={(w0 >> 17) & 15}" if (op in TEXOPS and not br) else ""
            print(f"  +0x{off:03X} {name:6s}{unit:9s} w0={w0:08X} w1={w1:08X} w2={w2:08X} w3={w3:08X}"
                  f"{' K' if k else ''}{' END' if w0 & 1 else ''}")


if __name__ == "__main__":
    main()
