"""cube_alpha.py <dir of a pause_start run> [before gate] [after gate]
The dark squares' check (2026-11-25): the alpha of target 01AB0000 (the occlusion term the
scene pass reads) right before and right after the vehicles' contact-shadow cubes (program
0x301), from the captures gate_00 (gate 'fpb=301') and gate_01 ('fp=301') of
scripts/pause_start.ps1 -Photo -Gates 'fpb=301','fp=301' -Env @{RSX_CAP_ALPHA='1'}.
Inside the cubes the alpha should only be multiplied by the soft shadow (about 1 away from the
vehicle): prints how many pixels changed, by how much (after / before), and writes
<dir>/cube_alpha.png = before | after | difference x3.
System python (PIL, numpy).
"""
import sys, os
import numpy as np
from PIL import Image

d = sys.argv[1]
g0 = sys.argv[2] if len(sys.argv) > 2 else 'gate_00'
g1 = sys.argv[3] if len(sys.argv) > 3 else 'gate_01'
a0 = np.asarray(Image.open(os.path.join(d, 'cap', g0, 'rt_01AB0000_a.bmp')).convert('L'), float)
a1 = np.asarray(Image.open(os.path.join(d, 'cap', g1, 'rt_01AB0000_a.bmp')).convert('L'), float)
diff = np.abs(a1 - a0)
m = diff > 6
print('pixels changed by more than 6: %d (%.1f %% of the target)' % (m.sum(), 100.0 * m.mean()))
if m.sum():
    ratio = (a1[m] + 1) / (a0[m] + 1)
    print('after / before where changed: mean %.3f, 10 %% %.3f, 50 %% %.3f, 90 %% %.3f' %
          (ratio.mean(), *np.percentile(ratio, [10, 50, 90])))
    print('mean alpha there: before %.0f, after %.0f' % (a0[m].mean(), a1[m].mean()))
h, w = a0.shape
out = Image.new('L', (w * 3 // 2, h // 2))
for i, im in enumerate((a0, a1, np.minimum(255, diff * 3))):
    out.paste(Image.fromarray(im.astype(np.uint8)).resize((w // 2, h // 2)), (i * w // 2, 0))
out.save(os.path.join(d, 'cube_alpha.png'))
print(os.path.join(d, 'cube_alpha.png'))
