"""Which lifted WWS job module(s) contain a given SPU LS pc?

usage: jobmod_pc.py <pc> [<pc> ...]     (hex, e.g. 44D0 0x4DF8)

For each job id (port/spu/jobmods_register.c), prints the module, its code end
and the lifted function whose entry is the closest one <= pc (only if pc is
inside the module's code). All job modules load at LS 0x4000, so several can
match: the [pm-end] "recent" pcs narrow it down.
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SPU = os.path.join(HERE, '..', 'port', 'spu')


def load():
    man = json.load(open(os.path.join(SPU, 'jobmods_manifest.json')))
    by_ea = {}
    for m in man:
        for ea in m.get('eas', [m['ea']]):
            by_ea[ea] = m
    reg = open(os.path.join(SPU, 'jobmods_register.c'), encoding='latin-1').read()
    jobs = []
    for ea, jid in re.findall(r'verified_region\(0x([0-9A-F]+)u, 0x4000u, jm_span\([^)]*\), (\d+),', reg):
        m = by_ea.get(int(ea, 16))
        if not m:
            continue
        src = open(os.path.join(SPU, m['name'], 'spu_recomp.c'), encoding='latin-1').read()
        funcs = sorted(int(x, 16) for x in set(re.findall(
            r'^void ' + re.escape(m['prefix']) + r'spu_func_([0-9A-F]{8})\(spu_context', src, re.M)))
        jobs.append((int(jid), m, funcs))
    return jobs


def main():
    pcs = [int(a, 16) for a in sys.argv[1:]]
    jobs = load()
    for pc in pcs:
        print('pc 0x%05X:' % pc)
        for jid, m, funcs in jobs:
            end = m.get('code_end', m['base'] + m['size'])
            if not (m['base'] <= pc < end):
                continue
            f = max((x for x in funcs if x <= pc), default=None)
            exact = ' (entry)' if pc in funcs else ''
            print('  job %d %s code_end=0x%X func=0x%05X%s' % (jid, m['name'], end, f or 0, exact))


if __name__ == '__main__':
    main()
