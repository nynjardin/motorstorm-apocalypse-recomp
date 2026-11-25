# Read a PSARC archive (ms3.psarc of MotorStorm Apocalypse) in place, without extracting it.
#   python scripts/psarc.py <archive> exts                     file count and size by extension
#   python scripts/psarc.py <archive> list [name-regex]        names (with sizes)
#   python scripts/psarc.py <archive> cat <name>               one file to stdout (binary)
#   python scripts/psarc.py <archive> extract <name-regex> <out-dir>   files to a directory (keeps paths)
#   python scripts/psarc.py <archive> grep <bytes-regex> [name-regex]  files whose content matches
# Names are matched case-insensitively. Extract only small things, and never onto I: (small disk).
import sys, os, re, struct, zlib

class Psarc:
    def __init__(self, path):
        self.f = open(path, 'rb')
        h = self.f.read(32)
        magic, ver, comp, toc_len, esz, n, self.bs, flags = struct.unpack('>4sI4sIIIII', h)
        if magic != b'PSAR': sys.exit('not a PSARC')
        if comp != b'zlib': sys.exit('compression %r not handled' % comp)
        toc = self.f.read(toc_len - 32)
        self.ent = []
        for i in range(n):
            e = toc[i * esz:(i + 1) * esz]
            blk, = struct.unpack_from('>I', e, 16)
            size = int.from_bytes(e[20:25], 'big'); off = int.from_bytes(e[25:30], 'big')
            self.ent.append((blk, size, off))
        w = 2 if self.bs <= 0x10000 else 3 if self.bs <= 0x1000000 else 4
        tab = toc[n * esz:]
        self.bsz = [int.from_bytes(tab[i:i + w], 'big') for i in range(0, len(tab) - w + 1, w)]
        self.names = ['<manifest>'] + self.read(0).decode('latin-1').split('\n')
    def read(self, i):
        blk, size, off = self.ent[i]
        self.f.seek(off); out = bytearray()
        while len(out) < size:
            z = self.bsz[blk]; blk += 1
            if z == 0: out += self.f.read(self.bs); continue
            b = self.f.read(z)
            if z == size - len(out): out += b; continue          # stored
            try: out += zlib.decompress(b)
            except zlib.error: out += b
        return bytes(out[:size])

a = Psarc(sys.argv[1]); cmd = sys.argv[2]
if cmd == 'exts':
    st = {}
    for i, nm in enumerate(a.names[1:], 1):
        if i >= len(a.ent): break
        x = os.path.splitext(nm)[1].lower()
        c, s = st.get(x, (0, 0)); st[x] = (c + 1, s + a.ent[i][1])
    for x, (c, s) in sorted(st.items(), key=lambda t: -t[1][1]): print('%-12s %6d files %10.1f MB' % (x, c, s / 1048576.0))
elif cmd == 'list':
    rx = re.compile(sys.argv[3], re.I) if len(sys.argv) > 3 else None
    for i, nm in enumerate(a.names[1:], 1):
        if i < len(a.ent) and (not rx or rx.search(nm)): print('%10d %s' % (a.ent[i][1], nm))
elif cmd == 'cat':
    want = sys.argv[3].lower()
    for i, nm in enumerate(a.names):
        if nm.lower() == want: sys.stdout.buffer.write(a.read(i)); break
    else: sys.exit('not found')
elif cmd == 'extract':
    rx = re.compile(sys.argv[3], re.I); out = sys.argv[4]
    for i, nm in enumerate(a.names[1:], 1):
        if i < len(a.ent) and rx.search(nm):
            p = os.path.join(out, nm.lstrip('/').replace('/', os.sep)); os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, 'wb').write(a.read(i)); print(p)
elif cmd == 'grep':
    rx = re.compile(sys.argv[3].encode('latin-1'), re.I)
    nrx = re.compile(sys.argv[4], re.I) if len(sys.argv) > 4 else None
    for i, nm in enumerate(a.names[1:], 1):
        if i >= len(a.ent) or (nrx and not nrx.search(nm)): continue
        m = rx.search(a.read(i))
        if m: print('%10d %s  @%d' % (a.ent[i][1], nm, m.start())); sys.stdout.flush()
else: sys.exit('unknown command')
