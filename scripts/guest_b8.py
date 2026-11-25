"""guest_b8.py <ea hex>:<w>:<h> [...]
A B8 texture (one byte per texel, RSX format 0x81) read from the memory of the running game,
printed as a grid of hex bytes twice: as stored (swizzled, the "(SZ)" of a capture manifest)
and de-swizzled (Morton order: x and y bits interleaved, x first). The ea of a local-memory
texture is its "off=" in a capture manifest (0xC... = local memory).
For the vehicles' contact-shadow textures of the cube fp=0x301 (16x16, dark squares,
2026-11-25). System python.
"""
import sys, ctypes
sys.path.insert(0, 'I:/Projets/Recomp/MotorStorm/scripts')
import guest_peek as gp

k32 = ctypes.windll.kernel32
h = k32.OpenProcess(gp.PROCESS_VM_READ | gp.PROCESS_QUERY_INFORMATION, False, gp.find_pid())
base = gp.find_vm_base(h)


def morton(x, y, w, hh):
    """Index of texel (x, y) in a swizzled square power-of-two texture: bit i of x goes to
    bit 2i, bit i of y to bit 2i + 1."""
    r = 0
    for i in range(max(w, hh).bit_length()):
        r |= ((x >> i) & 1) << (2 * i) | ((y >> i) & 1) << (2 * i + 1)
    return r


for a in sys.argv[1:]:
    ea, w, hh = a.split(':'); ea = int(ea, 16); w = int(w); hh = int(hh)
    n = w * hh
    buf = (ctypes.c_ubyte * n)(); got = ctypes.c_size_t()
    k32.ReadProcessMemory(h, ctypes.c_void_p(base + ea), buf, n, ctypes.byref(got))
    b = bytes(buf[:got.value])
    print('%08X %dx%d read=%d' % (ea, w, hh, len(b)))
    print(' as stored:')
    for y in range(hh):
        print('  ' + ' '.join('%02X' % b[y * w + x] for x in range(w)))
    print(' de-swizzled:')
    for y in range(hh):
        print('  ' + ' '.join('%02X' % b[morton(x, y, w, hh)] for x in range(w)))
