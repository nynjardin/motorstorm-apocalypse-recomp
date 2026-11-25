# Objects that blink, counted from a FRAME_LOG=1 run.log: a "hole" is a frame whose vertex total
# drops by more than --step below the frame before and is back within --back frames (to within a
# third of the drop); a "bump" is the same upwards. A scene that changes smoothly (camera moving,
# vehicles leaving) has none; an object the title submits one frame and not the next makes one.
# The draws lost/gained with it are printed, to tell an object (tens of draws) from noise.
#   python scripts/framelog_blink.py <run.log> [--step 6000] [--back 4] [--first 0] [--n 100000] [--list]
import sys, re

path = sys.argv[1]
step, back, first, n, lst = 6000, 4, 0, 100000, False
a = sys.argv[2:]
while a:
    if a[0] == '--step': step = int(a[1]); a = a[2:]
    elif a[0] == '--back': back = int(a[1]); a = a[2:]
    elif a[0] == '--first': first = int(a[1]); a = a[2:]
    elif a[0] == '--n': n = int(a[1]); a = a[2:]
    elif a[0] == '--list': lst = True; a = a[1:]
    else: sys.exit('unknown option ' + a[0])
rx = re.compile(rb'\[FRAME_LOG\] frame (\d+) t=(\d+) draws=(\d+) clears=\d+ verts=(\d+) scene=(\d+)x(\d+)')
fr = []
for line in open(path, 'rb'):
    m = rx.search(line)
    if m: fr.append(tuple(int(x) for x in m.groups()))
fr = fr[first:first + n]
if len(fr) < 10: sys.exit('fewer than 10 FRAME_LOG lines')
holes = bumps = 0; i = 1; events = []
while i < len(fr) - 1:
    d = fr[i][3] - fr[i - 1][3]
    if abs(d) > step:
        base = fr[i - 1][3]
        for j in range(i + 1, min(i + 1 + back, len(fr))):
            if abs(fr[j][3] - base) < abs(d) / 3:
                if d < 0: holes += 1
                else: bumps += 1
                events.append((i, j - i, d, fr[i][2] - fr[i - 1][2], fr[i][1] - fr[0][1]))
                i = j
                break
    i += 1
secs = (fr[-1][1] - fr[0][1]) / 1000.0
print('%d race frames over %.1f s (%.1f FPS), draws %d..%d' % (len(fr), secs, (len(fr) - 1) / secs if secs else 0,
      min(f[2] for f in fr), max(f[2] for f in fr)))
print('holes %d, bumps %d (step > %d vertices, back within %d frames) = %.1f per 100 frames' %
      (holes, bumps, step, back, 100.0 * (holes + bumps) / len(fr)))
if lst:
    for i, ln, d, dd, t in events:
        print('  frame +%d (%.1f s): %+d vertices, %+d draws, for %d frame(s)' % (i, t / 1000.0, d, dd, ln))
