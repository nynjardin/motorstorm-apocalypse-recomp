"""Resolve PS3_SAMPLE host RVAs to symbols with the linker map.

    python scripts/samp_resolve.py --rvas <file> [--skip-ms <ms>] [--map <map>]
    python scripts/samp_resolve.py --log port/run.log [--map <map>]

--rvas: the PS3_SAMPLE_RVAS=<file> dump (every sample, one hex RVA per line,
"# <tick ms>" closing each report block; 0 = outside the exe, 0xFFFFFF00|i =
the DLL named by a "# mod i <name>" line). --skip-ms drops
blocks closed less than <ms> after the first block (e.g. skip boot/menus and
keep the race). --log: the top-25 "[samp] rva" lines of a run log, summed.
Prints the symbol each RVA falls in (nearest public at or below it), by symbol.
--by-thread (PS3_SAMPLE_NAME runs: lines are "<rva> <tid>", threads named by "# tid <tid> <name>"):
one table per thread, with the share of its samples spent outside waits.
"""
import argparse
import bisect
import re
from collections import defaultdict


def load_map(path):
    base = 0x140000000
    syms = []
    pub = False
    with open(path, "r", encoding="latin-1") as f:
        for line in f:
            if "Preferred load address is" in line:
                base = int(line.split()[-1], 16)
            if "Publics by Value" in line:
                pub = True
                continue
            if not pub:
                continue
            parts = line.split()
            if len(parts) < 3 or ":" not in parts[0]:
                continue
            try:
                va = int(parts[2], 16)
            except ValueError:
                continue
            if va < base:
                continue
            syms.append((va - base, parts[1]))
    syms.sort()
    return [s[0] for s in syms], [s[1] for s in syms]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rvas")
    ap.add_argument("--log")
    ap.add_argument("--map", default="port/build/MotorStormApocalypse.map")
    ap.add_argument("--skip-ms", type=int, default=0)
    ap.add_argument("--top", type=int, default=60)
    ap.add_argument("--by-thread", action="store_true")
    a = ap.parse_args()
    rvas, names = load_map(a.map)
    counts = defaultdict(int)   # (tid, rva) -> samples
    mods = {}   # "# mod <index> <name>": samples outside the exe are 0xFFFFFF00 | index
    tnames = {}
    if a.rvas:
        blocks, cur = [], []
        with open(a.rvas, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("# mod "):
                    _, _, idx, name = line.split(" ", 3)
                    mods[int(idx)] = name
                    continue
                if line.startswith("# tid "):
                    parts = line.split(" ", 3)
                    tnames[int(parts[2])] = parts[3] if len(parts) > 3 else "?"
                    continue
                if line.startswith("#"):
                    blocks.append((int(line[1:].split()[0]), cur))
                    cur = []
                else:
                    parts = line.split()
                    cur.append((int(parts[1]) if len(parts) > 1 else 0, int(parts[0], 16)))
        t0 = blocks[0][0] if blocks else 0
        for t, b in blocks:
            if t - t0 < a.skip_ms:
                continue
            for r in b:
                counts[r] += 1
    else:
        rx = re.compile(r"\[samp\] rva 0x([0-9A-Fa-f]+)\s+([\d.]+)% \((\d+)\)")
        with open(a.log, "r", encoding="latin-1") as f:
            for line in f:
                m = rx.search(line)
                if m:
                    counts[(0, int(m.group(1), 16))] += int(m.group(3))

    def sym(rva):
        if rva == 0:
            return "<outside exe: waits / DLLs>"
        if (rva & 0xFFFFFF00) == 0xFFFFFF00:
            return "<dll %s>" % mods.get(rva & 0xFF, "#%d" % (rva & 0xFF))
        i = bisect.bisect_right(rvas, rva) - 1
        return names[i] if i >= 0 else "?"

    def table(items, top):
        agg = defaultdict(int)
        total = 0
        for rva, n in items:
            agg[sym(rva)] += n
            total += n
        for name, n in sorted(agg.items(), key=lambda x: -x[1])[:top]:
            print(f"{100.0 * n / max(total, 1):5.1f}%  {n:8d}  {name}")
        print(f"total {total} samples")

    if a.by_thread:
        per = defaultdict(list)
        for (tid, rva), n in counts.items():
            per[tid].append((rva, n))
        for tid, items in sorted(per.items(), key=lambda x: -sum(n for _, n in x[1])):
            print(f"=== thread {tid} [{tnames.get(tid, '?')}]")
            table(items, a.top)
    else:
        merged = defaultdict(int)
        for (tid, rva), n in counts.items():
            merged[rva] += n
        table(merged.items(), a.top)


if __name__ == "__main__":
    main()
