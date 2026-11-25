"""Search the guest memory of a running MotorStormApocalypse.exe for a byte pattern.

    python scripts/guest_find.py <hex bytes> [--lo <ea>] [--hi <ea>] [--max 40] [--ctx 0]
    python scripts/guest_find.py "433EF8D4 407471B4 3FF471B4"          # a float triple, big-endian
    python scripts/guest_find.py 3F800000000000003F80000000000000 --lo 0x10000000 --hi 0x20000000 --ctx 32

Only committed pages of the guest reservation are read (scripts/guest_peek.py finds it). Prints the
guest address of each match (first --max) and, with --ctx <n>, the n bytes before and after it as
big-endian words. To find where a value seen in a vertex stream or a texture also lives (the
structure it was copied from), and to watch a table over time (run it again).
"""
import ctypes, os, sys

sys.path.insert(0, os.path.dirname(__file__))
import guest_peek as gp


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    opt = {"--lo": 0x10000, "--hi": 0xE0000000, "--max": 40, "--ctx": 0}
    pat = None
    i = 0
    while i < len(a):
        if a[i] in opt:
            opt[a[i]] = int(a[i + 1], 0); i += 2
        else:
            pat = bytes.fromhex(a[i].replace(" ", "")); i += 1
    lo, hi, mx, ctx = opt["--lo"], opt["--hi"], opt["--max"], opt["--ctx"]
    k32 = ctypes.windll.kernel32
    k32.VirtualQueryEx.restype = ctypes.c_size_t
    h = k32.OpenProcess(gp.PROCESS_VM_READ | gp.PROCESS_QUERY_INFORMATION, False, gp.find_pid())
    if not h:
        sys.exit("OpenProcess failed")
    base = gp.find_vm_base(h)
    mbi = gp.MBI()
    ea = lo
    found = 0
    got = ctypes.c_size_t()
    while ea < hi and found < mx:
        if not k32.VirtualQueryEx(h, ctypes.c_void_p(base + ea), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        end = (mbi.BaseAddress or 0) + mbi.RegionSize - base
        if mbi.State == 0x1000 and not (mbi.Protect & 0x101):      # MEM_COMMIT, not NOACCESS / GUARD
            pos = ea
            while pos < min(end, hi) and found < mx:
                n = min(8 << 20, min(end, hi) - pos)
                buf = (ctypes.c_ubyte * (n + len(pat)))()
                if not k32.ReadProcessMemory(h, ctypes.c_void_p(base + pos), buf, n + len(pat), ctypes.byref(got)):
                    k32.ReadProcessMemory(h, ctypes.c_void_p(base + pos), buf, n, ctypes.byref(got))
                data = bytes(buf[:got.value])
                at = data.find(pat)
                while at >= 0 and at < n and found < mx:
                    found += 1
                    line = "0x%08X" % (pos + at)
                    if ctx:
                        s = max(0, (at - ctx) & ~3)
                        seg = data[s:at + len(pat) + ctx]
                        line += "  [0x%08X] " % (pos + s) + " ".join(seg[j:j + 4].hex().upper() for j in range(0, len(seg), 4))
                    print(line)
                    at = data.find(pat, at + 1)
                pos += n
        ea = max(end, ea + 0x1000)
    print("%d match(es)%s" % (found, " (stopped at --max)" if found >= mx else ""))


if __name__ == "__main__":
    main()
