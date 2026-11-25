"""Where is every thread of the running MotorStormApocalypse.exe? (external, no debugger)

    python scripts/host_stacks.py [--name <substr>] [--samples 20] [--depth 10] [--map <map>]

For each thread (named by SetThreadDescription: "ppu main", "spurs pm", "spu job"...), suspends
it briefly --samples times, reads RIP and scans its stack for return addresses into the
executable's code, and resolves them with the linker map (port/build/MotorStormApocalypse.map).
Prints, per thread, the distinct call chains seen (innermost first) with their sample counts:
for a frozen game this names the lifted guest function each PPU thread loops or waits in
(func_XXXXXXXX = guest address) and the runtime call it sits under.
The stack scan is heuristic (any stack word that points into code counts), so a chain can hold
stale entries; the first ones are the reliable ones.
"""
import argparse, bisect, collections, ctypes, ctypes.wintypes as wt, os, struct, sys, time

sys.path.insert(0, os.path.dirname(__file__))
from guest_peek import find_pid  # noqa: E402
from samp_resolve import load_map  # noqa: E402

k32 = ctypes.windll.kernel32
TH32CS_SNAPTHREAD = 4
THREAD_ACCESS = 0x0002 | 0x0008 | 0x0040 | 0x0800   # SUSPEND_RESUME | GET_CONTEXT | QUERY_INFO | QUERY_LIMITED
CONTEXT_CONTROL = 0x100001
CONTEXT_INTEGER = 0x100002


class THREADENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ThreadID", wt.DWORD),
                ("th32OwnerProcessID", wt.DWORD), ("tpBasePri", wt.LONG), ("tpDeltaPri", wt.LONG),
                ("dwFlags", wt.DWORD)]


def threads_of(pid):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    te = THREADENTRY32(); te.dwSize = ctypes.sizeof(te)
    out = []
    ok = k32.Thread32First(snap, ctypes.byref(te))
    while ok:
        if te.th32OwnerProcessID == pid:
            out.append(te.th32ThreadID)
        ok = k32.Thread32Next(snap, ctypes.byref(te))
    k32.CloseHandle(snap)
    return out


def thread_name(h):
    p = ctypes.c_wchar_p()
    try:
        if ctypes.windll.kernelbase.GetThreadDescription(h, ctypes.byref(p)) >= 0 and p.value is not None:
            s = p.value
            k32.LocalFree(p)
            return s
    except Exception:
        pass
    return ""


def exe_image(hproc, pid):
    """(base, code_lo, code_hi) of the main module, read from its PE headers."""
    psapi = ctypes.windll.psapi
    mods = (ctypes.c_void_p * 1)()
    need = wt.DWORD()
    psapi.EnumProcessModules(hproc, mods, ctypes.sizeof(mods), ctypes.byref(need))
    base = mods[0]

    def rd(a, n):
        b = (ctypes.c_ubyte * n)(); got = ctypes.c_size_t()
        k32.ReadProcessMemory(hproc, ctypes.c_void_p(a), b, n, ctypes.byref(got))
        return bytes(b)
    lfanew = struct.unpack("<I", rd(base + 0x3C, 4))[0]
    nsec = struct.unpack("<H", rd(base + lfanew + 6, 2))[0]
    optsz = struct.unpack("<H", rd(base + lfanew + 20, 2))[0]
    sec = base + lfanew + 24 + optsz
    lo, hi = None, 0
    for i in range(nsec):
        s = rd(sec + 40 * i, 40)
        vsize, va = struct.unpack("<II", s[8:16])
        chars = struct.unpack("<I", s[36:40])[0]
        if chars & 0x20000000:      # IMAGE_SCN_MEM_EXECUTE
            lo = va if lo is None else min(lo, va)
            hi = max(hi, va + vsize)
    return base, base + lo, base + hi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="")
    ap.add_argument("--samples", type=int, default=20)
    ap.add_argument("--depth", type=int, default=10)
    ap.add_argument("--map", default=os.path.join(os.path.dirname(__file__), "..", "port", "build",
                                                  "MotorStormApocalypse.map"))
    a = ap.parse_args()
    rvas, names = load_map(a.map)

    def sym(addr, base):
        i = bisect.bisect_right(rvas, addr - base) - 1
        return names[i] if i >= 0 else "?"

    pid = find_pid()
    k32.OpenProcess.restype = wt.HANDLE
    k32.OpenThread.restype = wt.HANDLE
    hproc = k32.OpenProcess(0x0410, False, pid)
    base, clo, chi = exe_image(hproc, pid)
    ctx = (ctypes.c_ubyte * 1232)()            # x64 CONTEXT, 16-byte aligned below
    buf_t = ctypes.c_ubyte * 1248
    raw = buf_t()
    off = (-ctypes.addressof(raw)) % 16
    ctxp = ctypes.addressof(raw) + off
    res = {}
    for tid in threads_of(pid):
        h = k32.OpenThread(THREAD_ACCESS, False, tid)
        if not h:
            continue
        nm = thread_name(h)
        if a.name and a.name not in nm:
            k32.CloseHandle(h); continue
        chains = collections.Counter()
        for _ in range(a.samples):
            if k32.SuspendThread(h) == 0xFFFFFFFF:
                break
            ctypes.memset(ctxp, 0, 1232)
            struct.pack_into("<I", raw, off + 0x30, CONTEXT_CONTROL | CONTEXT_INTEGER)
            chain = []
            if k32.GetThreadContext(h, ctypes.c_void_p(ctxp)):
                rsp = struct.unpack_from("<Q", raw, off + 0x98)[0]
                rip = struct.unpack_from("<Q", raw, off + 0xF8)[0]
                chain.append(sym(rip, base) if clo <= rip < chi else "<outside exe>")
                stack = (ctypes.c_ubyte * 65536)(); got = ctypes.c_size_t()
                for want in (65536, 16384, 4096, 1024):     # the read fails whole past the stack top
                    if k32.ReadProcessMemory(hproc, ctypes.c_void_p(rsp), stack, want, ctypes.byref(got)):
                        break
                    got.value = 0
                last = None
                for (v,) in struct.iter_unpack("<Q", bytes(stack[:got.value & ~7])):
                    if clo <= v < chi:
                        s = sym(v, base)
                        if s != last:
                            chain.append(s); last = s
                        if len(chain) > a.depth:
                            break
            k32.ResumeThread(h)
            chains[tuple(chain)] += 1
            time.sleep(0.01)
        k32.CloseHandle(h)
        res[tid] = (nm, chains)
    for tid, (nm, chains) in sorted(res.items(), key=lambda x: x[1][0]):
        print("=== thread %d [%s]" % (tid, nm))
        for chain, n in chains.most_common(4):
            print("  %3d x  %s" % (n, " <- ".join(chain)))


if __name__ == "__main__":
    main()
