# What a STILL view draws, from DRAW_SIG recordings (toolkit patch #47), and how two runs of the
# same still view differ (idle_sig.ps1: the bike left on the starting grid, the pack gone).
#   python scripts/drawsig_static.py <a.bin> --from-tick <ms> [--frames 60]
#   python scripts/drawsig_static.py <a.bin> --from-tick <ms> --cmp <b.bin> --cmp-tick <ms> [--top 40]
# Per colour target: draws and indices of the median frame of the window, and how much they move
# inside the window (a still view should not move). With --cmp: the draws (target, index count,
# times drawn) that one run has and the other lacks, addresses left out (they change between runs).
import sys, struct, collections
import numpy as np

def load(path, tick0, nfr):
    data = open(path, 'rb').read(); pos = 0; fr = []
    while pos + 16 <= len(data) and len(fr) < nfr:
        magic, fno, tick, nr = struct.unpack_from('<4I', data, pos); pos += 16
        if magic != 0x47495344 or pos + 24 * nr > len(data): break
        if ((tick - tick0) & 0xFFFFFFFF) <= 0x7FFFFFFF:
            fr.append(np.frombuffer(data, dtype='<u4', count=6 * nr, offset=pos).reshape(nr, 6))
        pos += 24 * nr
    if not fr: sys.exit('%s: no frame after that tick' % path)
    return fr

def summary(name, fr):
    tot = sorted(range(len(fr)), key=lambda i: len(fr[i]))
    mid = fr[tot[len(tot) // 2]]
    print('%s: %d frames, draws a frame %d..%d (median %d)' % (name, len(fr), len(fr[tot[0]]), len(fr[tot[-1]]), len(mid)))
    rts = collections.Counter(mid[:, 0].tolist())
    for rt, c in sorted(rts.items(), key=lambda t: -t[1])[:10]:
        per = [int((f[:, 0] == rt).sum()) for f in fr]
        idx = int(mid[mid[:, 0] == rt][:, 4].sum())
        print('   rt %08X: %5d draws (%d..%d in the window), %8d indices' % (rt, c, min(per), max(per), idx))
    return mid

a = sys.argv[1]; ta = tb = None; b = None; nfr = 60; top = 40
x = sys.argv[2:]
while x:
    if x[0] == '--from-tick': ta = int(x[1]) & 0xFFFFFFFF; x = x[2:]
    elif x[0] == '--cmp': b = x[1]; x = x[2:]
    elif x[0] == '--cmp-tick': tb = int(x[1]) & 0xFFFFFFFF; x = x[2:]
    elif x[0] == '--frames': nfr = int(x[1]); x = x[2:]
    elif x[0] == '--top': top = int(x[1]); x = x[2:]
    else: sys.exit('unknown option ' + x[0])
ma = summary('A', load(a, ta, nfr))
if b:
    mb = summary('B', load(b, tb, nfr))
    ka = collections.Counter(map(tuple, ma[:, [0, 4]].tolist())); kb = collections.Counter(map(tuple, mb[:, [0, 4]].tolist()))
    da = ka - kb; db = kb - ka
    print('draws only in A: %d (%d indices); only in B: %d (%d indices)' % (sum(da.values()), sum(k[1] * c for k, c in da.items()),
          sum(db.values()), sum(k[1] * c for k, c in db.items())))
    for nm, dd in (('A', da), ('B', db)):
        by_rt = collections.Counter()
        for (rt, n), c in dd.items(): by_rt[rt] += c
        print('  only in %s by target: %s' % (nm, ', '.join('%08X: %d' % t for t in by_rt.most_common(8))))
        for (rt, n), c in sorted(dd.items(), key=lambda t: -t[0][1] * t[1])[:top]:
            print('      rt %08X n %6d x%d' % (rt, n, c))
