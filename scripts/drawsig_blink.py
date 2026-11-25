# Objects the title stops submitting for a few frames, counted from a DRAW_SIG=<file> run
# (toolkit patch #47: 6 u32 a draw = colour target, fragment program, vertex array offset, first
# index offset, index/vertex count, texture 0 offset).
# A draw is identified by a key; a "blink" is a key whose number of draws in a frame falls below
# what it was during the --stable frames before, and is back within --back frames. A camera cut or
# an object leaving the view never comes back that fast, so only real blinks are counted.
#   python scripts/drawsig_blink.py <file> [--key geo|shape] [--back 4] [--stable 3] [--first 0]
#          [--n 100000] [--from-tick <ms>] [--rt <hex>] [--min-count 0] [--list] [--top 15]
#   --key geo   (default) target + program + vertex array + first index + count (a mesh in memory)
#   --key shape target + program + count + texture 0 (for meshes rebuilt at a new address each frame)
#   --from-tick only the frames from that GetTickCount value on (pack_sig.ps1: the race, not its presentation)
#   --rt        only the draws into that colour target (hex RSX offset)
#   --min-count only the draws of at least that many indices / vertices
# Output: blinks per 100 frames, how long they last, the keys that blink most.
import sys, struct, collections
import numpy as np

path = sys.argv[1]
key, back, stable, first, n, rt, minc, lst, top, tick0 = 'geo', 4, 3, 0, 100000, None, 0, False, 15, None
a = sys.argv[2:]
while a:
    if a[0] == '--key': key = a[1]; a = a[2:]
    elif a[0] == '--back': back = int(a[1]); a = a[2:]
    elif a[0] == '--stable': stable = int(a[1]); a = a[2:]
    elif a[0] == '--first': first = int(a[1]); a = a[2:]
    elif a[0] == '--n': n = int(a[1]); a = a[2:]
    elif a[0] == '--from-tick': tick0 = int(a[1]) & 0xFFFFFFFF; a = a[2:]
    elif a[0] == '--rt': rt = int(a[1], 16); a = a[2:]
    elif a[0] == '--min-count': minc = int(a[1]); a = a[2:]
    elif a[0] == '--top': top = int(a[1]); a = a[2:]
    elif a[0] == '--list': lst = True; a = a[1:]
    else: sys.exit('unknown option ' + a[0])
cols = {'geo': [0, 1, 2, 3, 4], 'shape': [0, 1, 4, 5]}[key]

data = open(path, 'rb').read()
frames = []          # (frame number, tick, {key bytes: draws})
pos = 0
while pos + 16 <= len(data):
    magic, fno, tick, nr = struct.unpack_from('<4I', data, pos)
    if magic != 0x47495344: sys.exit('bad block at %d' % pos)
    pos += 16
    if pos + 24 * nr > len(data): break          # truncated last block (game killed)
    rec = np.frombuffer(data, dtype='<u4', count=6 * nr, offset=pos).reshape(nr, 6)
    pos += 24 * nr
    if tick0 is not None and ((tick - tick0) & 0xFFFFFFFF) > 0x7FFFFFFF: continue
    if rt is not None: rec = rec[rec[:, 0] == rt]
    if minc: rec = rec[rec[:, 4] >= minc]
    k = np.ascontiguousarray(rec[:, cols])
    v = k.view(np.dtype((np.void, 4 * len(cols)))).ravel()
    u, c = np.unique(v, return_counts=True)
    frames.append((fno, tick, dict(zip((x.tobytes() for x in u), c.tolist())), len(rec)))
frames = frames[first:first + n]
if len(frames) < stable + back + 2: sys.exit('too few frames (%d)' % len(frames))

def show(kb):
    w = struct.unpack('<%dI' % len(cols), kb)
    if key == 'geo': return 'rt %08X fp %08X vtx %08X ix %08X n %6d' % w
    return 'rt %08X fp %08X n %6d tex0 %08X' % w
cnt_ix = cols.index(4)

events = []          # (frame index, frames missing, key, draws missing)
kept = total = 0
for i in range(stable, len(frames) - 1):
    cur = frames[i][2]; prev = frames[i - 1][2]
    total += len(prev)
    for kb, c0 in prev.items():
        c1 = cur.get(kb, 0)
        if c1 >= c0: kept += 1; continue
        if any(frames[i - s][2].get(kb, 0) < c0 for s in range(2, stable + 1)): continue
        for j in range(i + 1, min(i + 1 + back, len(frames))):
            if frames[j][2].get(kb, 0) >= c0:
                events.append((i, j - i, kb, c0 - c1))
                break
nf = len(frames)
secs = ((frames[-1][1] - frames[0][1]) & 0xFFFFFFFF) / 1000.0
print('%d frames over %.1f s (%.1f FPS), %d..%d draws, key=%s%s%s' % (nf, secs, (nf - 1) / secs if secs else 0,
      min(f[3] for f in frames), max(f[3] for f in frames), key,
      ' rt=%08X' % rt if rt is not None else '', ' min-count=%d' % minc if minc else ''))
print('keys kept from one frame to the next: %.1f %%' % (100.0 * kept / total if total else 0))
by_len = collections.Counter(e[1] for e in events)
fr_with = len(set(e[0] for e in events))
idx = sum(struct.unpack_from('<I', e[2], 4 * cnt_ix)[0] * e[3] for e in events)
print('blinks: %d (%.1f per 100 frames), in %d frames (%.1f %%), %.0f indices missing per 100 frames' %
      (len(events), 100.0 * len(events) / nf, fr_with, 100.0 * fr_with / nf, 100.0 * idx / nf))
print('  missing for ' + ', '.join('%d frame(s): %d' % (l, by_len[l]) for l in sorted(by_len)))
by_rt = collections.Counter(struct.unpack_from('<I', e[2], 0)[0] for e in events)
print('  by target: ' + ', '.join('%08X: %d' % (r, c) for r, c in by_rt.most_common(8)))
by_key = collections.Counter(e[2] for e in events)
for kb, c in by_key.most_common(top):
    print('  %4d x  %s' % (c, show(kb)))
if lst:
    by_fr = collections.defaultdict(list)
    for e in events: by_fr[e[0]].append(e)
    for i in sorted(by_fr):
        ev = by_fr[i]
        print('frame +%d (#%d, %.2f s): %d key(s), %d indices' % (i, frames[i][0], ((frames[i][1] - frames[0][1]) & 0xFFFFFFFF) / 1000.0,
              len(ev), sum(struct.unpack_from('<I', e[2], 4 * cnt_ix)[0] * e[3] for e in ev)))
        for e in ev[:12]: print('      %s  -%d for %d frame(s)' % (show(e[2]), e[3], e[1]))
