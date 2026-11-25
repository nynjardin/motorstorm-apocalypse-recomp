"""Trim each WWS job module's verified region to its real code (stop at the first >=1 KB run of
zero bytes = the module's BSS/buffers). A DMA GET into a buffer inside the registered span drops
the lifted residency mid-job (spu_overlay_note_get), which desynchronises the host frames."""
import re, shutil, os
p = r'I:\Projets\Recomp\MotorStorm\port\spu\jobmods_register.c'
bak = r'E:\jobmods_register.c.bak'
if not os.path.exists(bak):
    shutil.copy(p, bak)
s = open(p, encoding='latin-1', newline='').read()
nl = '\r\n' if '\r\n' in s[:5000] else '\n'

helper = r'''/* Length of a job module's code: up to the first run of >= 1 KB of zero bytes (its BSS and
 * buffers, which the job DMAs into; a GET there must not drop the lifted residency). */
static uint32_t jm_code_len(const uint8_t* b, uint32_t n)
{
    uint32_t run = 0;
    for (uint32_t i = 0; i < n; i++) {
        if (b[i]) { run = 0; continue; }
        if (++run >= 1024) { uint32_t end = i + 1 - run; return (end + 15u) & ~15u; }
    }
    return n;
}
static uint32_t jm_span(uint32_t seg_lsa, uint32_t base, uint32_t len, uint32_t span)
{
    if (getenv("PORT_JOBMODS_FULLSPAN")) return span;   /* old behaviour, for A/B */
    uint32_t s = seg_lsa - base + len;
    return s < span ? s : span;
}
'''
anchor = 'static int jm_on(int id)'
assert anchor in s and 'jm_code_len' not in s
s = s.replace(anchor, helper.replace('\n', nl) + anchor, 1)

pat = re.compile(r'static const spu_overlay_code_segment seg = \{(0x[0-9A-Fa-f]+u), sizeof (code_\d+), (code_\d+)\};'
                 r'(.*?)spu_overlay_register_verified_region\((0x[0-9A-Fa-f]+u), (0x[0-9A-Fa-f]+u), (0x[0-9A-Fa-f]+u),',
                 re.S)
def rep(m):
    lsa, c1, c2, mid, ea, base, span = m.groups()
    return ('spu_overlay_code_segment seg = {%s, sizeof %s, %s};' % (lsa, c1, c2) +
            ' if (!getenv("PORT_JOBMODS_FULLSPAN")) seg.size = jm_code_len(%s, sizeof %s);' % (c1, c1) +
            mid + 'spu_overlay_register_verified_region(%s, %s, jm_span(%s, %s, seg.size, %s),' % (ea, base, lsa, base, span))
s, n = pat.subn(rep, s)
print('patched', n)
open(p, 'w', encoding='latin-1', newline='').write(s)
