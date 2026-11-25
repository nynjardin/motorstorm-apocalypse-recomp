"""guest_dxt.py <out.png> <guest ea hex>:<w>:<h> [...]
DXT1 textures read from the memory of the running game and decoded (colour, then alpha), side by side.
The ea of a local-memory texture is its "off=" in a capture manifest (0xC... = local memory).
System python (PIL).
"""
import sys, struct, ctypes, io
sys.path.insert(0, 'I:/Projets/Recomp/MotorStorm/scripts')
import guest_peek as gp
from PIL import Image
def dds(w, h, data):
    hdr = struct.pack('<4sIIIIIII44xII4sIIIIIIIIII', b'DDS ', 124, 0x81007, h, w, len(data), 0, 1,
                      32, 4, b'DXT1', 0, 0, 0, 0, 0, 0x1000, 0, 0, 0, 0)
    return hdr + data
k32 = ctypes.windll.kernel32
h = k32.OpenProcess(gp.PROCESS_VM_READ | gp.PROCESS_QUERY_INFORMATION, False, gp.find_pid())
base = gp.find_vm_base(h)
out = sys.argv[1]
tiles = []
for a in sys.argv[2:]:
    ea, w, hh = a.split(':'); ea = int(ea, 16); w = int(w); hh = int(hh)
    n = w * hh // 2
    buf = (ctypes.c_ubyte * n)(); got = ctypes.c_size_t()
    ok = k32.ReadProcessMemory(h, ctypes.c_void_p(base + ea), buf, n, ctypes.byref(got))
    b = bytes(buf[:got.value])
    print('%08X %dx%d read=%d ok=%d nonzero=%d first=%s' % (ea, w, hh, got.value, ok, sum(1 for x in b[::97] if x), b[:16].hex()))
    im = Image.open(io.BytesIO(dds(w, hh, b))).convert('RGBA')
    rgb = im.convert('RGB').resize((384, 384 * hh // w)); al = im.split()[3].convert('RGB').resize((384, 384 * hh // w))
    tiles += [rgb, al]
s = Image.new('RGB', (384 * len(tiles), 384), (60, 0, 60))
for i, t in enumerate(tiles): s.paste(t, (i * 384, 0))
s.save(out); print(out)
