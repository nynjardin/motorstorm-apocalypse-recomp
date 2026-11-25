"""Write a big-endian 32-bit word into the guest memory of the running game.

    python scripts/guest_poke.py <ea> <value>

DIAGNOSTIC THAT FABRICATES GUEST STATE: use it only to test a hypothesis on a frozen game
(e.g. set the completion flag a thread polls, to see whether everything else was done).
"""
import ctypes, struct, sys
sys.path.insert(0, __import__('os').path.dirname(__file__))
from guest_peek import find_pid, find_vm_base

ea, val = int(sys.argv[1], 0), int(sys.argv[2], 0)
k32 = ctypes.windll.kernel32
h = k32.OpenProcess(0x10 | 0x20 | 0x08 | 0x400, False, find_pid())   # VM_READ | VM_WRITE | VM_OPERATION | QUERY
if not h:
    sys.exit("OpenProcess failed")
base = find_vm_base(h)
b = struct.pack(">I", val)
n = ctypes.c_size_t()
ok = k32.WriteProcessMemory(h, ctypes.c_void_p(base + ea), b, 4, ctypes.byref(n))
print("0x%08X <- 0x%08X: %s" % (ea, val, "ok" if ok else "FAILED"))
