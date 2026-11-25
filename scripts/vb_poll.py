"""Poll the title's frame pacing state in a running MotorStormApocalypse.exe.

    python scripts/vb_poll.py [seconds=3] [period_ms=2] [--quiet]

Reads the display object ([0x0144F150]) and RSX labels 72..76 every period and prints one line
per change: time (ms), mode (+0x64), next mode (+0x68), vblank counter (+0x6C), counter at the
last flip (+0x70), flip interval in vblanks (+0x74), labels 72 / 73 / 75 / 76.
Ends with rates: vblanks per second (handler calls), flips per second (changes of +0x70), and
the histogram of vblanks per flip. --quiet prints the summary only.
Expected with the title's limiter working: 59.94 vblanks/s, flips 2 vblanks apart or more.
See docs/hle.md ("Frame pacing").
"""
import ctypes, struct, sys, time
import guest_peek as gp

args = [a for a in sys.argv[1:] if not a.startswith('-')]
quiet = '--quiet' in sys.argv
secs = float(args[0]) if args else 3.0
per = (float(args[1]) if len(args) > 1 else 2.0) / 1000.0

k32 = ctypes.windll.kernel32
h = k32.OpenProcess(gp.PROCESS_VM_READ | gp.PROCESS_QUERY_INFORMATION, False, gp.find_pid())
if not h:
    sys.exit("OpenProcess failed")
base = gp.find_vm_base(h)


def rd(ea, n):
    buf = (ctypes.c_ubyte * n)()
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(base + ea), buf, n, ctypes.byref(got)):
        return None
    return bytes(buf[:got.value])


obj = struct.unpack(">I", rd(0x0144F150, 4))[0]
print(f"display object 0x{obj:08X}")
t0 = time.perf_counter()
last = None
first = None
flips = 0
hist = {}
prev_flip_ctr = None
while True:
    t = time.perf_counter() - t0
    if t > secs:
        break
    o = rd(obj + 0x64, 0x14)
    lab = rd(0x20000480, 0x50)
    if not o or not lab:
        time.sleep(per)
        continue
    mode, nxt, ctr, lastf, itv = struct.unpack(">5I", o)
    l72, l73, l75, l76 = (struct.unpack(">I", lab[i:i + 4])[0] for i in (0, 0x10, 0x30, 0x40))
    cur = (mode, nxt, ctr, lastf, itv, l72, l73, l75, l76)
    if first is None:
        first = (t, ctr)
        prev_flip_ctr = lastf
    if lastf != prev_flip_ctr:
        flips += 1
        d = (lastf - prev_flip_ctr) & 0xFFFFFFFF
        hist[d] = hist.get(d, 0) + 1
        prev_flip_ctr = lastf
    if cur != last:
        if not quiet:
            print(f"{t * 1000:8.1f} mode={mode} next={nxt} ctr={ctr} last={lastf} itv={itv} | "
                  f"L72={l72} L73={l73} L75={l75} L76={l76}")
        last = cur
    time.sleep(per)
dt = t - first[0]
print(f"{dt:.2f} s: {(last[2] - first[1]) / dt:.2f} vblanks/s, {flips / dt:.2f} flips/s, "
      f"vblanks per flip: {dict(sorted(hist.items()))}")
