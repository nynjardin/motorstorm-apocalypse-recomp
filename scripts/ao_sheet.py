"""ao_sheet.py <ao_cap dir> [out.png] [--width 640]
One contact sheet of the ambient occlusion chain captured by scripts/ao_cap.ps1 (system python:
PIL + numpy). Tiles, each a single channel shown as grey, with min/max/mean in the label:
  quarter G / A     rt_03150000_320x270 of the race capture (result of the SSAO pass + its blur)
  history G         rt_03630000 (what the next frame's SSAO pass blends with)
  half R / A        rt_03150000_640x540 of cap/stop_0034EE41 (upsample, edge mask)
  normals A         rt_01AB0000_a of cap/stop_0034FFC1 (the occlusion the scene pass reads)
  frame             race_backbuffer.png
Prints the statistics too: "max 0" on quarter G = the SSAO pass produced nothing.
"""
import glob
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

args = [a for a in sys.argv[1:] if not a.startswith('--')]
root = args[0]
out = args[1] if len(args) > 1 else os.path.join(root, 'ao_sheet.png')
W = int(sys.argv[sys.argv.index('--width') + 1]) if '--width' in sys.argv else 640


def last_frame(sub):
    d = sorted(glob.glob(os.path.join(root, 'cap', sub)))
    return d[-1] if d else None


def find(frame, pat):
    if not frame:
        return None
    g = sorted(glob.glob(os.path.join(frame, pat)))
    return g[0] if g else None


def chan(path, c):
    if not path:
        return None
    a = np.array(Image.open(path).convert('RGB'))
    return a[..., c]


race = last_frame('frame_*')
s_half = last_frame('stop_0034EE41')
s_full = last_frame('stop_0034FFC1')
tiles = [
    ('quarter G (SSAO, blurred)', chan(find(race, 'rt_03150000_320x270_f*[0-9].bmp'), 1)),
    ('quarter A', chan(find(race, 'rt_03150000_320x270_f*_a.bmp'), 0)),
    ('history G', chan(find(race, 'rt_03630000.bmp'), 1)),
    ('history B', chan(find(race, 'rt_03630000.bmp'), 2)),
    ('half R (upsampled)', chan(find(s_half, 'rt_03150000_640x540_f*[0-9].bmp'), 0)),
    ('half A (edges)', chan(find(s_half, 'rt_03150000_640x540_f*_a.bmp'), 0)),
    ('normals A (read by the scene)', chan(find(s_full, 'rt_01AB0000_a.bmp'), 0)),
]
imgs = []
for name, a in tiles:
    if a is None:
        print('%-32s missing' % name)
        continue
    print('%-32s %4dx%-4d min %3d max %3d mean %6.2f' % (name, a.shape[1], a.shape[0], a.min(), a.max(), a.mean()))
    im = Image.fromarray(a).convert('RGB')
    im = im.resize((W, int(W * 9 / 16)), Image.BILINEAR)
    ImageDraw.Draw(im).text((6, 4), '%s  [%d..%d] mean %.1f' % (name, a.min(), a.max(), a.mean()), fill=(255, 64, 64))
    imgs.append(im)
bb = os.path.join(root, 'race_backbuffer.png')
if os.path.exists(bb):
    imgs.append(Image.open(bb).convert('RGB').resize((W, int(W * 9 / 16)), Image.BILINEAR))
cols = 2
rows = (len(imgs) + cols - 1) // cols
th = int(W * 9 / 16)
sheet = Image.new('RGB', (cols * W, rows * th), (40, 0, 40))
for i, im in enumerate(imgs):
    sheet.paste(im, ((i % cols) * W, (i // cols) * th))
sheet.save(out)
print(out)
