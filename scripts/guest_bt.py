"""Guest call chain of a thread from its guest stack pointer (frame walk, game left running).

    python scripts/guest_bt.py <sp hex> [depth=40]
    python scripts/guest_bt.py --name "ppu main" [depth]     (sp taken from host_ppuctx.py)

PPC64 ABI as the lifted code uses it: [sp] = back chain (64 bit), the caller's LR saved at
back_chain + 0x10. Prints the return addresses (guest code), innermost first; the function that
contains each is the one at or just below that address in the lifted tree (grep "^void func_").
sp of a thread: scripts/host_ppuctx.py prints r1 of the candidate contexts.
"""
import ctypes, os, re, struct, subprocess, sys

sys.path.insert(0, os.path.dirname(__file__))
from guest_peek import find_pid, find_vm_base  # noqa: E402

k32 = ctypes.windll.kernel32
h = k32.OpenProcess(0x10 | 0x400, False, find_pid())
base = find_vm_base(h)


def rd(ea, n):
    buf = (ctypes.c_ubyte * n)()
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(base + ea), buf, n, ctypes.byref(got)) or got.value != n:
        return None
    return bytes(buf)


args = sys.argv[1:]
if not args:
    sys.exit(__doc__)
if args[0] == "--name":
    cmd = [sys.executable, os.path.join(os.path.dirname(__file__), "host_ppuctx.py"), "--name", args[1]]
    if "main" not in args[1]:   # worker threads have their stacks at 0xD0xxxxxx
        cmd += ["--sp-lo", "0xD0000000", "--sp-hi", "0xD2000000"]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    m = re.search(r"r1\s+([0-9A-F]{16})", out)
    if not m:
        sys.exit("no sp found:\n" + out)
    sp = int(m.group(1), 16)
    depth = int(args[2]) if len(args) > 2 else 40
else:
    sp = int(args[0], 16)
    depth = int(args[1]) if len(args) > 1 else 40
print("sp 0x%08X" % sp)
for i in range(depth):
    b = rd(sp, 8)
    if not b:
        break
    bc = struct.unpack(">Q", b)[0] & 0xFFFFFFFF
    if bc <= sp or bc == 0:
        break
    l = rd(bc + 0x10, 8)
    if not l:
        break
    lr = struct.unpack(">Q", l)[0] & 0xFFFFFFFF
    print("  frame %2d sp=0x%08X -> lr=0x%08X" % (i, bc, lr))
    sp = bc
