"""Guest frame rate over time from a PS3_FTRACE file (frames = guest flip requests).

    python scripts/ftrace_frames.py <trace.txt> [--bucket 1.0]

One line per bucket (default 1 s): start time, frames, guest FPS, median frame ms, and the mean
RSX drain time per frame. Useful when the window title FPS is not available (RSX_NO_RENDER) or
to compare two halves of one run.
"""
import argparse
import statistics

FLIP_REQ, DRAIN = 9, 7   # tools/ftrace_report.py kinds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('trace')
    ap.add_argument('--bucket', type=float, default=1.0)
    a = ap.parse_args()
    flips, drains = [], []
    with open(a.trace) as f:
        for line in f:
            if line.startswith('#') or line.startswith('T '):
                continue
            p = line.split()
            if len(p) < 6:
                continue
            k = int(p[0])
            if k == FLIP_REQ:
                flips.append(float(p[4]) / 1e6)
            elif k == DRAIN:
                drains.append((float(p[4]) / 1e6, (float(p[5]) - float(p[4])) / 1e3))
    flips.sort()
    if len(flips) < 2:
        print('fewer than 2 flips'); return
    t0 = flips[0]
    b = {}
    for x, y in zip(flips, flips[1:]):
        b.setdefault(int((x - t0) / a.bucket), []).append((y - x) * 1000)
    d = {}
    for t, ms in drains:
        d.setdefault(int((t - t0) / a.bucket), []).append(ms)
    for k in sorted(b):
        fr = b[k]
        dr = sum(d.get(k, [])) / max(1, len(fr))
        print('%8.1fs  %3d frames  %5.1f fps  median %6.1f ms  drain/frame %5.1f ms' %
              (t0 + k * a.bucket, len(fr), 1000.0 / statistics.mean(fr), statistics.median(fr), dr))


if __name__ == '__main__':
    main()
