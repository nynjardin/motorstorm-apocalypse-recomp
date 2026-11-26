"""guest_tex_png.py <ea hex> <w> <h> <out prefix> [--bpp 1|4]
A texture read from the memory of the running game, written as two PNGs: <prefix>_raw.png (bytes
as stored, rows of w texels) and <prefix>_swz.png (de-swizzled, Morton order: bit i of x to bit
2i, bit i of y to bit 2i + 1, for square or rectangular power-of-two sizes). --bpp 1 (default) =
B8 (RSX format 0x81), grey; --bpp 4 = A8R8G8B8, written as RGB. Local-memory textures: ea =
0xC0000000 + offset. For the lens-flare atlas (fp 0x20EBC1, tex0 0x0020EC80 B8 512x512,
2026-11-26). System python (PIL).
"""
import sys, ctypes
sys.path.insert(0, 'I:/Projets/Recomp/MotorStorm/scripts')
import guest_peek as gp
from PIL import Image

ea, w, h, prefix = int(sys.argv[1], 16), int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
bpp = int(sys.argv[sys.argv.index('--bpp') + 1]) if '--bpp' in sys.argv else 1
k32 = ctypes.windll.kernel32
hp = k32.OpenProcess(gp.PROCESS_VM_READ | gp.PROCESS_QUERY_INFORMATION, False, gp.find_pid())
base = gp.find_vm_base(hp)
n = w * h * bpp
buf = (ctypes.c_ubyte * n)(); got = ctypes.c_size_t()
k32.ReadProcessMemory(hp, ctypes.c_void_p(base + ea), buf, n, ctypes.byref(got))
b = bytes(buf[:got.value])
if len(b) < n:
    sys.exit('read %d of %d bytes' % (len(b), n))


def morton(x, y):
    """Swizzled index of (x, y): interleave the low bits while both sizes have them."""
    i, bit, sx, sy = 0, 0, 1, 1
    while sx < w or sy < h:
        if sx < w:
            i |= ((x >> (sx.bit_length() - 1)) & 1) << bit; bit += 1; sx <<= 1
        if sy < h:
            i |= ((y >> (sy.bit_length() - 1)) & 1) << bit; bit += 1; sy <<= 1
    return i


def texel(i):
    p = b[i * bpp:(i + 1) * bpp]
    return p[0] if bpp == 1 else (p[1], p[2], p[3])   # A8R8G8B8 big-endian bytes: A R G B


mode = 'L' if bpp == 1 else 'RGB'
raw = Image.new(mode, (w, h)); swz = Image.new(mode, (w, h))
raw.putdata([texel(y * w + x) for y in range(h) for x in range(w)])
swz.putdata([texel(morton(x, y)) for y in range(h) for x in range(w)])
raw.save(prefix + '_raw.png'); swz.save(prefix + '_swz.png')
nz = sum(1 for v in b[::bpp] if v)
print('%s_raw.png / _swz.png written (%dx%d, %d of %d texels non-zero, max %d)' % (prefix, w, h, nz, w * h, max(b)))
