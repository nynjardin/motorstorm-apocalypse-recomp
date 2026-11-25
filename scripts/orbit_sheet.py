"""orbit_sheet.py <pause_start dir> [out.png] [--width 640] [--file backbuffer.bmp]
Contact sheet of the captures of scripts/pause_start.ps1 (system python, PIL): first row the
"off" series (the frame as it is), second row the "kill" series (the hand-blending draws left
out), in capture order around the orbit of the pause camera.
--file: another image of each capture (rt_01010000.bmp = the scene before the HUD).
"""
import glob
import os
import sys

from PIL import Image, ImageDraw

args = []
skip = False
for a in sys.argv[1:]:          # positional arguments only (a flag takes the word after it)
    if skip:
        skip = False
    elif a.startswith('--'):
        skip = True
    else:
        args.append(a)
root = args[0]
out = args[1] if len(args) > 1 else os.path.join(root, 'orbit.png')
W = int(sys.argv[sys.argv.index('--width') + 1]) if '--width' in sys.argv else 640
name = sys.argv[sys.argv.index('--file') + 1] if '--file' in sys.argv else 'backbuffer.bmp'
rows = [sorted(glob.glob(os.path.join(root, 'cap', p))) for p in ('off_*', 'kill_*', 'kill0_*', 'kill1_*', 'kill2_*', 'kill3_*')]
rows = [r for r in rows if r]
n = max(len(r) for r in rows)
H = W * 9 // 16
sheet = Image.new('RGB', (n * W, len(rows) * H), (40, 0, 40))
for y, r in enumerate(rows):
    for x, d in enumerate(r):
        try:
            im = Image.open(os.path.join(d, name)).convert('RGB').resize((W, H), Image.LANCZOS)
        except OSError as e:
            print(d, e)
            continue
        ImageDraw.Draw(im).text((6, 4), os.path.basename(d), fill=(255, 0, 255))
        sheet.paste(im, (x * W, y * H))
sheet.save(out)
print(out)
