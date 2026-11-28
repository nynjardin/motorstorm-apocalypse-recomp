"""Extend each WWS job module's verified region to ALL of its lifted code.

lift_jobmods.py's code_end only follows direct branches from the seeded entries, but the
lifter also lifts code reached through indirect branches (e.g. job 203: 0x50DC is reached
by a computed branch, and its `brsl 0x55E8` calls code past code_end=0x55C8). That code
was outside the registered span: lookups there miss the resident job, the interpreter
takes over in the middle of lifted C frames and the PM run ends at depth 0 on a return
address ([pm-end] pc == lr), stranding the job list.

New end = one past the highest instruction reachable (direct branches + fallthrough)
from every lifted function entry of the module. Rewrites in port/spu/jobmods_register.c
the expected bytes `code_<id>[]` (= module bytes [0x4030, end)) and the span constant,
and code_end in jobmods_manifest.json. jm_code_len's zero-run trim still applies; the
script warns when it would cut before the last lifted function.

usage: extend_jobmods.py [--dry-run]
"""
import json, os, re, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..'))
SPU = os.path.join(ROOT, 'port', 'spu')
TITLE = os.environ.get('MS_TITLE', 'BCES00484')       # BCES00484_106: the 1.06 modules (_106 files)
SUF = '' if TITLE == 'BCES00484' else '_106'
REG = os.path.join(SPU, 'jobmods_register%s.c' % SUF)
MAN = os.path.join(SPU, 'jobmods_manifest%s.json' % SUF)
ELF = os.path.join(ROOT, 'game', TITLE, 'EBOOT.elf')
BAK = r'E:\jobmods_register%s.c.before_extend.bak' % SUF
TOOLS = os.path.normpath(os.path.join(ROOT, '..', 'ps3recomp', 'tools'))
sys.path.insert(0, TOOLS)
sys.path.insert(0, HERE)
import lift_jobmods as L  # noqa: E402
import jobmod_pc as J     # noqa: E402

BASE = 0x4000


def zero_cut(b):
    """jm_code_len(): offset of the first >= 1 KB zero run (rounded up to 16), or len."""
    run = 0
    for i, x in enumerate(b):
        if x:
            run = 0
            continue
        run += 1
        if run >= 1024:
            end = i + 1 - run
            return (end + 15) & ~15
    return len(b)


def fmt_array(name, data, nl):
    lines = ['static const uint8_t %s[%d] = {' % (name, len(data))]
    for i in range(0, len(data), 16):
        lines.append('    ' + ','.join('0x%02X' % x for x in data[i:i + 16]) + ',')
    lines.append('};')
    return nl.join(lines)


def main():
    dry = '--dry-run' in sys.argv
    elf = open(ELF, 'rb').read()
    raws = dict(L.find_engine_modules(elf))
    s = open(REG, encoding='latin-1', newline='').read()
    nl = '\r\n' if '\r\n' in s[:5000] else '\n'
    man = json.load(open(MAN))
    by_name = {m['name']: m for m in man}
    changed = 0
    for jid, m, funcs in sorted(J.load()):
        raw = raws[m['ea']]
        hi = BASE + len(raw)
        # target = the manifest's code_end (scripts/relift_jobmods.py sets it to cover all
        # lifted code); current span = what the register says now.
        new_end = m['code_end']
        sm = re.search(r'jm_span\(0x4030u, 0x4000u, seg\.size, 0x([0-9A-F]+)u\), %d,' % jid, s)
        if not sm:
            sys.exit('job %d: span not found' % jid)
        old_span = int(sm.group(1), 16)
        real = [f for f in funcs if f < new_end]
        cut = BASE + 0x30 + zero_cut(raw[0x30:new_end - BASE])
        warn = '  WARNING zero-run cut at 0x%X < last func 0x%X' % (cut, max(real)) if cut <= max(real) else ''
        print('job %d %s: span end 0x%X -> 0x%X (module end 0x%X)%s'
              % (jid, m['name'], BASE + old_span, new_end, hi, warn))
        if new_end == BASE + old_span:
            continue
        new_span = new_end - BASE
        data = raw[0x30:new_end - BASE]
        arr = re.compile(r'static const uint8_t code_%d\[\d+\] = \{.*?\};' % jid, re.S)
        s, n1 = arr.subn(lambda _m: fmt_array('code_%d' % jid, data, nl), s, count=1)
        span_pat = re.compile(r'(jm_span\(0x4030u, 0x4000u, seg\.size, )0x%Xu(\), %d,)' % (old_span, jid))
        s, n2 = span_pat.subn(lambda mm: mm.group(1) + '0x%Xu' % new_span + mm.group(2), s, count=1)
        if n1 != 1 or n2 != 1:
            sys.exit('job %d: pattern not found (array %d, span %d)' % (jid, n1, n2))
        changed += 1
    print('changed', changed)
    if dry or not changed:
        return
    if not os.path.exists(BAK):
        shutil.copy(REG, BAK)
    open(REG, 'w', encoding='latin-1', newline='').write(s)


if __name__ == '__main__':
    main()
