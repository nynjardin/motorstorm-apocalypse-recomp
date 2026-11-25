"""bmpdiff.py <a.bmp> <b.bmp> [--grid N]: mean absolute difference of two same-size BMPs (RSX_CAP
dumps), overall and per cell of an NxN grid (default 8), plus each cell's mean brightness in a.
Shows WHERE two captures of a still scene differ (e.g. flicker sources). No dependencies."""
import struct
import sys


def load(path):
    d = open(path, "rb").read()
    off = struct.unpack_from("<I", d, 10)[0]
    w, h = struct.unpack_from("<ii", d, 18)
    bpp = struct.unpack_from("<H", d, 28)[0]
    flip = h > 0
    h = abs(h)
    bs = bpp // 8
    stride = (w * bs + 3) & ~3
    rows = [d[off + y * stride: off + y * stride + w * bs] for y in range(h)]
    if flip:
        rows.reverse()
    return w, h, bs, rows


def main():
    a = sys.argv[1:]
    grid = 8
    if "--grid" in a:
        i = a.index("--grid")
        grid = int(a[i + 1])
        del a[i:i + 2]
    w, h, bs, ra = load(a[0])
    w2, h2, bs2, rb = load(a[1])
    if (w, h, bs) != (w2, h2, bs2):
        sys.exit("size mismatch %s vs %s" % ((w, h, bs), (w2, h2, bs2)))
    tot = 0
    print("%dx%d, %d bytes/px; per cell: mean|a-b| (mean a)" % (w, h, bs))
    for gy in range(grid):
        line = []
        for gx in range(grid):
            y0, y1 = gy * h // grid, (gy + 1) * h // grid
            x0, x1 = gx * w // grid, (gx + 1) * w // grid
            s = n = m = 0
            for y in range(y0, y1):
                pa = ra[y][x0 * bs:x1 * bs]
                pb = rb[y][x0 * bs:x1 * bs]
                s += sum(abs(p - q) for p, q in zip(pa, pb))
                m += sum(pa)
                n += len(pa)
            tot += s
            line.append("%5.1f(%3d)" % (s / max(n, 1), m // max(n, 1)))
        print(" ".join(line))
    print("overall mean |a-b| = %.2f" % (tot / (w * h * bs)))


main()
