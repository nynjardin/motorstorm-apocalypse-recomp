# Render-thread cost per frame from the [PERF] lines of a run.log (PERF=1: one line every 20
# frames): median and mean, in ms a frame, of render_frame, its pre-pass, the SRV part of the
# pre-pass ("srv") and the texture slot calls ("tex"), plus the FPS of those lines.
# Less noisy than the window-title FPS for a change on the render thread (the title FPS also
# moves with the main thread and the 30 FPS limiter).
#   python scripts/perf_lines.py <run.log> [--last 10] [--after <text>] [--before <text>] [--min-draws-fps 0]
#   --last N     only the last N [PERF] lines (e.g. the still window at the end of idle_sig.ps1)
#   --after T / --before T   only the lines after / before the first log line containing T
#                (race_perf.ps1 marks: "[race_perf] idle begin", "drive begin", "drive end")
import sys, re, statistics
path = sys.argv[1]; last = 0; after = before = None
a = sys.argv[2:]
while a:
    if a[0] == '--last': last = int(a[1]); a = a[2:]
    elif a[0] == '--after': after = a[1]; a = a[2:]
    elif a[0] == '--before': before = a[1]; a = a[2:]
    else: sys.exit('unknown option ' + a[0])
rx = re.compile(r'\[PERF\] ([0-9.]+) fps \| tex ([0-9.]+)s \(\d+%, (\d+) calls\).*render_frame ([0-9.]+)s.*prepass ([0-9.]+)s.*\[srv ([0-9.]+)s')
rows = []; on = after is None
for line in open(path, encoding='latin-1', errors='replace'):
    if not on and after in line: on = True; continue
    if on and before and before in line: break
    if not on: continue
    m = rx.search(line)
    if m: rows.append([float(m.group(1)), float(m.group(2)) * 50, float(m.group(3)) / 20, float(m.group(4)) * 50, float(m.group(5)) * 50, float(m.group(6)) * 50])
if last: rows = rows[-last:]
if not rows: sys.exit('no [PERF] line')
names = ['fps', 'tex ms', 'tex calls', 'render_frame ms', 'prepass ms', 'srv ms']
print('%d [PERF] lines (%d frames)' % (len(rows), 20 * len(rows)))
for i, n in enumerate(names):
    col = [r[i] for r in rows]
    print('  %-16s median %7.2f  mean %7.2f  min %7.2f  max %7.2f' % (n, statistics.median(col), statistics.mean(col), min(col), max(col)))
