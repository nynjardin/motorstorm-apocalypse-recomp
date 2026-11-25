"""Relift the WWS job modules with a code end that covers ALL their code.

ps3recomp's lift_jobmods.module_code_end() follows direct branches from the
seeded entries only. Code reached through an indirect branch (job 203: 0x50DC,
whose `brsl 0x55E8` calls the module's tail) is not followed, so the tail is
past --code-end: the lifter emits it as interpreter stubs and the verified
region does not cover it. The job then runs that tail in the interpreter in
the middle of lifted C frames and the PM run ends on a return address
([pm-end] pc == lr, depth 0), stranding the job list (race loading freeze).

Here every lifted non-stub function entry of the previous lift is a seed too;
lift -> collect entries -> recompute the end, until it is stable. The toolkit
is not modified. Outputs:
  port/spu/<module>/spu_recomp.{c,h}  (relifted)
  port/spu/jobmods_manifest.json      (code_end updated)
The registration TU is NOT regenerated (it carries port hand edits): run
scripts/extend_jobmods.py afterwards, which rewrites code_<id>[] and the spans
from the manifest.

usage: relift_jobmods.py [--only name_substr,...] [--dry-run] [--merge | --no-merge]
(after --merge / --no-merge: scripts/direct_bie.py, then port\build.bat)
"""
import hashlib, json, os, re, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..'))
SPU = os.path.join(ROOT, 'port', 'spu')
MAN = os.path.join(SPU, 'jobmods_manifest.json')
ELF = os.path.join(ROOT, 'game', 'BCES00484', 'EBOOT.elf')
TOOLS = os.path.normpath(os.path.join(ROOT, '..', 'ps3recomp', 'tools'))
sys.path.insert(0, TOOLS)
os.chdir(TOOLS)   # toolkit tools import siblings
import lift_jobmods as L  # noqa: E402

BASE = L.BASE
STUB = re.compile(r'^void (\w+?)spu_func_([0-9A-F]{8})\(spu_context\* ctx\) \{\s*\n'
                  r'\s*ctx->pc = 0x[0-9A-F]+u; g_spu_trampoline_fn = spu_indirect_branch; return;\s*\n\}',
                  re.M)
FUNC = re.compile(r'^void (\w+?)spu_func_([0-9A-F]{8})\(spu_context\* ctx\) \{', re.M)


def lifted_entries(name):
    """Non-stub function entries of the current lift of `name` (empty if none)."""
    p = os.path.join(SPU, name, 'spu_recomp.c')
    if not os.path.exists(p):
        return set()
    src = open(p, encoding='latin-1').read()
    allf = {int(a, 16) for _, a in FUNC.findall(src)}
    stubs = {int(a, 16) for _, a in STUB.findall(src)}
    return allf - stubs


def code_end_from(raw, name, extra):
    """module_code_end() with `extra` entries as additional seeds."""
    hi = min(BASE + len(raw), L.CODE_END.get(name, BASE + len(raw)))
    seeds = {BASE + struct.unpack_from(">I", raw, 0x10)[0], BASE + 0x30}
    seeds |= {int(a, 0) for a in L.EXTRA_FUNCS}
    seeds |= {e for e in extra if BASE + 0x30 <= e < hi}
    derived = L.manual_link_sites(raw, BASE) + L.switch_table_sites(raw, BASE)
    while True:
        seen = L.reachable(raw, seeds, hi, BASE)
        new = {t for site, t in derived if site in seen} - seeds
        if not new:
            break
        seeds |= new
    return max(seen) + 4 if seen else None


def main():
    dry = '--dry-run' in sys.argv
    # --merge / --no-merge: relift every module at the manifest's code end with (without) the
    # lifter's --merge-chunks (contiguous chunks of one function = one C function with gotos).
    # Without either flag: the code-end fix-point below, lifted without merging.
    merge = '--merge' in sys.argv
    remerge = merge or '--no-merge' in sys.argv
    only = []
    if '--only' in sys.argv:
        only = sys.argv[sys.argv.index('--only') + 1].split(',')
    found = L.find_engine_modules(open(ELF, 'rb').read())
    by_name = {}
    for ea, raw in found:
        entry_off = struct.unpack_from(">I", raw, 0x10)[0]
        name = f"jobmod_{hashlib.sha1(raw).hexdigest()[:12]}_e{entry_off:04X}"
        by_name.setdefault(name, (raw, []))[1].append(ea)
    man = json.load(open(MAN))
    idx = {m['name']: i for i, m in enumerate(man)}
    tmp_elf = os.path.join(SPU, '_tmp_relift.elf')
    for name, (raw, eas) in sorted(by_name.items(), key=lambda kv: kv[1][1][0]):
        if only and not any(o in name for o in only):
            continue
        if name not in idx:
            print('  SKIP %s: not in manifest' % name)
            continue
        old = man[idx[name]]['code_end']
        if remerge:
            # same code end, only the shape of the C changes (see --merge / --no-merge)
            print('%s: relift at code_end 0x%X, merge_chunks=%s' % (name, old, merge))
            if not dry:
                m = L.lift_module(raw, name, SPU, tmp_elf, merge, old)
                if not m:
                    sys.exit('lift failed: ' + name)
                m.update(ea=eas[0], eas=eas, code_end=old)
                man[idx[name]] = m
                json.dump(man, open(MAN, 'w'), indent=2)
            continue
        if old >= BASE + len(raw):
            print('%s: code_end 0x%X = module end, unchanged' % (name, old))
            continue
        ce = old
        for it in range(8):
            new = code_end_from(raw, name, lifted_entries(name))
            new = max(new or ce, ce)
            if new == ce and it > 0:
                break
            ce = new
            print('%s: code_end 0x%X -> 0x%X (pass %d)' % (name, old, ce, it + 1))
            if dry:
                break
            m = L.lift_module(raw, name, SPU, tmp_elf, False, ce)
            if not m:
                sys.exit('lift failed: ' + name)
            m.update(ea=eas[0], eas=eas, code_end=ce)
            man[idx[name]] = m
        if not dry:
            json.dump(man, open(MAN, 'w'), indent=2)
    if os.path.exists(tmp_elf):
        os.remove(tmp_elf)


if __name__ == '__main__':
    main()
