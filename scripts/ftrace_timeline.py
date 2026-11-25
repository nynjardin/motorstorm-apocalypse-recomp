"""One frame as a text timeline: what the main thread does and which job runs on each lane.

  ftrace_timeline.py <trace.txt> [--frame N | --median] [--bin-ms 0.25] [--tid 1] [--long 1.0]

PS3_FTRACE trace (toolkit patch #39 for the per-job spans, kind 16). For the chosen frame
(between two flip requests, kind 9; --median = a frame of median length, default) prints one
row for the main thread (R = running, a letter per wait site, legend below) and one row per
SPU lane (a letter per job module, '.' = idle, '+' = busy outside any job: job manager,
other SPURS workloads), one column per --bin-ms. Then the jobs longer than --long ms with
their start (relative to the frame start), length and lane, and the critical-path summary:
for every main-thread wait, which jobs were still running when it ended.
Use it after ftrace_idle.py / ftrace_jobs.py, to see the ORDER of things in a frame.
"""
import argparse
import collections
import os
import re
import statistics

SYSCALL, USLEEP, SPU_BUSY, FLIP_REQ, SPU_JOB = 1, 2, 4, 9, 16


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


def modnames():
    here = os.path.dirname(os.path.abspath(__file__))
    out = {}
    try:
        import subprocess, sys
        txt = subprocess.run([sys.executable, os.path.join(here, 'jobmod_names.py')],
                             capture_output=True, text=True, timeout=60).stdout
        for line in txt.splitlines():
            m = re.search(r'\bid\s+(\d+)\s+(jobmod_[0-9a-f]{12})', line)
            n = re.match(r'\s*(\w+)', line)
            if m and n:
                out[int(m.group(1))] = n.group(1)
    except Exception:
        pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('trace')
    ap.add_argument('--frame', type=int, default=-1)
    ap.add_argument('--bin-ms', type=float, default=0.25)
    ap.add_argument('--tid', type=int, default=1)
    ap.add_argument('--long', type=float, default=1.0)
    ap.add_argument('--names', action='store_true', help='resolve module names with jobmod_names.py')
    args = ap.parse_args()
    names, spans = load(args.trace)
    # unit: the trace is in ms if frames are ~30 apart, else seconds or us
    flips = sorted(s[4] for s in spans if s[0] == FLIP_REQ)
    gaps = [b - a for a, b in zip(flips, flips[1:])]
    med = statistics.median(gaps)
    scale = 1.0
    if med < 1.0:
        scale = 1000.0           # seconds -> ms
    elif med > 1000.0:
        scale = 0.001            # us -> ms
    if args.frame >= 0:
        fi = args.frame
    else:
        order = sorted(range(len(gaps)), key=lambda i: gaps[i])
        fi = order[len(order) // 2]
    f0, f1 = flips[fi], flips[fi + 1]
    L = (f1 - f0) * scale
    print(f'{len(gaps)} frames, median {med * scale:.1f} ms; frame {fi}: {L:.1f} ms')

    def rel(t):
        return (t - f0) * scale

    nb = int(L / args.bin_ms) + 1
    inwin = [s for s in spans if s[5] > f0 and s[4] < f1]
    # main thread row
    row = ['R'] * nb
    sites, letters = {}, 'abcdefghijklmnopqrstuvwxyz'
    waits = []
    for k, who, a, b, t0, t1 in inwin:
        if who != args.tid or k not in (SYSCALL, USLEEP):
            continue
        key = ('usleep' if k == USLEEP else f'syscall {a}', b)
        if (t1 - t0) * scale < args.bin_ms / 2 and k == SYSCALL:
            continue
        if key not in sites:
            sites[key] = letters[len(sites) % 26]
        waits.append((rel(t0), rel(t1), key))
        for i in range(max(0, int(rel(t0) / args.bin_ms + 0.5)), min(nb, int(rel(t1) / args.bin_ms + 0.5))):
            row[i] = sites[key]
    print('\n      ms ' + ''.join(str(int(i * args.bin_ms) % 10) if abs(i * args.bin_ms - round(i * args.bin_ms)) < 1e-9 else ' ' for i in range(nb)))
    print('    main ' + ''.join(row))
    # lanes
    jobs = [s for s in inwin if s[0] == SPU_JOB]
    busy = [s for s in inwin if s[0] == SPU_BUSY]
    mods = sorted({s[2] for s in jobs})
    modtime = collections.Counter()
    for s in jobs:
        modtime[s[2]] += s[5] - s[4]
    sym = {}
    pool = 'ABCDEFGHIJKLMNOPQSTUVWXYZ0123456789'
    for i, (m, _) in enumerate(modtime.most_common()):
        sym[m] = pool[i] if i < len(pool) else '#'
    for who in sorted({s[1] for s in busy} | {s[1] for s in jobs}):
        r = ['.'] * nb
        for s in busy:
            if s[1] == who:
                for i in range(max(0, int(rel(s[4]) / args.bin_ms + 0.5)), min(nb, int(rel(s[5]) / args.bin_ms + 0.5))):
                    r[i] = '+'
        for s in jobs:
            if s[1] == who:
                a, b = rel(s[4]), rel(s[5])
                i0, i1 = max(0, int(a / args.bin_ms + 0.5)), min(nb, int(b / args.bin_ms + 0.5))
                for i in range(i0, max(i1, i0 + (1 if b - a >= args.bin_ms / 2 else 0))):
                    if i < nb:
                        r[i] = sym[s[2]]
        if any(c != '.' for c in r):
            print(f'{("SPU" + str(who))[-8:]:>8} ' + ''.join(r))
    mn = modnames() if args.names else {}
    print('\nmain: R = running; ' + '; '.join(f'{v} = {k[0]}@{k[1]:08X}' for k, v in sites.items()))
    print('jobs: ' + '; '.join(f'{sym[m]} = {m}{" " + mn[m] if m in mn else ""} ({modtime[m] * scale:.1f} ms)' for m, _ in modtime.most_common()))
    print(f'\njobs longer than {args.long} ms (start, length, lane, module, entry):')
    for s in sorted(jobs, key=lambda s: s[4]):
        d = (s[5] - s[4]) * scale
        if d >= args.long:
            print(f'  +{rel(s[4]):6.2f} {d:6.2f}  SPU{s[1]}  {s[2]}{" " + mn[s[2]] if s[2] in mn else ""}  pc {s[3] & 0x7FFFFFFF:05X}')
    print('\nmain-thread waits >= 0.3 ms and what was still running in their last 0.1 ms:')
    merged = []
    for a, b, key in sorted(waits):
        if merged and merged[-1][2] == key and a - merged[-1][1] < 0.15:
            merged[-1][1] = b
        else:
            merged.append([a, b, key])
    for a, b, key in merged:
        if b - a < 0.3:
            continue
        last = collections.Counter()
        for s in jobs:
            if rel(s[5]) > b - 0.1 and rel(s[4]) < b:
                last[(s[2], s[1])] += 1
        desc = ', '.join(f'{m} on SPU{w} (started +{min(rel(s[4]) for s in jobs if s[2] == m and s[1] == w and rel(s[5]) > b - 0.1 and rel(s[4]) < b):.2f})' for (m, w) in last)
        print(f'  +{a:6.2f} .. +{b:6.2f} ({b - a:5.2f} ms) {key[0]}@{key[1]:08X}: {desc or "no job"}')


if __name__ == '__main__':
    main()
