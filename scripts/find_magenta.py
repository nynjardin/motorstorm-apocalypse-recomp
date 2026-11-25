# Screenshots that show fuchsia / magenta pixels (the "fuchsia lights that should be red" bug):
# counts the pixels with red and blue high and green low, and prints the bounding box of the
# biggest cluster, to know which picture to look at and where.
#   python scripts/find_magenta.py <png or directory> [...] [--min 12] [--crop <out dir>]
#   --min   fewest such pixels for a picture to be listed
#   --crop  save a 4x zoom of the area around the biggest cluster of each listed picture
# System python (PIL + numpy), not the venv.
import sys, os, glob
import numpy as np
from PIL import Image

paths = []; mn = 12; crop = None
a = sys.argv[1:]
while a:
    if a[0] == '--min': mn = int(a[1]); a = a[2:]
    elif a[0] == '--crop': crop = a[1]; a = a[2:]
    else: paths.append(a[0]); a = a[1:]
files = []
for p in paths:
    files += sorted(glob.glob(os.path.join(p, '*.png'))) if os.path.isdir(p) else [p]
for f in files:
    try: im = np.asarray(Image.open(f).convert('RGB')).astype(np.int32)
    except Exception as e: print('?', f, e); continue
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    m = (r > 170) & (b > 140) & (g < 0.55 * np.minimum(r, b)) & (np.abs(r - b) < 100)
    m[:40, :] = False                                   # window title bar
    n = int(m.sum())
    if n < mn: continue
    ys, xs = np.nonzero(m)
    # biggest cluster: the 48x48 cell with the most hits
    cy, cx = ys // 48, xs // 48
    cells, cnt = np.unique(cy * 1000 + cx, return_counts=True)
    k = cells[cnt.argmax()]; by, bx = (k // 1000) * 48, (k % 1000) * 48
    print('%6d magenta pixels, %3d in the cell at x=%d y=%d  %s' % (n, cnt.max(), bx, by, f))
    if crop:
        os.makedirs(crop, exist_ok=True)
        x0, y0 = max(0, bx - 100), max(0, by - 80)
        z = Image.open(f).convert('RGB').crop((x0, y0, x0 + 248, y0 + 208)).resize((992, 832), Image.NEAREST)
        z.save(os.path.join(crop, os.path.splitext(os.path.basename(f))[0] + '_magenta.png'))
