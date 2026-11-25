"""What runs on the SPU lanes during each wait of the main thread at one site?

  ftrace_site.py <trace.txt> [--site ff5afc] [--tid 1] [--frames 3]

Companion of ftrace_idle.py (same PS3_FTRACE file). The waits of thread --tid
at usleep site --site (guest lr, hex) are numbered inside each frame (frame =
between two flip requests). Report:
  - per ordinal (1st wait of the frame, 2nd, ...): how often it exists, median
    length, where in the frame it starts, lane time per (image, wid) during it,
    and the time with exactly 1 lane busy split by which (image, wid) is alone;
  - the detailed timeline of the first --frames frames: each wait with the SPU
    spans that overlap it (lane, image, wid, start/end relative to the wait).
"""
import argparse
import bisect
import collections
import statistics

SYSCALL, USLEEP, SPU_BUSY, FLIP_REQ = 1, 2, 4, 9


def load(path):
    spans = []
    with open(path) as f:
        for line in f:
            if line[0] in '#T':
                continue
            k, who, a, b, t0, t1 = line.split()
            spans.append((int(k), int(who), int(a, 16), int(b, 16), float(t0), float(t1)))
    return spans


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('trace')
    ap.add_argument('--site', default='ff5afc')
    ap.add_argument('--tid', type=int, default=1)
    ap.add_argument('--frames', type=int, default=3)
    ap.add_argument('--min-ms', type=float, default=0.2, help='ignore waits shorter than this')
    args = ap.parse_args()
    site = int(args.site, 16)
    spans = load(args.trace)
    flips = sorted(s[4] for s in spans if s[0] == FLIP_REQ)
    busy = sorted((s for s in spans if s[0] == SPU_BUSY), key=lambda s: s[4])
    busy_t0 = [s[4] for s in busy]
    max_len = max(s[5] - s[4] for s in busy)
    waits = sorted((s for s in spans if s[0] == USLEEP and s[1] == args.tid and s[3] == site
                    and s[5] - s[4] >= args.min_ms * 1e3), key=lambda s: s[4])
    other = sorted((s for s in spans if s[1] == args.tid and s[0] in (USLEEP, SYSCALL)), key=lambda s: s[4])

    def overlapping(t0, t1):
        i = bisect.bisect_left(busy_t0, t0 - max_len)
        out = []
        while i < len(busy) and busy[i][4] < t1:
            if busy[i][5] > t0:
                out.append(busy[i])
            i += 1
        return out

    def profile(t0, t1):
        """-> (lane time per (img, wid), time alone per (img, wid), time with 0 lane)"""
        ov = overlapping(t0, t1)
        ev = []
        per = collections.Counter()
        for s in ov:
            a, b = max(s[4], t0), min(s[5], t1)
            per[(s[2], s[3])] += b - a
            ev.append((a, 1, (s[2], s[3])))
            ev.append((b, -1, (s[2], s[3])))
        ev.sort(key=lambda e: (e[0], e[1]))
        alone = collections.Counter()
        cur = collections.Counter()
        last, none = t0, 0.0
        for t, d, key in ev:
            n = sum(cur.values())
            if n == 0:
                none += t - last
            elif n == 1:
                alone[next(k for k, v in cur.items() if v)] += t - last
            cur[key] += d
            last = t
        if sum(cur.values()) == 0:
            none += t1 - last
        return per, alone, none

    by_ord = collections.defaultdict(list)
    frames = []
    for f0, f1 in zip(flips, flips[1:]):
        ws = [w for w in waits if f0 <= w[4] < f1]
        frames.append((f0, f1, ws))
        for i, w in enumerate(ws):
            by_ord[i].append((w, f0, f1))
    nf = len(frames)
    print('%d frames, median %.1f ms; waits at %06X >= %.1f ms: %d (%.1f per frame, %.1f ms per frame)' % (
        nf, statistics.median(f1 - f0 for f0, f1, _ in frames) / 1e3, site, args.min_ms, len(waits),
        len(waits) / nf, sum(w[5] - w[4] for w in waits) / 1e3 / nf))
    print('waits per frame:', dict(sorted(collections.Counter(len(ws) for _, _, ws in frames).items())))
    print('\nper ordinal inside the frame (ms; lane time and "alone" = exactly one lane busy):')
    for i in sorted(by_ord):
        lst = by_ord[i]
        per, alone, none = collections.Counter(), collections.Counter(), 0.0
        for w, f0, f1 in lst:
            p, a, z = profile(w[4], w[5])
            per.update(p)
            alone.update(a)
            none += z
        n = len(lst)
        print('  #%d: in %3d frames, median %.2f ms (mean %.2f), starts at +%.1f ms of the frame' % (
            i + 1, n, statistics.median(w[5] - w[4] for w, _, _ in lst) / 1e3,
            sum(w[5] - w[4] for w, _, _ in lst) / 1e3 / n,
            statistics.median(w[4] - f0 for w, f0, _ in lst) / 1e3))
        print('      lane time: %s' % ', '.join('img %d wid %d: %.2f' % (k[0], k[1], v / 1e3 / n) for k, v in per.most_common(5)))
        print('      alone:     %s ; nothing runs: %.2f' % (
            ', '.join('img %d wid %d: %.2f' % (k[0], k[1], v / 1e3 / n) for k, v in alone.most_common(4)), none / 1e3 / n))
    for f0, f1, ws in frames[:args.frames]:
        print('\nframe at %.1f, %.1f ms' % (f0 / 1e3, (f1 - f0) / 1e3))
        prev = f0
        for w in ws:
            # what the thread did since the previous wait at this site
            mid = [o for o in other if prev <= o[4] < w[4] and o[5] - o[4] >= 300 and not (o[0] == USLEEP and o[3] == site)]
            for o in mid:
                print('    (+%.2f: %s %.2f ms)' % ((o[4] - f0) / 1e3,
                      ('usleep@%06X' % o[3]) if o[0] == USLEEP else ('syscall %d @%06X' % (o[2], o[3])), (o[5] - o[4]) / 1e3))
            print('  wait +%.2f .. +%.2f (%.2f ms)' % ((w[4] - f0) / 1e3, (w[5] - f0) / 1e3, (w[5] - w[4]) / 1e3))
            rows = collections.defaultdict(list)
            for s in overlapping(w[4], w[5]):
                rows[s[1]].append(s)
            for lane in sorted(rows):
                txt = ' '.join('[w%d %+.2f..%+.2f]' % (s[3], (s[4] - w[4]) / 1e3, (s[5] - w[4]) / 1e3)
                               if s[2] == 1 else '[i%d/w%d %+.2f..%+.2f]' % (s[2], s[3], (s[4] - w[4]) / 1e3, (s[5] - w[4]) / 1e3)
                               for s in rows[lane][:14])
                more = len(rows[lane]) - 14
                print('    SPU%d: %s%s' % (lane, txt, (' ... +%d' % more) if more > 0 else ''))
            prev = w[5]


if __name__ == '__main__':
    main()
