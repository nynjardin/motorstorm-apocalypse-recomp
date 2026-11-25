"""WWS jobs of a frame: how many, how long, which module?  (PS3_FTRACE, kind 16)

  ftrace_jobs.py <trace.txt> [--site ff5afc] [--tid 1] [--frames 2] [--top 20]

Needs a trace made with toolkit patch #39 (one PS3_FT_SPU_JOB span per job: who = SPU,
a = job module image, b = entry pc, bit 31 = closed by the next job entry, not by a return).
Report:
  - per job module: jobs per frame, SPU time per frame, median / p90 / max job length, and the
    share of that time spent in jobs longer than 1 ms (long jobs vs many small ones);
  - time the lanes are busy (kind 4) outside any job = the job manager itself + other workloads;
  - the same per module restricted to the main thread's waits at --site (the big job wait);
  - for the first --frames frames, the longest wait at --site with the jobs of each lane.
Module names: port/spu/jobmods_register.c (image id -> jobmod_<fp>).
"""
import argparse
import bisect
import collections
import os
import re
import statistics

USLEEP, SPU_BUSY, FLIP_REQ, SPU_JOB = 2, 4, 9, 16


def load(path):
    spans = []
    with open(path) as f:
        for line in f:
            if line[0] in '#T':
                continue
            k, who, a, b, t0, t1 = line.split()
            spans.append((int(k), int(who), int(a, 16), int(b, 16), float(t0), float(t1)))
    return spans


def names():
    reg = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'port', 'spu', 'jobmods_register.c')
    out = {}
    try:
        src = open(reg, encoding='latin-1').read()
    except OSError:
        return out
    for m in re.finditer(r'spu_begin_image\((\d+)\); (jobmod_[0-9a-f]{12})\w*?_spu_recomp_register', src):
        out.setdefault(int(m.group(1)), m.group(2))
    return out


def pct(v, p):
    s = sorted(v)
    return s[min(len(s) - 1, int(len(s) * p))]


def table(jobs, nf, nm, top):
    by = collections.defaultdict(list)
    for j in jobs:
        by[j[2]].append(j[5] - j[4])
    print('  %-26s %8s %9s %7s %7s %7s %8s' % ('module', 'jobs/fr', 'ms/frame', 'median', 'p90', 'max', '>1ms %'))
    for img, v in sorted(by.items(), key=lambda kv: -sum(kv[1]))[:top]:
        tot = sum(v)
        print('  %-26s %8.1f %9.2f %7.3f %7.3f %7.2f %8.0f' % (
            '%d %s' % (img, nm.get(img, '')), len(v) / nf, tot / 1e3 / nf, statistics.median(v) / 1e3,
            pct(v, 0.9) / 1e3, max(v) / 1e3, 100 * sum(x for x in v if x > 1000) / tot if tot else 0))
    allv = [j[5] - j[4] for j in jobs]
    if allv:
        print('  %-26s %8.1f %9.2f %7.3f %7.3f %7.2f' % ('all', len(allv) / nf, sum(allv) / 1e3 / nf,
              statistics.median(allv) / 1e3, pct(allv, 0.9) / 1e3, max(allv) / 1e3))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('trace')
    ap.add_argument('--site', default='ff5afc')
    ap.add_argument('--tid', type=int, default=1)
    ap.add_argument('--frames', type=int, default=2)
    ap.add_argument('--top', type=int, default=20)
    a = ap.parse_args()
    site = int(a.site, 16)
    spans = load(a.trace)
    nm = names()
    flips = sorted(s[4] for s in spans if s[0] == FLIP_REQ)
    jobs = sorted((s for s in spans if s[0] == SPU_JOB), key=lambda s: s[4])
    busy = [s for s in spans if s[0] == SPU_BUSY]
    if not jobs or len(flips) < 2:
        print('no job spans (kind 16) or no frames in this trace')
        return
    f0, f1 = flips[0], flips[-1]
    nf = len(flips) - 1
    inwin = [j for j in jobs if f0 <= j[4] < f1]
    unret = sum(1 for j in inwin if j[3] & 0x80000000)
    print('%d frames, median %.1f ms; %d jobs (%d closed by the next entry instead of a return)' % (
        nf, statistics.median(y - x for x, y in zip(flips, flips[1:])) / 1e3, len(inwin), unret))
    print('\nall jobs:')
    table(inwin, nf, nm, a.top)
    bt = collections.Counter()
    for s in busy:
        x, y = max(s[4], f0), min(s[5], f1)
        if y > x:
            bt[(s[2], s[3])] += y - x
    jt = sum(min(j[5], f1) - j[4] for j in inwin)
    print('\nlane busy time per frame (kind 4): %s' % ', '.join(
        'img %d wid %d: %.1f ms' % (k[0], k[1], v / 1e3 / nf) for k, v in bt.most_common(6)))
    print('job time per frame: %.1f ms -> busy outside jobs (manager, DMA waits, other workloads): %.1f ms' % (
        jt / 1e3 / nf, (sum(bt.values()) - jt) / 1e3 / nf))
    # by lane
    lanes = collections.Counter()
    for j in inwin:
        lanes[j[1]] += j[5] - j[4]
    print('job time per lane and frame: %s' % ', '.join('SPU%d %.1f' % (k, v / 1e3 / nf) for k, v in sorted(lanes.items())))

    waits = sorted((s for s in spans if s[0] == USLEEP and s[1] == a.tid and s[3] == site and f0 <= s[4] < f1
                    and s[5] - s[4] >= 200), key=lambda s: s[4])
    if not waits:
        return
    jt0 = [j[4] for j in jobs]
    maxlen = max(j[5] - j[4] for j in jobs)

    def over(t0, t1):
        i = bisect.bisect_left(jt0, t0 - maxlen)
        out = []
        while i < len(jobs) and jobs[i][4] < t1:
            if jobs[i][5] > t0:
                out.append(jobs[i])
            i += 1
        return out

    clipped = []
    for w in waits:
        for j in over(w[4], w[5]):
            clipped.append((j[0], j[1], j[2], j[3], max(j[4], w[4]), min(j[5], w[5])))
    print('\njobs during the waits of thread %d at %06X (%.1f ms of wait per frame), clipped to the waits:' % (
        a.tid, site, sum(w[5] - w[4] for w in waits) / 1e3 / nf))
    table(clipped, nf, nm, a.top)

    for x, y in list(zip(flips, flips[1:]))[:a.frames]:
        ws = [w for w in waits if x <= w[4] < y]
        if not ws:
            continue
        w = max(ws, key=lambda s: s[5] - s[4])
        print('\nframe at %.1f (%.1f ms): longest wait +%.2f .. +%.2f (%.2f ms)' % (
            x / 1e3, (y - x) / 1e3, (w[4] - x) / 1e3, (w[5] - x) / 1e3, (w[5] - w[4]) / 1e3))
        rows = collections.defaultdict(list)
        for j in over(w[4], w[5]):
            rows[j[1]].append(j)
        for lane in sorted(rows):
            r = rows[lane]
            txt = ' '.join('[%d %+.2f %.2f]' % (j[2], (j[4] - w[4]) / 1e3, (j[5] - j[4]) / 1e3) for j in r[:16])
            print('  SPU%d (%d jobs, %.2f ms): %s%s' % (lane, len(r), sum(j[5] - j[4] for j in r) / 1e3, txt,
                  ' ...' if len(r) > 16 else ''))
        print('  [module start-relative-to-wait length], ms')


if __name__ == '__main__':
    main()
