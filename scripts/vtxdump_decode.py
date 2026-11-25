"""vtxdump_decode.py <run.log>
The [VTXDUMP] blocks of a run (VTX_FP_DUMP, VTX_FP_DUMP_FILE, VTX_FP_DUMP_OWN: toolkit patch #64 tools),
each distinct (program, primitive, count) once, attributes decoded (float, half, bytes).
System python (numpy).
"""
import re, sys
import numpy as np
lines = [l.rstrip('\n') for l in open(sys.argv[1], encoding='latin-1') if 'VTXDUMP' in l]
def dec(t, size, e):
    # RSX vertex types: 1 s16n, 2 float, 3 half, 4 u8n, 5 s16, 6 cmp(11-11-10), 7 u8
    if t == 2: return tuple(round(float(x), 3) for x in np.frombuffer(e[:4*size], dtype='>f4'))
    if t == 3: return tuple(round(float(x), 3) for x in np.frombuffer(e[:2*size], dtype='>f2'))
    if t in (4, 7): return tuple(e[:size])
    if t == 1: return tuple(round(float(x)/32767, 3) for x in np.frombuffer(e[:2*size], dtype='>i2'))
    if t == 5: return tuple(int(x) for x in np.frombuffer(e[:2*size], dtype='>i2'))
    return e.hex()
seen = set(); i = 0
while i < len(lines):
    m = re.search(r'fp=0x(\w+) prim=(\d+) first=(\d+) count=(\d+) (\w+) .*frame (\d+)', lines[i])
    if m and (m.group(1), m.group(2), m.group(4)) not in seen:
        seen.add((m.group(1), m.group(2), m.group(4)))
        print('fp=%s prim=%s first=%s count=%s %s frame %s' % m.groups())
        j = i + 1
        while j < len(lines) and 'fp=0x' not in lines[j]:
            a = re.search(r'attr +(\d+) type (\d+) size (\d+) stride (\d+) offset 0x(\w+) freq (\d+):(.*)', lines[j])
            if a:
                t, size = int(a.group(2)), int(a.group(3))
                elems = [bytes(int(x, 16) for x in e.split()) for e in a.group(7).split('|')[1:]]
                print('   a%-2s t%d s%d st%-2s off %s:' % (a.group(1), t, size, a.group(4), a.group(5)), ' '.join(str(dec(t, size, e)) for e in elems)[:420])
            j += 1
    i += 1
