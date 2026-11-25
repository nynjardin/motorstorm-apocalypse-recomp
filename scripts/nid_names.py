"""Names of the functions a title imports, per library, from their NIDs.

    python scripts/nid_names.py [--lib sceNp,sys_net,...] [--imports <EBOOT.imports.json>] [--all]

A PS3 import NID is the first four bytes (little-endian) of SHA1(name + a fixed 16-byte suffix).
The candidate names are every identifier-like ASCII string of tools/rpcs3/rpcs3.exe (RPCS3 names
each function it knows), hashed once and cached in the scratch file given by --cache (default
E:/ms_perf/nid_cache.json). Default libraries: the network ones (sceNp*, sys_net, cellHttp,
cellSsl, cellNetCtl, cellVoice, cellSysutilNpEula, cellRudp). Unresolved NIDs are printed as hex.
"""
import argparse, hashlib, json, os, re, struct

HERE = os.path.dirname(os.path.abspath(__file__))
RPCS3 = os.path.normpath(os.path.join(HERE, '..', '..', 'tools', 'rpcs3', 'rpcs3.exe'))
SUFFIX = bytes.fromhex('6759659904250490566427499489741A')
NET = ('sceNp', 'sys_net', 'cellHttp', 'cellSsl', 'cellNetCtl', 'cellVoice', 'cellSysutilNpEula', 'cellRudp',
       'sceNp2', 'sceNpTrophy', 'cellSysutilAvc')


def nid(name):
    return struct.unpack('<I', hashlib.sha1(name.encode() + SUFFIX).digest()[:4])[0]


def table(cache):
    if os.path.exists(cache):
        return {int(k): v for k, v in json.load(open(cache)).items()}
    data = open(RPCS3, 'rb').read()
    out = {}
    for m in re.finditer(rb'[A-Za-z_][A-Za-z0-9_]{2,63}', data):
        s = m.group().decode()
        out.setdefault(nid(s), s)
    try:
        json.dump(out, open(cache, 'w'))
    except OSError:
        pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--imports', default=os.path.join(HERE, '..', 'work', 'BCES00484', 'ppu', 'EBOOT.imports.json'))
    ap.add_argument('--lib', default='')
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--cache', default='E:/ms_perf/nid_cache.json')
    a = ap.parse_args()
    t = table(a.cache)
    libs = {}
    for f in json.load(open(a.imports)):
        libs.setdefault(f['library'], []).append(int(f['nid'], 16))
    want = [x for x in a.lib.split(',') if x]
    for lib in sorted(libs):
        if not a.all and not (lib in want if want else lib.startswith(NET)):
            continue
        names = sorted(t.get(n, '0x%08X' % n) for n in libs[lib])
        miss = sum(1 for n in libs[lib] if n not in t)
        print(f'== {lib} ({len(names)}{", %d unresolved" % miss if miss else ""})')
        for n in names:
            print('   ' + n)


if __name__ == '__main__':
    main()
