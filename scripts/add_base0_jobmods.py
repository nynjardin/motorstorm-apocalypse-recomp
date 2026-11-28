"""Lift the WWS job modules whose header carries load base 0, and add them to the port.

lift_jobmods.find_engine_modules() only took headers with 0x4000 at +0x28. The EBOOT holds ten
more modules (C0DEC0DE magic, entry offset 0x30, +0x28 = 0) that the job manager loads at LS
0x4000 all the same: they ran in the SPU interpreter, silently (2026-11-22: sig 42071202...,
EA 0x0139B500, ~54 runs a second in a race, a fifth of one job lane's busy time). The toolkit's
finder now accepts base 0 (local patch); this script handles the modules that are not in
port/spu/jobmods_manifest.json yet:

  1. lift each (merged chunks, like relift_jobmods.py --merge) with the same code-end fix-point
     as relift_jobmods.py (every lifted non-stub entry is a seed),
  2. append its manifest entry,
  3. append its registration to port/spu/jobmods_register.c (extern, code_<id>[] = module bytes
     [0x30, code_end), the jm_on(<id>) block): ids continue after the highest existing one, the
     existing ids and the file's hand edits are untouched.

Then: scripts/direct_bie.py, port\\build.bat configure.
usage: add_base0_jobmods.py [--dry-run]
Backup of the register TU: E:/ms_perf/jobmods_register.c.before_base0
"""
import hashlib, json, os, re, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import relift_jobmods as R   # noqa: E402  (chdir to the toolkit tools, imports lift_jobmods as L)

L, SPU, MAN, ELF, BASE = R.L, R.SPU, R.MAN, R.ELF, R.BASE
REG = R.REG
BAK = 'E:/ms_perf/jobmods_register%s.c.before_base0' % R.SUF


def fmt_array(name, data, nl):
    lines = ['static const uint8_t %s[%d] = {' % (name, len(data))]
    for i in range(0, len(data), 16):
        lines.append('    ' + ','.join('0x%02X' % x for x in data[i:i + 16]) + ',')
    lines.append('};')
    return nl.join(lines)


def main():
    dry = '--dry-run' in sys.argv
    found = L.find_engine_modules(open(ELF, 'rb').read())
    by_name = {}
    for ea, raw in found:
        entry_off = struct.unpack_from(">I", raw, 0x10)[0]
        name = "jobmod_%s_e%04X" % (hashlib.sha1(raw).hexdigest()[:12], entry_off)
        by_name.setdefault(name, (raw, []))[1].append(ea)
    man = json.load(open(MAN))
    known = {m['name'] for m in man}
    new = [(n, v) for n, v in sorted(by_name.items(), key=lambda kv: kv[1][1][0]) if n not in known]
    print('%d module(s) in the ELF, %d in the manifest, %d to add' % (len(by_name), len(man), len(new)))
    if not new:
        return
    reg = open(REG, encoding='latin-1', newline='').read()
    nl = '\r\n' if '\r\n' in reg[:5000] else '\n'
    next_id = max(int(x) for x in re.findall(r'if \(jm_on\((\d+)\)\)', reg)) + 1
    tmp_elf = os.path.join(SPU, '_tmp_base0.elf')
    externs, arrays, blocks = [], [], []
    for name, (raw, eas) in new:
        base_field = struct.unpack_from(">I", raw, 0x28)[0]
        ce = L.module_code_end(raw, name)
        print('%s: EA %s header base 0x%X size 0x%X, first code_end %s' % (
            name, ','.join('0x%08X' % e for e in eas), base_field, len(raw), hex(ce) if ce else None))
        if ce is None:
            print('  SKIP: no reachable code')
            continue
        if dry:
            continue
        m = None
        for it in range(8):
            m = L.lift_module(raw, name, SPU, tmp_elf, True, ce)
            if not m:
                sys.exit('lift failed: ' + name)
            nxt = R.code_end_from(raw, name, R.lifted_entries(name))
            nxt = max(nxt or ce, ce)
            if nxt == ce:
                break
            print('  code_end 0x%X -> 0x%X (pass %d)' % (ce, nxt, it + 1))
            ce = nxt
        m.update(ea=eas[0], eas=eas, code_end=ce)
        man.append(m)
        jid = next_id
        next_id += 1
        data = raw[0x30:ce - BASE]
        externs.append('extern void %sspu_recomp_register(void);' % m['prefix'])
        arrays.append(fmt_array('code_%d' % jid, data, nl))
        b = []
        for k, ea in enumerate(eas):
            if k == 0:
                b.append('    if (jm_on(%d)) { spu_overlay_code_segment seg = {0x4030u, sizeof code_%d, code_%d}; '
                         'if (!getenv("PORT_JOBMODS_FULLSPAN")) seg.size = jm_code_len(code_%d, sizeof code_%d);'
                         % (jid, jid, jid, jid, jid))
                b.append('      spu_begin_image(%d); %sspu_recomp_register();   /* %s entry 0x%X (header base 0) */'
                         % (jid, m['prefix'], name, m['entry']))
            b.append('      if (!spu_overlay_register_verified_region(0x%08Xu, 0x4000u, jm_span(0x4030u, 0x4000u, '
                     'seg.size, 0x%Xu), %d, &seg, 1))' % (ea, ce - BASE, jid))
            b.append('          fprintf(stderr, "[jobmods] image %d: verified region 0x%08X not registered, '
                     'interpreted\\n");' % (jid, ea))
        b.append('    }')
        blocks.append(nl.join(b))
        print('  -> job id %d, code_end 0x%X, %d function(s)' % (jid, ce, m['funcs']))
    if os.path.exists(tmp_elf):
        os.remove(tmp_elf)
    if dry or not blocks:
        return
    json.dump(man, open(MAN, 'w'), indent=2)
    if not os.path.exists(BAK):
        shutil.copy(REG, BAK)
    # externs after the last existing one, arrays before the registration function, blocks
    # before the closing spu_begin_image(0)
    last_ext = list(re.finditer(r'extern void jobmod_\w+_spu_recomp_register\(void\);', reg))[-1]
    reg = reg[:last_ext.end()] + nl + nl.join(externs) + reg[last_ext.end():]
    tail = reg.rindex('    spu_begin_image(0);')
    reg = reg[:tail] + nl.join(blocks) + nl + reg[tail:]
    first_block = re.search(r'^[^\n]*\bvoid port_jobmods_register_all\(void\)', reg, re.M)
    if not first_block:
        sys.exit('port_jobmods_register_all not found in the register TU')
    reg = reg[:first_block.start()] + (nl + nl).join(arrays) + nl + nl + reg[first_block.start():]
    open(REG, 'w', encoding='latin-1', newline='').write(reg)
    print('register TU updated (backup %s)' % BAK)


if __name__ == '__main__':
    main()
