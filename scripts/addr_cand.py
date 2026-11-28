#!/usr/bin/env python3
"""addr_cand.py <disc addr>...: candidates in the 1.06 EBOOT for functions of the disc EBOOT that
scripts/addr_map.py could not match (or that you want to check), with a side-by-side disassembly.

    python scripts/addr_cand.py 0x002BD2D8 0x0082E4C8 [--dis 24] [--top 4]

Candidates come from the matched neighbours of the function (callers' callees, callees' callers) and
from the opcode-trigram index; each is scored (neighbour votes, Jaccard of the features, length).
Needs work/BCES00484_106/addr_map.json (addr_map.py). Judge by the disassembly: the compilers differ,
so registers and scheduling change, constants, call targets (through the map) and field offsets do not.
"""
import argparse, json, collections, bisect, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import addr_map as M
from capstone import Cs, CS_ARCH_PPC, CS_MODE_64, CS_MODE_BIG_ENDIAN

md = Cs(CS_ARCH_PPC, CS_MODE_64 | CS_MODE_BIG_ENDIAN)


def dis(img, addr, n, mp=None, rev=None):
    ws = img.funcs.get(addr)
    if ws is None:
        return []
    out = []
    raw = img.read(addr, min(len(ws), n) * 4)
    for i in md.disasm(raw, addr):
        txt = "%08x  %-7s %s" % (i.address, i.mnemonic, i.op_str)
        if i.mnemonic in ("bl", "b") and mp is not None:
            try:
                t = int(i.op_str, 0)
                k = "0x%08X" % t
                if mp is not None and k in mp:
                    txt += "   ; -> %s" % mp[k]["new"]
            except ValueError:
                pass
        out.append(txt)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("addrs", nargs="+")
    ap.add_argument("--dis", type=int, default=0)
    ap.add_argument("--top", type=int, default=4)
    ap.add_argument("--map", default=str(M.NEW / "addr_map.json"))
    a = ap.parse_args()
    mp = json.loads(Path(a.map).read_text())
    A = M.Image(M.ELF_DISC, M.DISC / "ppu" / "functions.code.json")
    B = M.Image(M.ELF_NEW, M.NEW / "ppu" / "functions.code.json")
    fa = {s: M.features(A, s, w) for s, w in A.funcs.items()}
    fb = {s: M.features(B, s, w) for s, w in B.funcs.items()}
    match = {int(k, 16): int(v["new"], 16) for k, v in mp.items()}
    used = set(match.values())
    callers_b = collections.defaultdict(set)
    callers_a = collections.defaultdict(set)
    for s, (_, calls, _) in fb.items():
        for c in calls:
            callers_b[c].add(s)
    for s, (_, calls, _) in fa.items():
        for c in calls:
            callers_a[c].add(s)
    idx = collections.defaultdict(list)
    for s, (toks, _, _) in fb.items():
        for k in toks:
            idx[k].append(s)
    keys = sorted(A.funcs)
    for q in a.addrs:
        s = int(q, 0)
        base = keys[bisect.bisect_right(keys, s) - 1]
        toks, calls, strs = fa[base]
        print("=" * 78)
        print("disc %08X  len %d  callers %d  callees %d  strings %s" %
              (base, len(A.funcs[base]), len(callers_a[base]), len(set(calls)),
               [x[:40] for x in list(strs)[:3]]))
        votes = collections.Counter()
        for c in callers_a[base]:
            if c in match:
                for y in set(fb[match[c]][1]):
                    votes[y] += 1
        for c in set(calls):
            if c in match:
                for y in callers_b.get(match[c], ()):
                    votes[y] += 1
        cnt = collections.Counter()
        for k in toks:
            lst = idx.get(k)
            if lst and len(lst) <= 300:
                for y in lst:
                    cnt[y] += 1
        cand = set(y for y, _ in votes.most_common(30)) | set(y for y, _ in cnt.most_common(30))
        rows = []
        ln = len(A.funcs[base])
        for y in cand:
            if y not in B.funcs:
                continue
            lb = len(B.funcs[y])
            if lb > ln * 2 + 8 or ln > lb * 2 + 8:
                continue
            js = M.wjaccard(toks, fb[y][0])
            rows.append((js + 0.05 * min(votes.get(y, 0), 6), js, votes.get(y, 0), y, lb))
        rows.sort(reverse=True)
        for sc, js, v, y, lb in rows[:a.top]:
            note = " (already matched to %08X)" % [k for k, vv in match.items() if vv == y][0] if y in used else ""
            print("  cand %08X  len %3d  jaccard %.2f  votes %d%s" % (y, lb, js, v, note))
        if a.dis and rows:
            left = dis(A, base, a.dis, mp)
            right = dis(B, rows[0][3], a.dis)
            print("  --- disc %08X                                 --- new %08X" % (base, rows[0][3]))
            for i in range(max(len(left), len(right))):
                l = left[i] if i < len(left) else ""
                r = right[i] if i < len(right) else ""
                print("  %-58s | %s" % (l[:58], r))


if __name__ == "__main__":
    main()
