# pair_sheet.py <lan_test output dir> [--match <regex>] [--width 480] [--rows 6] [--out <prefix>]
# Contact sheets of the captures made by screenshot_pair.ps1 / lan_test.ps1 -Start: one row per
# instant, every instance side by side (s<t>_h.png, s<t>_j.png, s<t>_p3.png...), each scaled to
# --width, the instant written on the left. --rows rows per sheet: <prefix>_1.png, _2.png...
# (default prefix: <dir>/sheet). To see a whole race of two or more instances in a few images
# instead of opening every capture (pair_montage.ps1 crops one HUD region instead). System python (PIL).
import argparse, glob, os, re, sys
from PIL import Image, ImageDraw

ap = argparse.ArgumentParser()
ap.add_argument('dir')
ap.add_argument('--match', default='')
ap.add_argument('--width', type=int, default=480)
ap.add_argument('--rows', type=int, default=6)
ap.add_argument('--out', default='')
a = ap.parse_args()

groups = {}
for f in sorted(glob.glob(os.path.join(a.dir, 's*_*.png'))):
    m = re.match(r'(s\d+)_(\w+)\.png$', os.path.basename(f))
    if not m or (a.match and not re.search(a.match, m.group(1))):
        continue
    groups.setdefault(m.group(1), {})[m.group(2)] = f
if not groups:
    sys.exit('no capture in ' + a.dir)
order = lambda tag: (0 if tag == 'h' else 1, tag)
tags = sorted({t for g in groups.values() for t in g}, key=order)
prefix = a.out or os.path.join(a.dir, 'sheet')
keys = sorted(groups)
for n in range(0, len(keys), a.rows):
    part = keys[n:n + a.rows]
    cells = []
    for k in part:
        row = []
        for t in tags:
            f = groups[k].get(t)
            if f:
                im = Image.open(f).convert('RGB')
                im = im.resize((a.width, im.height * a.width // im.width), Image.BILINEAR)
            else:
                im = None
            row.append(im)
        cells.append(row)
    h = max(im.height for row in cells for im in row if im)
    sheet = Image.new('RGB', (a.width * len(tags), h * len(part)))
    d = ImageDraw.Draw(sheet)
    for y, (k, row) in enumerate(zip(part, cells)):
        for x, im in enumerate(row):
            if im:
                sheet.paste(im, (x * a.width, y * h))
        d.rectangle((0, y * h, 46, y * h + 13), fill=(0, 0, 0))
        d.text((2, y * h + 1), k, fill=(255, 255, 0))
    out = '%s_%d.png' % (prefix, n // a.rows + 1)
    sheet.save(out)
    print('saved', out, '(%s)' % ' '.join(part))
