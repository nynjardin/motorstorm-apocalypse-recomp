# Flicker of a still scene from a series of screenshots (scripts/halo_series.ps1): mean luma of
# a grid of cells for each shot, then for each cell its spread over the series. Cells whose luma
# jumps from shot to shot are flickering; the table shows where on screen.
#   python scripts/halo_luma.py E:/ms_perf/halo_dbt_on [--cell 80] [--pair 5 6 out.png]
# --pair writes an amplified |difference| image of two shots.
import sys, glob, os
from PIL import Image, ImageChops
import numpy as np

d = sys.argv[1]
cell = 80
pair = None
a = sys.argv[2:]
while a:
    if a[0] == '--cell': cell = int(a[1]); a = a[2:]
    elif a[0] == '--pair': pair = (int(a[1]), int(a[2]), a[3]); a = a[4:]
    else: a = a[1:]
files = sorted(glob.glob(os.path.join(d, 's*.png')))
imgs = [np.asarray(Image.open(f).convert('L'), dtype=np.float32) for f in files]
h = min(i.shape[0] for i in imgs); w = min(i.shape[1] for i in imgs)
imgs = [i[:h, :w] for i in imgs]
gy, gx = h // cell, w // cell
series = np.array([[[im[y*cell:(y+1)*cell, x*cell:(x+1)*cell].mean() for x in range(gx)] for y in range(gy)] for im in imgs])
step = np.abs(np.diff(series, axis=0))
print('%d shots %dx%d, cell %d px' % (len(imgs), w, h, cell))
print('whole-image luma per shot:', ' '.join('%.1f' % im.mean() for im in imgs))
print('mean |step| per cell (luma units, 0-255):')
for y in range(gy):
    print(' '.join('%5.1f' % step[:, y, x].mean() for x in range(gx)))
print('max-min per cell:')
for y in range(gy):
    print(' '.join('%5.1f' % (series[:, y, x].max() - series[:, y, x].min()) for x in range(gx)))
if pair:
    i, j, out = pair
    df = np.clip(np.abs(imgs[i] - imgs[j]) * 6, 0, 255).astype(np.uint8)
    Image.fromarray(df).save(out)
    print('diff x6 of shots', i, j, '->', out)
