# tocref.py <guest addr hex> [...]: where the EBOOT stores that 32-bit pointer, and the matching
# TOC-relative displacement (TOC 0x01449A70) to grep in the lifted code.
import struct, sys

ELF = "I:/Projets/Recomp/MotorStorm/game/BCES00484/EBOOT.elf"
TOC = 0x01449A70
d = open(ELF, "rb").read()
phoff = struct.unpack(">Q", d[0x20:0x28])[0]
phentsize, phnum = struct.unpack(">HH", d[0x36:0x3A])
segs = []
for i in range(phnum):
    p = d[phoff + i * phentsize: phoff + (i + 1) * phentsize]
    ptype, flags, off, vaddr, paddr, filesz, memsz, align = struct.unpack(">IIQQQQQQ", p)
    if ptype == 1:
        segs.append((vaddr, off, filesz))
for a in sys.argv[1:]:
    v = int(a, 16)
    pat = struct.pack(">I", v)
    for vaddr, off, filesz in segs:
        i = d.find(pat, off, off + filesz)
        while i >= 0:
            if (i - off) % 4 == 0:
                ea = vaddr + i - off
                disp = ea - TOC
                print("%08X stored at %08X  toc%+d (%s0x%X)" % (v, ea, disp, "-" if disp < 0 else "", abs(disp)))
            i = d.find(pat, i + 1, off + filesz)
