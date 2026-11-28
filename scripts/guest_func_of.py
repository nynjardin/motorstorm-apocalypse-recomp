"""Which lifted function contains a guest address?   guest_func_of.py <title dir> <addr hex> [...]

    python scripts/guest_func_of.py work/BCES00484_106/recomp 0x63A020 0x4C7EAC

Reads the "void func_XXXXXXXX(" definitions of the lifted tree (cached in the temp dir) and prints
the function at or just below each address (a return address is inside its caller).
"""
import bisect, glob, os, re, sys, tempfile

d = sys.argv[1]
cache = os.path.join(tempfile.gettempdir(), "funcs_" + re.sub(r"\W", "_", os.path.abspath(d)) + ".txt")
if os.path.exists(cache) and os.path.getmtime(cache) > max(os.path.getmtime(f) for f in glob.glob(os.path.join(d, "ppu_recomp_*.cpp"))):
    addrs = [int(x) for x in open(cache).read().split()]
else:
    addrs = []
    for f in glob.glob(os.path.join(d, "ppu_recomp_*.cpp")):
        txt = open(f, encoding="latin-1").read()
        addrs += [int(m, 16) for m in re.findall(r"(?m)^void func_([0-9A-F]{8})\(ppu_context", txt)]
    addrs = sorted(set(addrs))
    open(cache, "w").write(" ".join(map(str, addrs)))
for a in sys.argv[2:]:
    v = int(a, 0)
    i = bisect.bisect_right(addrs, v) - 1
    print("0x%08X in func_%08X (+0x%X)" % (v, addrs[i], v - addrs[i]) if i >= 0 else "0x%08X ?" % v)
