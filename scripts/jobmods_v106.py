"""WWS job modules of the 1.06 EBOOT: where are the disc's lifted modules in it?

    python scripts/jobmods_v106.py            # report only
    python scripts/jobmods_v106.py --write    # also (re)write the PORT_V106 block of port/spu/jobmods_register.c

The disc's job modules (port/spu/jobmods_register.c) are registered by the EA of the module in the EBOOT's
data and verified byte for byte against the code lifted from it. The 1.06 EBOOT is another link: the same
module bytes sit at other addresses (or differ: recompiled). For every registration this finds the code
array's bytes in game/BCES00484_106/EBOOT.elf and gives the new EA; the extra registrations go into a
function between the markers  /* PORT_V106 BEGIN */ ... /* PORT_V106 END */  (idempotent), called at the end
of port_jobmods_register_all under #ifdef PORT_V106. Modules not found stay interpreted: listed.
"""
import os, re, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..'))
TU = os.path.join(ROOT, 'port', 'spu', 'jobmods_register.c')
BEGIN, END = '/* PORT_V106 BEGIN */', '/* PORT_V106 END */'


def load(title):
    d = open(os.path.join(ROOT, 'game', title, 'EBOOT.elf'), 'rb').read()
    ph = struct.unpack('>Q', d[0x20:0x28])[0]
    n = struct.unpack('>H', d[0x38:0x3a])[0]
    segs = []
    for i in range(n):
        t, fl, off, va, pa, fs, ms, al = struct.unpack('>IIQQQQQQ', d[ph + i * 56:ph + i * 56 + 56])
        if t == 1 and fs:
            segs.append((va, d[off:off + fs]))
    return segs


def find_all(segs, needle):
    out = []
    for va, b in segs:
        i = b.find(needle)
        while i >= 0:
            out.append(va + i)
            i = b.find(needle, i + 1)
    return out


def at(segs, ea, n):
    for va, b in segs:
        if va <= ea < va + len(b):
            return b[ea - va:ea - va + n]
    return b''


src = open(TU, encoding='latin-1').read()
if BEGIN in src:                                   # work on the text without our block
    a, b = src.index(BEGIN), src.index(END) + len(END)
    src = src[:a] + src[b:]
arrays = {}
for m in re.finditer(r'static const uint8_t code_(\d+)\[(\d+)\] = \{(.*?)\n\};', src, re.S):
    arrays[int(m.group(1))] = bytes(int(x, 16) for x in re.findall(r'0x([0-9A-Fa-f]{2})', m.group(3)))
blocks = re.findall(r'if \(jm_on\((\d+)\)\) \{ spu_overlay_code_segment seg = \{(0x[0-9A-F]+)u, sizeof code_\1, code_\1\};'
                    r'.*?spu_overlay_register_verified_region\((0x[0-9A-F]{8})u, (0x[0-9A-F]+)u, (jm_span\([^;]*?\)), (\d+), &seg, 1\)',
                    src, re.S)
disc, v106 = load('BCES00484'), load('BCES00484_106')
lines, missing, same = [], [], 0
for id_, seglsa, ea, lsa, span, id2 in blocks:
    id_ = int(id_)
    ea = int(ea, 16)
    code = arrays[id_]
    k = None
    head = code[:64]
    # offset of the array inside the module image of the disc EBOOT
    for off in range(0, 0x200, 4):
        if at(disc, ea + off, 64) == head:
            k = off
            break
    if k is None:
        missing.append((id_, 'array not found in the disc EBOOT at the registered EA'))
        continue
    hits = [h for h in find_all(v106, head) if at(v106, h, len(code)) == code]
    if not hits:
        part = [h for h in find_all(v106, head)]
        missing.append((id_, 'bytes differ in 1.06' if part else 'not found'))
        continue
    new_ea = hits[0] - k
    if len(hits) > 1:
        print('note: id', id_, 'found', len(hits), 'times, taking', hex(new_ea))
    if new_ea == ea:
        same += 1
    lines.append((id_, seglsa, ea, new_ea, lsa, span, id2))
print('%d registrations, %d found in 1.06 (%d at the same EA), %d missing' % (len(blocks), len(lines), same, len(missing)))
for i, why in missing:
    print('  missing id %d: %s' % (i, why))
if '--write' in sys.argv:
    out = [BEGIN, '#ifdef PORT_V106',
           '/* the same modules at their 1.06 EBOOT addresses (scripts/jobmods_v106.py) */',
           'static void port_jobmods_register_v106(void)', '{']
    for id_, seglsa, ea, new_ea, lsa, span, id2 in lines:
        if new_ea == ea:
            continue
        out.append('    if (jm_on(%d)) { spu_overlay_code_segment seg = {%su, sizeof code_%d, code_%d}; if (!getenv("PORT_JOBMODS_FULLSPAN")) seg.size = jm_code_len(code_%d, sizeof code_%d);'
                   % (id_, seglsa, id_, id_, id_, id_))
        out.append('      spu_overlay_register_verified_region(0x%08Xu, %su, %s, %s, &seg, 1); }' % (new_ea, lsa, span, id2))
    out += ['}', '#endif', END, '']
    block = '\n'.join(out)
    # before port_jobmods_register_all, called at its end
    t = src
    t = t.replace('void port_jobmods_register_all(void)\n{', block + '\nvoid port_jobmods_register_all(void)\n{', 1)
    t = t.replace('    spu_begin_image(0);\n}\n\n#include <stdlib.h>',
                  '#ifdef PORT_V106\n    port_jobmods_register_v106();\n#endif\n    spu_begin_image(0);\n}\n\n#include <stdlib.h>', 1)
    open(TU, 'w', encoding='latin-1', newline='').write(t)
    print('wrote', TU)
