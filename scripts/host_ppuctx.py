"""Guest registers of a PPU thread of the running game, found from outside.

    python scripts/host_ppuctx.py [--name "ppu main"] [--sp-lo 0x0FE00000 --sp-hi 0x0FF00000]

A lifted function receives its ppu_context* in rcx and keeps it in host registers / spills
it on the host stack. This suspends the named thread, reads its integer registers and the
top of its host stack, and treats every pointer P found there as a candidate context: P is
accepted when gpr[1] (the u64 at P + 8) is a plausible guest stack pointer
(--sp-lo..--sp-hi; the main thread's stack is at 0x0FExxxxx, the others' at 0xD0xxxxxx).
Prints gpr[0..31] of each distinct candidate (ppu_context starts with gpr[32], u64 each).
"""
import argparse, ctypes, ctypes.wintypes as wt, os, struct, sys

sys.path.insert(0, os.path.dirname(__file__))
from guest_peek import find_pid  # noqa: E402
from host_stacks import threads_of, thread_name, THREAD_ACCESS  # noqa: E402

k32 = ctypes.windll.kernel32


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="ppu main")
    ap.add_argument("--sp-lo", type=lambda x: int(x, 0), default=0x0FE00000)
    ap.add_argument("--sp-hi", type=lambda x: int(x, 0), default=0x0FF00000)
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
        if nm != a.name and a.name not in nm:
            k32.CloseHandle(h); continue
        k32.SuspendThread(h)
        struct.pack_into("<I", raw, off + 0x30, 0x100003)        # CONTROL | INTEGER
        cands = []
        if k32.GetThreadContext(h, ctypes.c_void_p(ctxp)):
            regs = struct.unpack_from("<16Q", raw, off + 0x78)   # rax..r15
            rsp = regs[4]
            cands += list(regs)
            for want in (65536, 16384, 4096):
                st = rd(rsp, want)
                if st:
                    cands += [v for (v,) in struct.iter_unpack("<Q", st[:len(st) & ~7])]
                    break
        seen = set()
        print("=== thread %d [%s]" % (tid, nm))
        for p in cands:
            if p in seen or p < 0x10000 or p >= 1 << 47 or p & 7:
                continue
            seen.add(p)
            b = rd(p, 32 * 8)
            if not b or len(b) < 256:
                continue
            g = struct.unpack("<32Q", b)
            if a.sp_lo <= g[1] < a.sp_hi and g[2] < 1 << 32 and g[13] < 1 << 32:
                print("ctx at host %X" % p)
                for i in range(0, 32, 4):
                    print("  r%-2d %016X  r%-2d %016X  r%-2d %016X  r%-2d %016X" % (
                        i, g[i], i + 1, g[i + 1], i + 2, g[i + 2], i + 3, g[i + 3]))
        k32.ResumeThread(h)
        k32.CloseHandle(h)


if __name__ == "__main__":
    main()
