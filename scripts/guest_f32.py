"""guest_f32.py <ea hex> <count> [--le]
Big-endian float32 values (four per texel of a W32_Z32_Y32_X32 surface) read from the memory of
the running game, one texel (x, y, z, w) per line; non-zero texels only. --le reads them as
little-endian too (a write-back that forgot the byte swap shows sane values only that way).
For the lamp-visibility strips (128x1, RT_WB, lens flares, 2026-11-25). System python.
"""
import sys, ctypes, struct
sys.path.insert(0, 'I:/Projets/Recomp/MotorStorm/scripts')
import guest_peek as gp

k32 = ctypes.windll.kernel32
h = k32.OpenProcess(gp.PROCESS_VM_READ | gp.PROCESS_QUERY_INFORMATION, False, gp.find_pid())
base = gp.find_vm_base(h)
ea, count = int(sys.argv[1], 16), int(sys.argv[2])
n = count * 16
buf = (ctypes.c_ubyte * n)(); got = ctypes.c_size_t()
k32.ReadProcessMemory(h, ctypes.c_void_p(base + ea), buf, n, ctypes.byref(got))
b = bytes(buf[:got.value])
le = '--le' in sys.argv
for i in range(len(b) // 16):
    t = b[i * 16:(i + 1) * 16]
    if not any(t):
        continue
    be = struct.unpack('>4f', t)
    line = '%3d  BE %s' % (i, ' '.join('%10.4g' % v for v in be))
    if le:
        line += '   LE %s' % ' '.join('%10.4g' % v for v in struct.unpack('<4f', t))
    print(line)
