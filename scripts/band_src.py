"""Where does a wrong patch of a captured render target come from?

    python scripts/band_src.py <rt.bmp> x0 x1 y0 y1

The patch (x0..x1, y0..y1, exclusive ends) is compared with candidate source positions of the SAME
picture: same column or mirrored column, row y / H-1-y (+-2 rows, +-6 columns). For each candidate
the ratio patch / source is taken pixel by pixel; the real source has a constant ratio (relative
spread of a few %), a coincidence does not. Prints the six best candidates.
This is what showed that the "mirror" tyre tracks were 0.865 x the scene of row H-1-y whatever
the viewport height (a flip over the window height: WPOS origin, toolkit patch #54), and not an
undefined read. BMPs of an RSX capture (rt_*.bmp) are read directly, no PIL needed.
"""
import struct, sys


def main():
    if len(sys.argv) < 6:
        sys.exit(__doc__)
    d = open(sys.argv[1], "rb").read()
    off, = struct.unpack_from("<I", d, 10)
    w, h, _, bpp = struct.unpack_from("<iiHH", d, 18)
    bottom_up = h > 0
    h = abs(h)
    bpc = bpp // 8
    stride = (w * bpc + 3) & ~3

    def px(x, y):
        r = (h - 1 - y) if bottom_up else y
        o = off + r * stride + x * bpc
        return d[o + 2] + d[o + 1] + d[o]

    x0, x1, y0, y1 = map(int, sys.argv[2:6])

    def spread(fx, fy):
        rs = []
        for y in range(y0, y1):
            for x in range(x0, x1):
                sx, sy = fx(x), fy(y)
                if not (0 <= sx < w and 0 <= sy < h):
                    continue
                b = px(sx, sy)
                if b < 60:
                    continue
                rs.append(px(x, y) / b)
        if len(rs) < 20:
            return None
        m = sum(rs) / len(rs)
        return (sum((r - m) ** 2 for r in rs) / len(rs)) ** 0.5 / m, m, len(rs)

    res = []
    cols = (("same column", lambda x: x), ("column W-1-x", lambda x: w - 1 - x))
    rows = (("row y", lambda y: y), ("row H-1-y", lambda y: h - 1 - y))
    for cname, fx in cols:
        for rname, fy in rows:
            for dx in range(-6, 7, 2):
                for dy in range(-2, 3):
                    if cname == "same column" and rname == "row y" and abs(dx) < 4 and abs(dy) < 2:
                        continue   # the patch itself
                    s = spread(lambda x, fx=fx, dx=dx: fx(x) + dx, lambda y, fy=fy, dy=dy: fy(y) + dy)
                    if s:
                        res.append((s[0], cname, dx, rname, dy, s[1], s[2]))
    res.sort()
    print(f"picture {w}x{h}, patch x {x0}..{x1} y {y0}..{y1}")
    for r in res[:6]:
        print("relative spread %.3f  %s %+d, %s %+d  ratio %.3f  (%d pixels)" % r)


if __name__ == "__main__":
    main()
