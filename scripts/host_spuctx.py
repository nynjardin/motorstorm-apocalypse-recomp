"""SPU registers of the SPU host threads of the running game, found from outside.

    python scripts/host_spuctx.py [--name "spu job"] [--ls <lsa> <len>]

Like host_ppuctx.py: suspends each matching thread, takes every pointer found in its host
registers / on its host stack as a candidate spu_context*, and accepts it when the fields the
lifted code uses look right: ctx + 0x40800 = local-store pointer (readable, 256 KB),
ctx + 0x40808 = pc < 0x40000, gpr[1] (stack) word 0 < 0x40000. Prints pc, r0 (link), r1, r2,
r3..r6 preferred words, and optionally a local-store range. For a task parked in WAIT_SIGNAL,
r0 is the return address of the syscall = where in the task's code it waits.
"""
import argparse, ctypes, ctypes.wintypes as wt, os, struct, sys

sys.path.insert(0, os.path.dirname(__file__))
from guest_peek import find_pid  # noqa: E402
from host_stacks import threads_of, thread_name, THREAD_ACCESS  # noqa: E402

k32 = ctypes.windll.kernel32
LS_OFF, PC_OFF = 0x40800, 0x40808


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="spu job")
    ap.add_argument("--ls", nargs=2, default=None)
    a = ap.parse_args()
    pid = find_pid()
    k32.OpenProcess.restype = wt.HANDLE
    k32.OpenThread.restype = wt.HANDLE
    hp = k32.OpenProcess(0x0410, False, pid)

    def rd(addr, n):
        b = (ctypes.c_ubyte * n)(); got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(hp, ctypes.c_void_p(addr), b, n, ctypes.byref(got)):
            return None
        return bytes(b[:got.value])

    raw = (ctypes.c_ubyte * 1248)()
    off = (-ctypes.addressof(raw)) % 16
    ctxp = ctypes.addressof(raw) + off
    for tid in threads_of(pid):
        h = k32.OpenThread(THREAD_ACCESS, False, tid)
        if not h:
            continue
        nm = thread_name(h)
        if a.name not in nm:
            k32.CloseHandle(h); continue
        k32.SuspendThread(h)
        struct.pack_into("<I", raw, off + 0x30, 0x100003)
        cands = []
        if k32.GetThreadContext(h, ctypes.c_void_p(ctxp)):
            regs = struct.unpack_from("<16Q", raw, off + 0x78)
            cands += list(regs)
            for want in (65536, 16384, 4096):
                st = rd(regs[4], want)
                if st:
                    cands += [v for (v,) in struct.iter_unpack("<Q", st[:len(st) & ~7])]
                    break
        seen = set()
        for p in cands:
            if p in seen or p < 0x10000 or p >= 1 << 47 or p & 15:
                continue
            seen.add(p)
            t = rd(p + LS_OFF, 16)
            if not t or len(t) < 16:
                continue
            ls, pc = struct.unpack("<QI", t[:12])
            if not (0x10000 <= ls < 1 << 47) or pc >= 0x40000 or pc & 3:
                continue
            g = rd(p, 8 * 16)
            if not g:
                continue
            r = [struct.unpack_from("<I", g, i * 16)[0] for i in range(8)]
            if r[1] >= 0x40000 or rd(ls + 0x3FFF0, 16) is None:
                continue
            print("thread %d [%s] ctx=%X pc=0x%05X r0(lr)=0x%05X r1=0x%05X r2=0x%X r3=0x%X r4=0x%X r5=0x%X r6=0x%X" % (
                tid, nm, p, pc, r[0] & 0x3FFFF, r[1], r[2], r[3], r[4], r[5], r[6]))
            if a.ls:
                lsa, n = int(a.ls[0], 0), int(a.ls[1], 0)
                b = rd(ls + lsa, n) or b""
                for o in range(0, len(b), 16):
                    print("   LS 0x%05X: %s" % (lsa + o, " ".join(b[o + i:o + i + 4].hex().upper() for i in range(0, 16, 4))))
            break
        k32.ResumeThread(h)
        k32.CloseHandle(h)


if __name__ == "__main__":
    main()
