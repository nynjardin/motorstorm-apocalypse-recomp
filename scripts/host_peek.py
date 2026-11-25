"""Read HOST memory of a running MotorStormApocalypse.exe (no debugger, no pause).

    python scripts/host_peek.py <host addr> [<len>=0x100]            raw host bytes
    python scripts/host_peek.py --ls <ctx> <lsa> [<len>=0x100] ...   SPU local store of a context

<ctx> is a spu_context* as printed by the runtime ([pm-end] ... ctx=000001D3...). Its local
store pointer is read at ctx + LS_PTR_OFF (0x40800 in the current build: the offset the lifted
code uses, `mov rax, [rcx + 264192]`; check the assembly again if spu_context changes).
--regs <ctx>: pc and the 128 registers' preferred words (gpr[] is at the start of the context).
Prints big-endian 32-bit words for LS (SPU order), little-endian for raw host memory.
"""
import ctypes, struct, sys

sys.path.insert(0, __import__('os').path.dirname(__file__))
from guest_peek import find_pid, PROCESS_VM_READ, PROCESS_QUERY_INFORMATION  # noqa: E402

LS_PTR_OFF = 0x40800
PC_OFF = 0x40808        # ctx->pc (`mov dword ptr [rcx + 264200], imm` in lifted code)


def reader():
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, find_pid())
    if not h:
        sys.exit("OpenProcess failed")

    def rd(addr, n):
        buf = (ctypes.c_ubyte * n)()
        got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)):
            return None
        return bytes(buf[:got.value])
    return rd


def dump(label, base, b, be=True):
    for o in range(0, len(b), 16):
        ws = []
        for i in range(0, min(16, len(b) - o), 4):
            w = b[o + i:o + i + 4]
            ws.append(w.hex().upper() if be else "%08X" % struct.unpack("<I", w)[0])
        print("%s0x%05X: %s" % (label, base + o, " ".join(ws)))


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    rd = reader()
    if a[0] == "--regs":
        ctx = int(a[1], 16)
        g = rd(ctx, 128 * 16)
        pc = rd(ctx + PC_OFF, 4)
        print("pc = 0x%05X" % (struct.unpack("<I", pc)[0] & 0x3FFFF))
        for r in range(128):
            w = struct.unpack("<4I", g[r * 16:r * 16 + 16])
            print("r%-3d %08X %08X %08X %08X" % ((r,) + w))
        return
    if a[0] == "--ls":
        ctx = int(a[1], 16)
        p = rd(ctx + LS_PTR_OFF, 8)
        if not p:
            sys.exit("context unreadable")
        ls = struct.unpack("<Q", p)[0]
        print("ctx %X: ls at host %X" % (ctx, ls))
        rest = [int(x, 0) for x in a[2:]]
        if len(rest) % 2:
            rest.append(0x100)
        for lsa, n in zip(rest[::2], rest[1::2]):
            b = rd(ls + lsa, n)
            if b is None:
                print("LS 0x%05X: unreadable" % lsa)
            else:
                dump("LS ", lsa, b)
        return
    addr = int(a[0], 16)
    n = int(a[1], 0) if len(a) > 1 else 0x100
    b = rd(addr, n)
    if b is None:
        sys.exit("unreadable")
    dump("", 0, b, be=False)


if __name__ == "__main__":
    main()
