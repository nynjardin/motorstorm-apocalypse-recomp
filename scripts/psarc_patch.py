"""Build port/psarc_patches.bin: replacement files for ms3.psarc, applied by the port at read time.

    python scripts/psarc_patch.py [--overlay port/psarc_overlay] [--out port/psarc_patches.bin] [--check]
    python scripts/psarc_patch.py --v106 [--check]       (1.06 build: ms3.psarc + ms3patchv0101..0106.psarc)

Two sources of replacements:
  - port/psarc_edits.json (the one in use, holds no game data): a list of
    {"file": "/ui/fe/multiplayer.xml", "replace": [["old text", "new text"], ...]}; each old text
    must occur exactly once in the original entry, read from the archive; "strip_comments": true
    first removes the XML comments (the room the edits need);
  - every file under the overlay directory replaces the archive entry of the same path
    (port/psarc_overlay/ui/fe/multiplayer.xml -> /ui/fe/multiplayer.xml); for experiments, never
    to be committed (it is the title's own file).
The archive on disc is never
written: the output is a list of (file offset, bytes) that port/psarc_patch.cpp copies over the
bytes the title reads (toolkit read hook, local patch #60). For each replacement:
  - the new content is cut in blocks of the archive's block size and each block zlib-compressed;
  - it must fit where the original was: no more blocks than the original entry, and no more
    compressed bytes in total (the next entry starts right behind). Trim the file (comments,
    indentation) if it does not;
  - three ranges are patched: the compressed data at the entry's offset, the entry's
    uncompressed size in the table of contents, and its block sizes in the block table.
--check re-reads the patched bytes through a simulated read and compares with the replacement.
Run it again after changing a file of the overlay; no rebuild needed (run.bat points the port at
the patch list when it exists). Format: "PSPATCH1", u32 count, then (u64 offset, u32 length,
bytes) per range, little-endian.
"""
import argparse, json, os, re, struct, sys, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = os.path.normpath(os.path.join(HERE, '..', 'port'))
ARCHIVE = ('F:/Jeux/PS3/MotorStorm - Apocalypse (Europe) (En,Fr,De,Es,It,Nl,Pt,Sv,No,Da,Fi,Ko,Pl,Ru) (v02.00)'
           '/PS3_GAME/USRDIR/ms3.psarc')


class Psarc:
    def __init__(self, path):
        self.f = open(path, 'rb')
        h = self.f.read(32)
        magic, ver, comp, self.toc_len, self.esz, self.n, self.bs, flags = struct.unpack('>4sI4sIIIII', h)
        if magic != b'PSAR' or comp != b'zlib':
            sys.exit('not a zlib PSARC')
        toc = self.f.read(self.toc_len - 32)
        self.ent = []
        for i in range(self.n):
            e = toc[i * self.esz:(i + 1) * self.esz]
            blk, = struct.unpack_from('>I', e, 16)
            self.ent.append((blk, int.from_bytes(e[20:25], 'big'), int.from_bytes(e[25:30], 'big')))
        self.w = 2 if self.bs <= 0x10000 else 3 if self.bs <= 0x1000000 else 4
        tab = toc[self.n * self.esz:]
        self.bsz = [int.from_bytes(tab[i:i + self.w], 'big') for i in range(0, len(tab) - self.w + 1, self.w)]
        self.names = ['<manifest>'] + self.read(0).decode('latin-1').split('\n')

    def nblocks(self, size):
        return (size + self.bs - 1) // self.bs

    def stored_len(self, i):
        blk, size, off = self.ent[i]
        return sum(self.bsz[b] or self.bs for b in range(blk, blk + self.nblocks(size)))

    def read(self, i, patched=None):
        blk, size, off = self.ent[i] if patched is None else patched['ent']
        bsz = self.bsz if patched is None else patched['bsz']
        pos, out = off, bytearray()
        while len(out) < size:
            z = bsz[blk]
            blk += 1
            n = z or self.bs
            self.f.seek(pos)
            b = bytearray(self.f.read(n))
            if patched is not None:
                for po, pb in patched['ranges']:
                    lo, hi = max(po, pos), min(po + len(pb), pos + n)
                    if lo < hi:
                        b[lo - pos:hi - pos] = pb[lo - po:hi - po]
            pos += n
            if z == 0 or z == size - len(out):
                out += b
                continue
            out += zlib.decompress(bytes(b))
        return bytes(out[:size])


def best_deflate(raw):
    # the archive's own packer does a little better than zlib.compress(raw, 9): try the other
    # memory levels and strategies and keep the smallest stream
    best = None
    for mem in (9, 8):
        for strat in (zlib.Z_DEFAULT_STRATEGY, zlib.Z_FILTERED):
            c = zlib.compressobj(9, zlib.DEFLATED, 15, mem, strat)
            z = c.compress(raw) + c.flush()
            if best is None or len(z) < len(best):
                best = z
    return best


HDD_USRDIR = 'F:/Jeux/PS3/_recomp/BCES00484/dev_hdd0/game/BCES00484/USRDIR/'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--overlay', default=os.path.join(PORT, 'psarc_overlay'))
    ap.add_argument('--edits', default=os.path.join(PORT, 'psarc_edits.json'))
    ap.add_argument('--out', default=os.path.join(PORT, 'psarc_patches.bin'))
    ap.add_argument('--archive', default=ARCHIVE)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--v106', action='store_true',
                    help='1.06 build: the title mounts ms3.psarc and ms3patchv0101..0106.psarc (the HDD copies in '
                         + HDD_USRDIR + '); an edited file is patched in the LAST archive that holds it; '
                         'writes port/psarc_patches_106.bin (PSPATCH2: one patch list per archive)')
    a = ap.parse_args()
    archives = [('ms3.psarc', Psarc(a.archive))]
    if a.v106:
        for k in range(1, 7):
            archives.append(('ms3patchv%04d.psarc' % (100 + k), Psarc(HDD_USRDIR + 'ms3patchv%04d.psarc' % (100 + k))))
        if a.out == os.path.join(PORT, 'psarc_patches.bin'):
            a.out = os.path.join(PORT, 'psarc_patches_106.bin')
    indexes = [{nm.lower(): i for i, nm in enumerate(ar.names)} for _, ar in archives]

    def winner(name):
        """(archive name, Psarc, entry index) of the last archive holding `name`, or None."""
        for (an, ar), ix in reversed(list(zip(archives, indexes))):
            if name.lower() in ix:
                return an, ar, ix[name.lower()]
        return None
    per_arc = {an: [] for an, _ in archives}
    failed = False
    todo = []                                   # (archive name, new content)
    for root, dirs, files in os.walk(a.overlay):
        for fn in sorted(files):
            full = os.path.join(root, fn)
            todo.append(('/' + os.path.relpath(full, a.overlay).replace(os.sep, '/'), open(full, 'rb').read()))
    if os.path.exists(a.edits):
        for item in json.load(open(a.edits, encoding='utf-8')):
            w = winner(item['file'])
            if w is None:
                todo.append((item['file'], None))
                continue
            data = w[1].read(w[2])
            if item.get('strip_comments'):      # room for the edits: XML comments carry nothing
                data = re.sub(rb'<!--.*?-->', b'', data, flags=re.S)
            for old, new in item['replace']:
                o, n = old.encode('utf-8'), new.encode('utf-8')
                if data.count(o) != 1:
                    sys.exit(f"{item['file']}: {data.count(o)} occurrences of {old!r} (1 wanted)")
                data = data.replace(o, n)
            todo.append((item['file'], data))
    for name, new in todo:
        if True:
            w = winner(name)
            if w is None or new is None:
                print(f'{name}: NOT IN THE ARCHIVE')
                failed = True
                continue
            an, arc, i = w
            print(f'[{an}]', end=' ')
            blk, size, off = arc.ent[i]
            old_nb, room = arc.nblocks(size), arc.stored_len(i)
            nb = arc.nblocks(len(new))
            blocks, zs = [], []
            for k in range(nb):
                raw = new[k * arc.bs:(k + 1) * arc.bs]
                z = best_deflate(raw)
                left = len(new) - k * arc.bs
                if len(z) >= len(raw) or len(z) == left:      # store it (a size equal to what is left reads as "stored")
                    if len(raw) != arc.bs and len(raw) != left:
                        sys.exit(f'{name}: block {k} cannot be stored')
                    blocks.append(raw)
                    zs.append(0 if len(raw) == arc.bs else len(raw))
                else:
                    blocks.append(z)
                    zs.append(len(z))
            data = b''.join(blocks)
            print(f'{name}: {size} -> {len(new)} bytes, {old_nb} -> {nb} blocks, stored {room} -> {len(data)} bytes')
            if nb > old_nb or len(data) > room:
                print('   DOES NOT FIT: trim the replacement (comments, indentation)')
                failed = True
                continue
            mine = [(off, data),
                    (32 + i * arc.esz + 20, len(new).to_bytes(5, 'big')),
                    (32 + arc.n * arc.esz + blk * arc.w, b''.join(z.to_bytes(arc.w, 'big') for z in zs))]
            if a.check:
                bsz = list(arc.bsz)
                bsz[blk:blk + nb] = zs
                got = arc.read(i, {'ent': (blk, len(new), off), 'bsz': bsz, 'ranges': mine})
                print('   check:', 'OK' if got == new else 'MISMATCH')
                failed |= got != new
            per_arc[an] += mine
    if failed:
        sys.exit('nothing written')
    with open(a.out, 'wb') as f:
        if not a.v106:
            ranges = per_arc['ms3.psarc']
            f.write(b'PSPATCH1' + struct.pack('<I', len(ranges)))
            for off, b in ranges:
                f.write(struct.pack('<QI', off, len(b)) + b)
        else:
            used = [(an, rg) for an, rg in per_arc.items() if rg]
            f.write(b'PSPATCH2' + struct.pack('<I', len(used)))
            for an, rg in used:
                nb = an.encode()
                f.write(struct.pack('<B', len(nb)) + nb + struct.pack('<I', len(rg)))
                for off, b in rg:
                    f.write(struct.pack('<QI', off, len(b)) + b)
    print(f'{a.out}: ' + ', '.join(f'{an}: {len(rg)} ranges' for an, rg in per_arc.items() if rg))


if __name__ == '__main__':
    main()
