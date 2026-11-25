"""Which lifted functions reference a string of the EBOOT?

    python scripts/strref.py "Lan::WorldCreate" "NetInitialize() failed" ...
    python scripts/strref.py --callers func_003EC4E0 func_0038A8D0     # direct call sites of functions

For each argument: every string of the ELF that CONTAINS it (guest address shown), then the lifted
functions that build that address with `lis` + `addi` (the title does not go through the TOC for
strings), and the pointers to it stored in the image (tables of names). One pass over the 66
lifted sources (~20 s). --callers lists `func_X(ctx)` call sites by enclosing function; a function
with no direct caller is reached through a pointer (virtual method, callback).
"""
import glob, os, re, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ELF = os.path.normpath(os.path.join(HERE, '..', 'game', 'BCES00484', 'EBOOT.elf'))
RECOMP = os.path.normpath(os.path.join(HERE, '..', 'work', 'BCES00484', 'recomp'))
HI = re.compile(r'ctx->gpr\[(\d+)\] = \(int64_t\)\(int32_t\)\(\(uint32_t\)0x([0-9A-F]+) << 16\);')


def sources():
    for path in sorted(glob.glob(os.path.join(RECOMP, 'ppu_recomp_[0-9]*.cpp'))):
        yield os.path.basename(path), open(path, encoding='latin-1').read().split('\n')


def callers(names):
    pats = {n: n + '(ctx)' for n in names}
    for fname, lines in sources():
        cur = None
        for i, l in enumerate(lines):
            if l.startswith('void func_'):
                cur = l[5:18]
                continue
            for n, p in pats.items():
                if p in l:
                    m = re.search(r'ctx->lr = (0x[0-9A-F]+);', l)
                    print(f'{n} called from {cur} ({m.group(1) if m else "tail"})  {fname}:{i + 1}')


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    if args[0] == '--callers':
        return callers(args[1:])
    d = open(ELF, 'rb').read()
    phoff = struct.unpack('>Q', d[0x20:0x28])[0]
    phentsize, phnum = struct.unpack('>HH', d[0x36:0x3A])
    segs = []
    for i in range(phnum):
        t, fl, off, va, pa, fsz, msz, al = struct.unpack('>IIQQQQQQ', d[phoff + i * phentsize: phoff + i * phentsize + 56])
        if t == 1 and fsz:
            segs.append((va, off, fsz))

    def va_of(fo):
        for v, o, s in segs:
            if o <= fo < o + s:
                return v + fo - o
        return None

    targets = {}
    for a in args:
        b = a.encode('latin-1')
        fo = d.find(b)
        while fo >= 0:
            start = fo
            while start > 0 and 32 <= d[start - 1] < 127:
                start -= 1
            end = d.find(b'\0', fo)
            va = va_of(start)
            if va is not None and va not in targets:
                targets[va] = d[start:end].decode('latin-1')
                # a reference may also point inside the string (shared tails): keep the hit itself too
                if start != fo and va_of(fo) not in targets:
                    targets[va_of(fo)] = d[fo:end].decode('latin-1')
            fo = d.find(b, fo + 1)
    if not targets:
        sys.exit('no such string')
    for va in sorted(targets):
        print('%08X  "%s"' % (va, targets[va][:110]))
        pat = struct.pack('>I', va)
        i = d.find(pat)
        while i >= 0:
            pv = va_of(i)
            if pv is not None and pv % 4 == 0:
                print('          pointer stored at %08X' % pv)
            i = d.find(pat, i + 1)
    his = {}
    for va in targets:
        lo, hi = va & 0xFFFF, va >> 16
        if lo >= 0x8000:
            hi += 1
            lo -= 0x10000
        his.setdefault(hi, {})[lo] = va
    for fname, lines in sources():
        cur = None
        for i, l in enumerate(lines):
            if l.startswith('void func_'):
                cur = l[5:18]
                continue
            if '<< 16);' not in l:
                continue
            m = HI.search(l)
            if not m or int(m.group(2), 16) not in his:
                continue
            reg, tab = m.group(1), his[int(m.group(2), 16)]
            for j in range(i + 1, min(i + 8, len(lines))):
                s = lines[j]
                mm = (re.search(r'ctx->gpr\[%s\] \+ \(int64_t\)\((-?(?:0x)?[0-9A-Fa-f]+)\)' % reg, s) or
                      re.search(r'_a = ctx->gpr\[%s\]; uint64_t _r = _a \+ \(uint64_t\)\(int64_t\)\((-?(?:0x)?[0-9A-Fa-f]+)\)' % reg, s))
                if mm:
                    v = int(mm.group(1), 0)
                    if v in tab:
                        print('REF  %s  %s:%d  "%s"' % (cur, fname, j + 1, targets[tab[v]][:70]))
                    break


if __name__ == '__main__':
    main()
