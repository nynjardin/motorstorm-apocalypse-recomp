"""Which render targets of an RSX capture hold a given defect? Prints, for every rt_*.bmp of a capture
directory, the pixels around a display position (as seen on a 1280x720 screenshot, window border
removed) scaled to the target's size, and how many "magenta" pixels (find_magenta.py's test) lie
within <radius> display pixels of it.

    python scripts/rt_probe.py <capture frame dir> <x> <y> [radius=6] [--vp WxH]

--vp: the viewport the scene was rendered with in the big targets (dynamic resolution; the "vp="
of the manifest's draws into 0x01010000), default = the whole target.
A target where the defect is absent, followed in the frame by one where it is present, brackets
the pass that draws it (order of the passes: scripts/rsxcap_passes.py).
"""
import glob, os, struct, sys


def load(path):
    d = open(path, "rb").read()
    off, = struct.unpack_from("<I", d, 10)
    w, h, _, bpp = struct.unpack_from("<iiHH", d, 18)
    bu = h > 0; h = abs(h); bpc = bpp // 8
    stride = (w * bpc + 3) & ~3

    def px(x, y):
        r = (h - 1 - y) if bu else y
        o = off + r * stride + x * bpc
        return d[o + 2], d[o + 1], d[o]
    return w, h, px


def magenta(c):
    r, g, b = c
    return r > 170 and b > 140 and g < 0.55 * min(r, b) and abs(r - b) < 100


def main():
    a = sys.argv[1:]
    vp = None
    if "--vp" in a:
        i = a.index("--vp"); vp = tuple(int(v) for v in a[i + 1].lower().split("x")); del a[i:i + 2]
    d, x, y = a[0], float(a[1]), float(a[2])
    rad = int(a[3]) if len(a) > 3 else 6
    for f in sorted(glob.glob(os.path.join(d, "rt_*.bmp"))):
        w, h, px = load(f)
        if w < 64 or h < 64:
            continue
        sw, sh = (vp if (vp and w >= vp[0] and h >= vp[1] and (w, h) != (1280, 720)) else (w, h))
        cx, cy = int(x * sw / 1280.0), int(y * sh / 720.0)
        rx, ry = max(1, int(rad * sw / 1280.0 + 0.5)), max(1, int(rad * sh / 720.0 + 0.5))
        n = 0; best = None
        for yy in range(max(0, cy - ry), min(h, cy + ry + 1)):
            for xx in range(max(0, cx - rx), min(w, cx + rx + 1)):
                c = px(xx, yy)
                if magenta(c):
                    n += 1; best = (xx, yy, c)
        c0 = px(min(w - 1, cx), min(h - 1, cy))
        print("%-34s %4dx%-4d at %4d,%-4d colour %02X%02X%02X  magenta near: %d%s" % (
            os.path.basename(f), w, h, cx, cy, c0[0], c0[1], c0[2], n,
            ("  e.g. %d,%d %02X%02X%02X" % (best[0], best[1], *best[2])) if best else ""))


if __name__ == "__main__":
    main()
