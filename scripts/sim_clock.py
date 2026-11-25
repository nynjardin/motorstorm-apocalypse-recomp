"""The title's simulation clock in a running MotorStormApocalypse.exe: show it, switch it, time it.

    python scripts/sim_clock.py                      # find the clock source, print its fields
    python scripts/sim_clock.py --watch 10           # race clock seconds per wall second, 10 s
    python scripts/sim_clock.py --realtime 1 --interval 1 [--watch 10]   # poke, then watch
    python scripts/sim_clock.py --realtime 0 --interval 2                # back to the title's setup

The clock source (constructed by func_005EE2A4 at +0x40 of the object whose vtable is
0x01188348, func_002D6C90): +0x00 int64 step in us, +0x10 refresh Hz, +0x14 float scale (slow
motion), +0x18 flip interval in vblanks, +0x1C real-time flag (0 = every frame adds the fixed
step, 1 = adds the wall time since the last frame * scale). The title's setup (func_002D6F30)
writes Hz 60, flag 0, interval 2: a fixed 1/30 s step per frame, whatever the frame takes.
The present copies +0x18 into the display object's flip interval every frame.
Race clock: float seconds at 0x014FC348. Addresses and layout from the notes of
millennium-h4x0r's port (docs/PROGRESS.md lead L); they are the same in our EBOOT.
--realtime / --interval WRITE GUEST STATE (an experiment, see docs/hle.md "Frame pacing"): the
title rewrites both whenever it reconfigures the clock (race load, some menus).
"""
import ctypes, os, struct, sys, time

sys.path.insert(0, os.path.dirname(__file__))
import guest_peek as gp

VTABLE = 0x01188348
RACE_CLOCK = 0x014FC348
DISPLAY_PTR = 0x0144F150
k32 = ctypes.windll.kernel32


def rd(h, base, ea, n):
    buf = (ctypes.c_ubyte * n)()
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(base + ea), buf, n, ctypes.byref(got)):
        return None
    return bytes(buf[:got.value])


def wr32(h, base, ea, v):
    n = ctypes.c_size_t()
    return k32.WriteProcessMemory(h, ctypes.c_void_p(base + ea), struct.pack(">I", v), 4, ctypes.byref(n))


def find_clock(h, base):
    pat = struct.pack(">I", VTABLE)
    mbi = gp.MBI()
    k32.VirtualQueryEx.restype = ctypes.c_size_t
    ea, out = 0x10000, []
    while ea < 0xE0000000:
        if not k32.VirtualQueryEx(h, ctypes.c_void_p(base + ea), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        end = (mbi.BaseAddress or 0) + mbi.RegionSize - base
        if mbi.State == 0x1000 and not (mbi.Protect & 0x101):
            pos = ea
            while pos < min(end, 0xE0000000):
                n = min(8 << 20, min(end, 0xE0000000) - pos)
                data = rd(h, base, pos, n) or b""
                at = data.find(pat)
                while at >= 0:
                    if at % 4 == 0:
                        c = rd(h, base, pos + at + 0x40, 0x24)
                        if c and len(c) == 0x24:
                            hz, scale, iv, flag = struct.unpack(">IfII", c[0x10:0x20])
                            if hz in (30, 50, 60) and 0 < iv <= 4 and flag <= 1 and 0.0 < scale <= 4.0:
                                out.append(pos + at + 0x40)
                    at = data.find(pat, at + 1)
                pos += n
        ea = max(end, ea + 0x1000)
    return out


def show(h, base, clk):
    c = rd(h, base, clk, 0x24)
    step, slack = struct.unpack(">qq", c[:16])
    hz, scale, iv, flag = struct.unpack(">IfII", c[0x10:0x20])
    d = struct.unpack(">I", rd(h, base, DISPLAY_PTR, 4))[0]
    div = struct.unpack(">I", rd(h, base, d + 0x74, 4))[0] if d else -1
    print(f"clock 0x{clk:08X}: step {step} us, {hz} Hz, scale {scale:g}, interval {iv}, real-time {flag}; "
          f"display interval {div}")


def main():
    a = sys.argv[1:]
    opt = {}
    i = 0
    while i < len(a):
        opt[a[i]] = a[i + 1]; i += 2
    h = k32.OpenProcess(0x10 | 0x20 | 0x08 | 0x400, False, gp.find_pid())
    if not h:
        sys.exit("OpenProcess failed")
    base = gp.find_vm_base(h)
    clocks = find_clock(h, base)
    if not clocks:
        sys.exit("clock source not found")
    for c in clocks:
        show(h, base, c)
    clk = clocks[0]
    if "--realtime" in opt or "--interval" in opt:
        if "--interval" in opt:
            wr32(h, base, clk + 0x18, int(opt["--interval"]))
        if "--realtime" in opt:
            wr32(h, base, clk + 0x1C, int(opt["--realtime"]))
        time.sleep(0.3)
        show(h, base, clk)
    if "--watch" in opt:
        secs = float(opt["--watch"])
        d = struct.unpack(">I", rd(h, base, DISPLAY_PTR, 4))[0]

        def sample():
            rc = struct.unpack(">f", rd(h, base, RACE_CLOCK, 4))[0]
            flips = struct.unpack(">I", rd(h, base, d + 0x70, 4))[0]
            vb = struct.unpack(">I", rd(h, base, d + 0x6C, 4))[0]
            return time.perf_counter(), rc, flips, vb
        t0, r0, f0, v0 = sample()
        pt, pr = t0, r0
        while time.perf_counter() - t0 < secs:
            time.sleep(2.0)
            t, r, f, v = sample()
            print(f"  +{t - t0:5.1f} s  race clock {r:9.3f}  ({(r - pr) / (t - pt):.3f} s/s)")
            pt, pr = t, r
        t, r, f, v = sample()
        print(f"race clock {r - r0:.3f} s in {t - t0:.3f} s of wall time: x{(r - r0) / (t - t0):.3f}; "
              f"vblanks {(v - v0) / (t - t0):.1f}/s; last-flip vblank count advanced {(f - f0) / (t - t0):.1f}/s")


if __name__ == "__main__":
    main()
