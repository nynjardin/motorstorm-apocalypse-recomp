# Names of the WWS job modules of MotorStorm Apocalypse: the EBOOT has a table of 12-byte entries
# {name string, module image address, image size} at 0x010F7384+ (found from the "occjob" string).
# Prints: name, image address in the EBOOT, size, then the image id and the lifted module of
# port/spu/jobmods_register.c registered for that address (the id of PORT_JOBMODS_EXCLUDE, of the
# [pm-end] lines and of ftrace_jobs.py; the module name is the directory under port/spu).
#   python scripts/jobmod_names.py [EBOOT.elf]
import sys, os, struct, glob, re
elf = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'game', 'BCES00484', 'EBOOT.elf')
d = open(elf, 'rb').read()
phoff, = struct.unpack_from('>Q', d, 0x20); phentsize, phnum = struct.unpack_from('>HH', d, 0x36)
segs = []
for i in range(phnum):
    p_type, p_flags, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_align = struct.unpack_from('>IIQQQQQQ', d, phoff + i * phentsize)
    if p_type == 1 and p_filesz: segs.append((p_offset, p_vaddr, p_filesz))
def off(va):
    for o, v, s in segs:
        if v <= va < v + s: return o + va - v
    return -1
def cstr(va):
    o = off(va)
    if o < 0: return None
    e = d.find(b'\0', o)
    s = d[o:e]
    return s.decode('latin-1') if 0 < len(s) < 64 and all(32 <= c < 127 for c in s) else None
reg = {}
rp = os.path.join(os.path.dirname(__file__), '..', 'port', 'spu', 'jobmods_register.c')
if os.path.exists(rp):
    last = None
    for line in open(rp, encoding='latin-1'):
        m = re.search(r'spu_begin_image\((\d+)\); (\w+)_spu_recomp_register', line)
        if m: last = (int(m.group(1)), m.group(2))
        m = re.search(r'spu_overlay_register_verified_region\(0x([0-9A-Fa-f]+)u', line)
        if m and last: reg[int(m.group(1), 16)] = last; last = None
anchor = 0x010F7534          # entry of "occjob"
lo = anchor
while cstr(struct.unpack_from('>I', d, off(lo - 12))[0]): lo -= 12
va = lo
while True:
    name_p, img, size = struct.unpack_from('>III', d, off(va))
    nm = cstr(name_p)
    if not nm: break
    r = reg.get(img)
    print('%-44s image %08X size %6X  %s' % (nm, img, size, ('id %d  %s' % r) if r else 'not lifted'))
    va += 12
