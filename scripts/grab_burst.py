# Fast burst of screenshots of the game window (true consecutive frames, unlike RSX_CAP whose
# dumps stall the game for a second each): N grabs as fast as possible, then a report of the
# mean luma change per screen cell between consecutive grabs, and an amplified difference strip.
#   python scripts/grab_burst.py <out_dir> [--n 60] [--cell 160] [--title ps3recomp]
# Needs the window visible (not minimised, not covered). System python (PIL + numpy), not the venv.
import sys, os, time, ctypes
from ctypes import wintypes
import numpy as np
from PIL import Image, ImageGrab

out = sys.argv[1]
n, cell, title = 60, 160, 'ps3recomp'
a = sys.argv[2:]
while a:
    if a[0] == '--n': n = int(a[1])
    elif a[0] == '--cell': cell = int(a[1])
    elif a[0] == '--title': title = a[1]
    a = a[2:]
os.makedirs(out, exist_ok=True)
user32 = ctypes.windll.user32
try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception: pass
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
found = []
def cb(h, l):
    b = ctypes.create_unicode_buffer(256); user32.GetWindowTextW(h, b, 256)
    if b.value.startswith(title) and user32.IsWindowVisible(h): found.append(h)
    return True
user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(cb), 0)
if not found: sys.exit('window not found')
h = found[0]
user32.ShowWindow(h, 9); user32.SetForegroundWindow(h); time.sleep(0.5)
pt = wintypes.POINT(0, 0); user32.ClientToScreen(h, ctypes.byref(pt))
rc = wintypes.RECT(); user32.GetClientRect(h, ctypes.byref(rc))
box = (pt.x, pt.y, pt.x + rc.right, pt.y + rc.bottom)
shots, times = [], []
tick0 = ctypes.windll.kernel32.GetTickCount64()   # same clock as the [FP_VSUM] / [FP_NSUM] lines of run.log
t0 = time.perf_counter()
for i in range(n):
    shots.append(ImageGrab.grab(bbox=box)); times.append(time.perf_counter() - t0)
print('%d grabs in %.2f s (%.1f per second), %dx%d' % (n, times[-1], n / times[-1], rc.right, rc.bottom))
g = [np.asarray(s.convert('L'), dtype=np.float32) for s in shots]
# drop grabs identical to the previous one (same game frame grabbed twice)
keep = [0] + [i for i in range(1, n) if np.abs(g[i] - g[i - 1]).mean() > 0.01]
print('distinct frames: %d' % len(keep))
for k, i in enumerate(keep): shots[i].save(os.path.join(out, 'b%03d.png' % k))
g = [g[i] for i in keep]
hh, ww = g[0].shape; gy, gx = hh // cell, ww // cell
ser = np.array([[[im[y*cell:(y+1)*cell, x*cell:(x+1)*cell].mean() for x in range(gx)] for y in range(gy)] for im in g])
st = np.abs(np.diff(ser, axis=0))
print('mean |step| per cell between consecutive distinct frames:')
for y in range(gy): print(' '.join('%5.1f' % st[:, y, x].mean() for x in range(gx)))
# second difference: a smooth drift has small |f(i+1) - 2 f(i) + f(i-1)|, a blink has a large one
d2 = np.abs(ser[2:] - 2 * ser[1:-1] + ser[:-2])
print('mean |second difference| per cell (blink, not drift):')
for y in range(gy): print(' '.join('%5.1f' % d2[:, y, x].mean() for x in range(gx)))
y0, x0 = int(st.mean(axis=0).argmax()) // gx, int(st.mean(axis=0).argmax()) % gx
print('most unstable cell (%d,%d) luma series:' % (x0, y0), ' '.join('%.0f' % v for v in ser[:, y0, x0]))
# ticks.txt: host tick (ms) and luma of that cell for every distinct frame, to line up with run.log
with open(os.path.join(out, 'ticks.txt'), 'w') as f:
    for k, i in enumerate(keep): f.write('%d %.1f%s' % (tick0 + int(times[i] * 1000), ser[k, y0, x0], chr(10)))
