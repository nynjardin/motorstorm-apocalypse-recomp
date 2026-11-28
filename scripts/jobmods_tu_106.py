"""Make port/spu/jobmods_register_106.c (the 1.06 EBOOT's job modules) from the toolkit's raw output.

    python scripts/jobmods_tu_106.py <raw register TU of tools/lift_jobmods.py>

The raw TU has none of the port's hand edits. This keeps the disc TU's preamble (jm_on / jm_code_len /
jm_span helpers, PORT_JOBMODS_* switches) and its constructor gate, and rewrites each block of the raw
one the way scripts/trim_jobmods.py does for the disc (guard by jm_on, verified span trimmed to the code).
Then, with MS_TITLE=BCES00484_106: relift_jobmods.py --merge, extend_jobmods.py, add_base0_at8000.py,
direct_bie.py (docs/spu.md "Regeneration order"; add_base0_jobmods / relift_base0 are not needed: the
tool finds the base-0 modules itself since patch #21).
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SPU = os.path.normpath(os.path.join(HERE, '..', 'port', 'spu'))
NL2 = chr(13) + chr(10)
disc = open(os.path.join(SPU, 'jobmods_register.c'), encoding='latin-1', newline='').read().replace(NL2, chr(10))
raw = open(sys.argv[1], encoding='latin-1', newline='').read().replace(NL2, chr(10))
anchor = 'extern void spu_begin_image(int image_id);\n'
pre = disc[:disc.index(anchor) + len(anchor)]
body = raw[raw.index(anchor) + len(anchor):]
# constructor of the disc TU (PORT_JOBMODS gate)
tail = disc[disc.index('#include <stdlib.h>\n__attribute__((constructor))'):]
body = body[:body.index('__attribute__((constructor))')]

blk = re.compile(r'    \{ static const spu_overlay_code_segment seg = \{(0x[0-9A-Fa-f]+u), sizeof (code_(\d+)), code_\3\};(.*?)'
                 r'spu_overlay_register_verified_region\((0x[0-9A-Fa-f]+u), (0x[0-9A-Fa-f]+u), (0x[0-9A-Fa-f]+u),', re.S)


def rep(m):
    lsa, c, id_, mid, ea, base, span = m.groups()
    return ('    if (jm_on(%s)) { spu_overlay_code_segment seg = {%s, sizeof %s, %s}; if (!getenv("PORT_JOBMODS_FULLSPAN")) seg.size = jm_code_len(%s, sizeof %s);'
            % (id_, lsa, c, c, c, c) + mid +
            'spu_overlay_register_verified_region(%s, %s, jm_span(%s, %s, seg.size, %s),' % (ea, base, lsa, base, span))


body, n = blk.subn(rep, body)
print('blocks rewritten:', n)
out = pre + body + tail
open(os.path.join(SPU, 'jobmods_register_106.c'), 'w', encoding='latin-1', newline='').write(out)
print('wrote jobmods_register_106.c')
