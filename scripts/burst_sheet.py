# Contact sheets of a window burst (grab_burst.py / pack_burst.ps1): consecutive frames side by
# side, each labelled with its index, to spot an object that is there in one frame and gone in
# the next. Optional crop (x0 y0 x1 y1 in window pixels) and zoom, for a small distant object.
#   python scripts/burst_sheet.py <burst_dir> [--first 0] [--n 30] [--cols 6] [--scale 0.25]
#                                 [--crop x0 y0 x1 y1] [--out sheet.png]
# System python (PIL), not the venv.
import sys, os, glob
from PIL import Image, ImageDraw

d = sys.argv[1]
first, n, cols, scale, crop, out = 0, 30, 6, 0.25, None, None
a = sys.argv[2:]
while a:
    if a[0] == '--first': first = int(a[1]); a = a[2:]
    elif a[0] == '--n': n = int(a[1]); a = a[2:]
    elif a[0] == '--cols': cols = int(a[1]); a = a[2:]
    elif a[0] == '--scale': scale = float(a[1]); a = a[2:]
    elif a[0] == '--out': out = a[1]; a = a[2:]
    elif a[0] == '--crop': crop = tuple(int(v) for v in a[1:5]); a = a[5:]
    else: sys.exit('unknown option ' + a[0])
files = sorted(glob.glob(os.path.join(d, 'b*.png')))[first:first + n]
if not files: sys.exit('no frames')
tiles = []
for f in files:
    im = Image.open(f).convert('RGB')
    if crop: im = im.crop(crop)
    im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.LANCZOS)
    ImageDraw.Draw(im).text((3, 2), os.path.basename(f)[1:4], fill=(255, 255, 0))
    tiles.append(im)
w, h = tiles[0].size
rows = (len(tiles) + cols - 1) // cols
sheet = Image.new('RGB', (cols * w, rows * h))
for i, t in enumerate(tiles): sheet.paste(t, ((i % cols) * w, (i // cols) * h))
out = out or os.path.join(d, 'sheet_%03d.png' % first)
sheet.save(out)
print(out, sheet.size)
