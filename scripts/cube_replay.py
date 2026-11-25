"""cube_replay.py <dir of a pause_start run with VTX_FP_DUMP=301 during the photo mode>
The vehicles' contact-shadow cube (fragment program 0x301, dark squares, 2026-11-25) replayed
on the CPU from a capture: per pixel, the depth the program reads (target 00AC0000 read as
A8R8G8B8: z24 = A:R:G, z_ndc = z24 / 2^23 - 1) and the cube's vertex constants give the
position in the cube's space, as the program computes it:
    P = c264 * x_ndc + c265 * y_ndc + c266 * z_ndc + c267,   box = P.xyz / P.w   (inside: |box| <= 1)
(vertex program: tc1 = w * (c264 x + c265 y + c267), tc2 = c266; fragment program:
r1 = z * tc2 + tc1 / w). Writes <dir>/cube_replay.png: the alpha change seen between the
captures gate_00 and gate_01, and in colour the pixels each cube's box should cover.
System python (PIL, numpy).
"""
import os, re, sys
import numpy as np
from PIL import Image

d = sys.argv[1]
cap0 = os.path.join(d, 'cap', 'gate_00')
cap1 = os.path.join(d, 'cap', 'gate_01')
W, H = 1272, 1064

# The cube draws of the first dumped frame: their constants.
cubes, cur = [], None
for l in open(os.path.join(d, 'run.log'), encoding='latin-1'):
    if '[VTXDUMP] fp=0x' in l:
        cur = {} if 'fp=0x00000301' in l and 'indexed' in l else None
        if cur is not None:
            cur['frame'] = int(re.search(r'frame (\d+)', l).group(1)); cubes.append(cur)
        continue
    if cur is not None:
        m = re.search(r'c\[ *(\d+)\] = (\S+) (\S+) (\S+) (\S+)', l)
        if m:
            cur[int(m.group(1))] = np.array([float(m.group(i)) for i in range(2, 6)])
        m = re.search(r'tex2 off=0x(\w+)', l)
        if m:
            cur['tex2'] = m.group(1)
f0 = cubes[0]['frame']
cubes = [c for c in cubes if c['frame'] == f0]
print('%d cube draws dumped at frame %d' % (len(cubes), f0))

c = np.asarray(Image.open(os.path.join(cap0, 'rt_00AC0000.bmp')).convert('RGB'), np.int64)[:H, :W]
a = np.asarray(Image.open(os.path.join(cap0, 'rt_00AC0000_a.bmp')).convert('L'), np.int64)[:H, :W]
z24 = (a << 16) | (c[..., 0] << 8) | c[..., 1]
z = z24 / float(1 << 23) - 1.0
ys, xs = np.mgrid[0:H, 0:W]
xn = 2.0 * (xs + 0.5) / W - 1.0
yn = 1.0 - 2.0 * (ys + 0.5) / H

al0 = np.asarray(Image.open(os.path.join(cap0, 'rt_01AB0000_a.bmp')).convert('L'), float)[:H, :W]
al1 = np.asarray(Image.open(os.path.join(cap1, 'rt_01AB0000_a.bmp')).convert('L'), float)[:H, :W]
seen = np.abs(al1 - al0) > 6

out = np.zeros((H, W, 3), np.uint8)
out[..., 0] = out[..., 1] = out[..., 2] = np.where(seen, 110, 0)
colours = [(255, 60, 60), (60, 255, 60), (80, 120, 255), (255, 255, 0), (255, 0, 255), (0, 255, 255)]
for i, cb in enumerate(cubes):
    P = (cb[264][:, None, None] * xn + cb[265][:, None, None] * yn +
         cb[266][:, None, None] * z + cb[267][:, None, None])
    with np.errstate(divide='ignore', invalid='ignore'):
        box = P[:3] / P[3]
    inside = np.all(np.abs(box) <= 1.0, axis=0) & (P[3] > 0)
    uv = box[:2] * 0.5 + 0.5
    print('cube %d (tex2 %s): %d pixels inside its box, %d of them changed; changed outside it: %d'
          % (i, cb.get('tex2', '?'), inside.sum(), (inside & seen).sum(), (seen & ~inside).sum()))
    if inside.sum():
        print('   box coords there: x %.2f..%.2f  y %.2f..%.2f  z %.2f..%.2f' % (
            box[0][inside].min(), box[0][inside].max(), box[1][inside].min(), box[1][inside].max(),
            box[2][inside].min(), box[2][inside].max()))
    edge = inside & ~np.roll(inside, 1, 0) | inside & ~np.roll(inside, 1, 1)
    out[edge] = colours[i % len(colours)]
Image.fromarray(out).resize((W // 2, H // 2)).save(os.path.join(d, 'cube_replay.png'))
print(os.path.join(d, 'cube_replay.png'))
