# elfpeek.py <vaddr hex> <len> [...]: hex+ascii dump of the decrypted EBOOT at guest addresses.
# elfpeek.py --find <ascii>: guest addresses of a string.
import struct, sys

ELF = "I:/Projets/Recomp/MotorStorm/game/BCES00484/EBOOT.elf"
d = open(ELF, "rb").read()
phoff = struct.unpack(">Q", d[0x20:0x28])[0]
phentsize, phnum = struct.unpack(">HH", d[0x36:0x3A])
segs = []
for i in range(phnum):
    p = d[phoff + i * phentsize: phoff + (i + 1) * phentsize]
    ptype, flags, off, vaddr, paddr, filesz, memsz, align = struct.unpack(">IIQQQQQQ", p)
    if ptype == 1:
        segs.append((vaddr, off, filesz))


def v2o(v):
    for vaddr, off, filesz in segs:
        if vaddr <= v < vaddr + filesz:
            return off + v - vaddr
    return None


def o2v(o):
    for vaddr, off, filesz in segs:
        if off <= o < off + filesz:
            return vaddr + o - off
    return None


a = sys.argv[1:]
if a and a[0] == "--find":
    s = a[1].encode()
    i = d.find(s)
    while i >= 0:
        b = i
        while b > 0 and 32 <= d[b - 1] < 127:
            b -= 1
        e = d.find(b"\0", i)
        v = o2v(b)
        print("%s %s" % ("%08X" % v if v is not None else "(off %X)" % b, d[b:e].decode("latin-1")[:150]))
        i = d.find(s, e)
else:
    for k in range(0, len(a), 2):
        v, n = int(a[k], 16), int(a[k + 1], 0)
        o = v2o(v)
        if o is None:
            print("%08X: not in file" % v)
            continue
        for r in range(0, n, 16):
            c = d[o + r:o + r + 16]
            print("%08X  %-48s %s" % (v + r, c.hex(" "), "".join(chr(x) if 32 <= x < 127 else "." for x in c)))
        print()
