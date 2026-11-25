"""Who works while the main thread waits?  (PS3_FTRACE timeline)

  ftrace_idle.py <trace.txt> [--step-us 20] [--tid 1]

For every instant of the trace (sampled every --step-us) the main PPU thread is
either running or waiting (merged usleep polls, kind 2, or a blocking syscall,
kind 1), and each SPURS lane is busy (kind 4) or not. The report gives, per wait
site (guest lr) of the main thread, the time spent with 0, 1, 2, ... lanes busy.
Time the main thread waits at a job-completion site with no lane busy is pure
latency (hand-offs, polls, wake-ups), not computation.
Also: frame length (between two flip requests, kind 9), busy time per lane and
per (image, workload), and the longest stretches "main waits, nothing runs".
"""
import argparse
import bisect
import collections
import statistics

SYSCALL, USLEEP, SPU_WAIT, SPU_BUSY = 1, 2, 3, 4
FLIP_REQ = 9


def load(path):
    names, spans = {}, []
    with open(path) as f:
        for line in f:
            if line.startswith('#'):
                continue
            if line.startswith('T '):
                _, tid, name = line.rstrip('\n').split(' ', 2)
                names[int(tid)] = name
                continue
            k, who, a, b, t0, t1 = line.split()
            spans.append((int(k), int(who), int(a, 16), int(b, 16), float(t0), float(t1)))
    return names, spans


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('trace')
    ap.add_argument('--step-us', type=float, default=20.0)
    ap.add_argument('--tid', type=int, default=1)
    args = ap.parse_args()
    names, spans = load(args.trace)
    kinds = collections.Counter(s[0] for s in spans)
    print('span kinds:', dict(sorted(kinds.items())))
    t_lo = min(s[4] for s in spans if s[0] in (USLEEP, SPU_BUSY))
    t_hi = max(s[5] for s in spans)
    # trim: spans that began before the window carry early t0
    flips = sorted(s[4] for s in spans if s[0] == FLIP_REQ)
    if len(flips) > 2:
        d = [b - a for a, b in zip(flips, flips[1:])]
        print('frames: %d, median %.1f ms, mean %.1f ms' % (len(d), statistics.median(d) / 1e3, sum(d) / len(d) / 1e3))
        t_lo, t_hi = flips[0], flips[-1]
    n = int((t_hi - t_lo) / args.step_us)
    step = args.step_us
    main_site = [0] * n          # 0 = running, else key of the wait site
    lanes = [0] * n
    site_key = {}
    site_name = {0: 'running'}

    def mark(arr, t0, t1, fn):
        i0 = max(0, int((t0 - t_lo) / step))
        i1 = min(n, int((t1 - t_lo) / step))
        for i in range(i0, i1):
            fn(arr, i)

    lane_busy = collections.Counter()
    img_busy = collections.Counter()
    for k, who, a, b, t0, t1 in spans:
        if k == SPU_BUSY:
            lane_busy[who] += max(0.0, min(t1, t_hi) - max(t0, t_lo))
            img_busy[(a, b)] += max(0.0, min(t1, t_hi) - max(t0, t_lo))
            i0 = max(0, int((t0 - t_lo) / step))
            i1 = min(n, int((t1 - t_lo) / step))
            for i in range(i0, i1):
                lanes[i] += 1
        elif who == args.tid and k in (USLEEP, SYSCALL):
            name = ('usleep@%08X' % b) if k == USLEEP else ('syscall %d @%08X' % (a, b))
            key = site_key.setdefault(name, len(site_key) + 1)
            site_name[key] = name
            i0 = max(0, int((t0 - t_lo) / step))
            i1 = min(n, int((t1 - t_lo) / step))
            for i in range(i0, i1):
                main_site[i] = key
    total_ms = n * step / 1e3
    nframes = max(1, len(flips) - 1)
    print('window %.0f ms, %d frames' % (total_ms, nframes))
    print('\nlane busy (ms per frame):', ', '.join('SPU%d %.1f' % (w, v / 1e3 / nframes) for w, v in sorted(lane_busy.items())))
    print('busy per (image, wid), ms per frame:', ', '.join('img %d wid %d: %.1f' % (a, b, v / 1e3 / nframes)
                                                           for (a, b), v in img_busy.most_common(8)))
    table = collections.defaultdict(collections.Counter)
    for i in range(n):
        table[main_site[i]][min(lanes[i], 4)] += 1
    print('\nmain thread state x lanes busy (ms per frame):')
    print('  %-28s %8s | %7s %7s %7s %7s %7s' % ('state', 'total', '0 lane', '1', '2', '3', '4+'))
    for key, c in sorted(table.items(), key=lambda kv: -sum(kv[1].values())):
        tot = sum(c.values()) * step / 1e3 / nframes
        if tot < 0.2:
            continue
        print('  %-28s %8.1f | %s' % (site_name[key], tot,
                                      ' '.join('%7.1f' % (c[j] * step / 1e3 / nframes) for j in range(5))))
    # what the lanes run during each state of the main thread
    by_state = collections.defaultdict(collections.Counter)
    for k, who, a, b, t0, t1 in spans:
        if k != SPU_BUSY:
            continue
        i0 = max(0, int((t0 - t_lo) / step))
        i1 = min(n, int((t1 - t_lo) / step))
        for i in range(i0, i1):
            by_state[main_site[i]][(a, b)] += 1
    print('\nlane time per main thread state, by (image, wid) (ms per frame):')
    for key, c in sorted(by_state.items(), key=lambda kv: -sum(kv[1].values())):
        if sum(c.values()) * step / 1e3 / nframes < 0.5:
            continue
        print('  %-28s %s' % (site_name[key], ', '.join(
            'img %d wid %d: %.1f' % (a, b, v * step / 1e3 / nframes) for (a, b), v in c.most_common(6))))
    # longest stretches: main waiting and no lane busy
    runs, cur, cur_site = [], 0, 0
    for i in range(n):
        if main_site[i] and lanes[i] == 0:
            if not cur:
                cur_site = main_site[i]
            cur += 1
        else:
            if cur:
                runs.append((cur * step / 1e3, cur_site, i - cur))
            cur = 0
    runs.sort(reverse=True)
    print('\nstretches "main waits, no lane busy": %d, total %.1f ms/frame; >= 1 ms: %d (%.1f ms/frame)' % (
        len(runs), sum(r[0] for r in runs) / nframes,
        sum(1 for r in runs if r[0] >= 1.0), sum(r[0] for r in runs if r[0] >= 1.0) / nframes))
    hist = collections.Counter()
    for ms, _, _ in runs:
        b = 0.05
        while ms > b and b < 64:
            b *= 2
        hist[b] += ms
    print('  by length (upper bound ms -> ms/frame):', ', '.join('%.2g: %.1f' % (b, v / nframes) for b, v in sorted(hist.items())))
    for ms, site, i in runs[:8]:
        print('  %.2f ms at %s (t=+%.1f ms)' % (ms, site_name[site], i * step / 1e3))


if __name__ == '__main__':
    main()
