"""Dump a range of guest memory of the running game to a file.   guest_dump.py <ea> <len> <out file>"""
import ctypes, os, sys

sys.path.insert(0, os.path.dirname(__file__))
from guest_peek import find_pid, find_vm_base  # noqa: E402

ea, n, out = int(sys.argv[1], 0), int(sys.argv[2], 0), sys.argv[3]
k32 = ctypes.windll.kernel32
h = k32.OpenProcess(0x10 | 0x400, False, find_pid())
base = find_vm_base(h)
buf = (ctypes.c_ubyte * n)()
got = ctypes.c_size_t()
if not k32.ReadProcessMemory(h, ctypes.c_void_p(base + ea), buf, n, ctypes.byref(got)):
    sys.exit("unreadable")
open(out, "wb").write(bytes(buf[:got.value]))
print("wrote", got.value, "bytes to", out, "nonzero", sum(1 for b in bytes(buf[:got.value]) if b))
