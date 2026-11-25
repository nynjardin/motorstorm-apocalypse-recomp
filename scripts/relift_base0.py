"""Relift the base-0 (relocatable) WWS job modules from their real main function.

These modules (names jobmod_*_e0030, added by add_base0_jobmods.py) start with a
position-independent crt0 at +0x30: it finds its load base ($126), clears the bss, runs the
constructor table and RETURNS the address of the job's main function in $3
(`ila $3, off; a $3, $3, $126`); the job manager then calls it. Nothing branches to that
function, so the first lift held the crt0 only. This reads `off` (and the constructor table)
out of the current lift / the module bytes, seeds them as function entries and relifts with the
same code-end fix-point as relift_jobmods.py, merged chunks.

Afterwards: scripts/extend_jobmods.py (register TU spans + code bytes), scripts/direct_bie.py,
port\\build.bat configure.
usage: relift_base0.py [--dry-run]
"""
import hashlib, json, os, re, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import relift_jobmods as R   # noqa: E402

L, SPU, MAN, ELF, BASE = R.L, R.SPU, R.MAN, R.ELF, R.BASE
MAIN = re.compile(r'ctx->gpr\[3\] = spu_ila\((0x[0-9A-F]+)\);\s*\n\s*ctx->gpr\[3\] = '
                  r'spu_a\(ctx->gpr\[3\], ctx->gpr\[126\]\);\s*\n\s*ctx->gpr\[1\] = spu_ai')
CTOR = re.compile(r'ctx->gpr\[80\] = spu_ila\((0x[0-9A-F]+)\);\s*\n\s*ctx->gpr\[80\] = '
                  r'spu_a\(ctx->gpr\[80\], ctx->gpr\[126\]\)')


def main():
    dry = '--dry-run' in sys.argv
    found = L.find_engine_modules(open(ELF, 'rb').read())
    by_name = {}
    for ea, raw in found:
        entry_off = struct.unpack_from(">I", raw, 0x10)[0]
        name = "jobmod_%s_e%04X" % (hashlib.sha1(raw).hexdigest()[:12], entry_off)
        by_name.setdefault(name, (raw, []))[1].append(ea)
    man = json.load(open(MAN))
    idx = {m['name']: i for i, m in enumerate(man)}
    tmp_elf = os.path.join(SPU, '_tmp_base0.elf')
    for name, (raw, eas) in sorted(by_name.items(), key=lambda kv: kv[1][1][0]):
        if struct.unpack_from(">I", raw, 0x28)[0] != 0 or name not in idx:
            continue
        src = open(os.path.join(SPU, name, 'spu_recomp.c'), encoding='latin-1').read()
        seeds = {BASE + int(x, 16) for x in MAIN.findall(src)}
        # constructor table: words below `end`, down to the 0xFFFFFFFF terminator (module offsets)
        for end in {int(x, 16) for x in CTOR.findall(src)}:
            p = end - 4
            while 0x30 <= p < len(raw):
                w = struct.unpack_from(">I", raw, p)[0]
                if w == 0xFFFFFFFF or not (0x30 <= w < len(raw)) or w & 3:
                    break
                seeds.add(BASE + w)
                p -= 4
        seeds = {s for s in seeds if BASE + 0x30 <= s < BASE + len(raw)}
        old = man[idx[name]]['code_end']
        print('%s: seeds %s (code_end now 0x%X, module end 0x%X)' % (
            name, ' '.join('0x%X' % s for s in sorted(seeds)) or '-', old, BASE + len(raw)))
        if not seeds or dry:
            continue
        L.EXTRA_FUNCS = [hex(s) for s in sorted(seeds)]
        ce = old
        for it in range(10):
            new = R.code_end_from(raw, name, R.lifted_entries(name) | seeds)
            new = max(new or ce, ce)
            if new == ce and it > 0:
                break
            ce = new
            m = L.lift_module(raw, name, SPU, tmp_elf, True, ce)
            if not m:
                sys.exit('lift failed: ' + name)
            m.update(ea=eas[0], eas=eas, code_end=ce)
            man[idx[name]] = m
        print('  -> code_end 0x%X, %d function(s)' % (ce, man[idx[name]]['funcs']))
        json.dump(man, open(MAN, 'w'), indent=2)
        L.EXTRA_FUNCS = []
    if os.path.exists(tmp_elf):
        os.remove(tmp_elf)


if __name__ == '__main__':
    main()
