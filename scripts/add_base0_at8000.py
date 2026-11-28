"""Second lift of the relocatable (base-0) WWS job modules, at LS 0x8000.

Seen with SPU_DUMP_OVL=<dir>,0x8000 in a race (2026-11-22): the job module
jobmod_135114c81d32_e0030 (id 242, at LS 0x4000) streams other base-0 modules -- EA
0x01399300, 0x0139A300, 0x013B0480... -- into LS 0x8000 and calls them: they are plug-ins,
which is why they are position independent. Lifted code is tied to its addresses, so each
module gets a second lift linked at 0x8000 (directory <name>_b8000, same code end and the
same function entries as its 0x4000 lift, shifted) and a second verified region at LS 0x8000
that reuses the 0x4000 lift's expected bytes (the module is unrelocated in memory).

Run after add_base0_jobmods.py + relift_base0.py + extend_jobmods.py (it reads their manifest
and code_<id>[] arrays). Idempotent: modules already registered at 0x8000 are skipped; rerun it
after a relift_base0.py (it relifts the _b8000 copies and updates their spans).
Then: port\\build.bat configure.
usage: add_base0_at8000.py [--dry-run]
"""
import hashlib, json, os, re, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import relift_jobmods as R   # noqa: E402

L, SPU, MAN, ELF, BASE = R.L, R.SPU, R.MAN, R.ELF, R.BASE
REG = R.REG
BAK = 'E:/ms_perf/jobmods_register%s.c.before_b8000' % R.SUF
NEW_BASE = 0x8000
HOSTS = {'jobmod_135114c81d32_e0030'}     # stays at 0x4000 only (it is the one that loads the others)
FIRST_ID = 260                            # image ids of the 0x8000 lifts (0x4000 lifts: 200..248)


def main():
    dry = '--dry-run' in sys.argv
    found = L.find_engine_modules(open(ELF, 'rb').read())
    raws = {}
    for ea, raw in found:
        entry_off = struct.unpack_from(">I", raw, 0x10)[0]
        raws["jobmod_%s_e%04X" % (hashlib.sha1(raw).hexdigest()[:12], entry_off)] = raw
    man = json.load(open(MAN))
    reg = open(REG, encoding='latin-1', newline='').read()
    nl = '\r\n' if '\r\n' in reg[:5000] else '\n'
    tmp_elf = os.path.join(SPU, '_tmp_b8000.elf')
    externs, blocks = [], []
    used = [int(x) for x in re.findall(r'if \(jm_on\((\d+)\)\)', reg)]
    next_id = max([FIRST_ID - 1] + [i for i in used if i >= FIRST_ID]) + 1
    shift = NEW_BASE - BASE
    for m in man:
        name = m['name']
        raw = raws.get(name)
        if raw is None or struct.unpack_from(">I", raw, 0x28)[0] != 0 or name in HOSTS:
            continue
        # the 0x4000 lift's id: its jm_on block names the module in a comment
        mo = re.search(r'spu_begin_image\((\d+)\); %sspu_recomp_register\(\);' % re.escape(m['prefix']), reg)
        if not mo:
            print('%s: no 0x4000 registration, skipped' % name)
            continue
        src_id = int(mo.group(1))
        name2 = name + '_b8000'
        entries = sorted(R.lifted_entries(name))
        ce2 = m['code_end'] + shift
        print('%s (id %d): relift at 0x%X, code_end 0x%X, %d entries' % (name, src_id, NEW_BASE, ce2, len(entries)))
        if dry:
            continue
        L.EXTRA_FUNCS = [hex(e + shift) for e in entries]
        m2 = L.lift_module(raw, name2, SPU, tmp_elf, True, ce2, base=NEW_BASE)
        L.EXTRA_FUNCS = []
        if not m2:
            sys.exit('lift failed: ' + name2)
        span = ce2 - NEW_BASE
        old = re.search(r'spu_begin_image\((\d+)\); %sspu_recomp_register\(\);' % re.escape(m2['prefix']), reg)
        if old:      # already registered: only the span can have changed
            jid = int(old.group(1))
            reg, n = re.subn(r'(jm_span\(0x8030u, 0x8000u, seg\.size, )0x[0-9A-F]+u(\), %d,)' % jid,
                             lambda mm: mm.group(1) + '0x%Xu' % span + mm.group(2), reg)
            print('  already registered as id %d (%d span(s) updated)' % (jid, n))
            continue
        jid = next_id
        next_id += 1
        externs.append('extern void %sspu_recomp_register(void);' % m2['prefix'])
        b = ['    if (jm_on(%d)) { spu_overlay_code_segment seg = {0x8030u, sizeof code_%d, code_%d}; '
             'if (!getenv("PORT_JOBMODS_FULLSPAN")) seg.size = jm_code_len(code_%d, sizeof code_%d);'
             % (jid, src_id, src_id, src_id, src_id),
             '      spu_begin_image(%d); %sspu_recomp_register();   /* %s: plug-in copy at LS 0x8000 of id %d */'
             % (jid, m2['prefix'], name2, src_id)]
        for ea in m['eas']:
            b.append('      if (!spu_overlay_register_verified_region(0x%08Xu, 0x8000u, jm_span(0x8030u, 0x8000u, '
                     'seg.size, 0x%Xu), %d, &seg, 1))' % (ea, span, jid))
            b.append('          fprintf(stderr, "[jobmods] image %d: verified region 0x%08X at LS 0x8000 not '
                     'registered, interpreted\\n");' % (jid, ea))
        b.append('    }')
        blocks.append(nl.join(b))
        print('  -> id %d, %d function(s)' % (jid, m2['funcs']))
    if os.path.exists(tmp_elf):
        os.remove(tmp_elf)
    if dry:
        return
    if not os.path.exists(BAK):
        shutil.copy(REG, BAK)
    if externs:
        last_ext = list(re.finditer(r'extern void jobmod_\w+_spu_recomp_register\(void\);', reg))[-1]
        reg = reg[:last_ext.end()] + nl + nl.join(externs) + reg[last_ext.end():]
        tail = reg.rindex('    spu_begin_image(0);')
        reg = reg[:tail] + nl.join(blocks) + nl + reg[tail:]
    open(REG, 'w', encoding='latin-1', newline='').write(reg)
    print('register TU updated (backup %s)' % BAK)


if __name__ == '__main__':
    main()
