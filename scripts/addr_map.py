#!/usr/bin/env python3
"""addr_map.py: map PPU function addresses of the disc EBOOT (BCES00484) to the 1.06 EBOOT (BCES00484_106).

    python scripts/addr_map.py [--out work/BCES00484_106/addr_map.json] [--query 0x0038A8D0 ...]
    python scripts/addr_map.py --load work/BCES00484_106/addr_map.json --query 0x0038A8D0   (no recompute)

The two executables are different builds (no address survives), so functions are matched by content:
  * tokens per function: trigrams of the opcode sequence (registers and immediates ignored), the C strings
    its code addresses (lis + addi/ori pairs), and its length class;
  * candidates by inverted index on the rare tokens (strings first), score = weighted Jaccard; the best
    candidate is kept when its score is high and clearly above the second one (anchor);
  * call-graph propagation: the n-th `bl` of a matched pair is matched to the n-th `bl` of the other, and
    the callers of a matched small function are matched through their own call lists, to a fixpoint.
Output: JSON {"disc_hex": {"new": hex, "how": "...", "score": s, "len": words, "len_new": words}}.
--query prints the match of the given disc addresses (an address inside a function maps by offset).
"""
import argparse, json, struct, sys, collections, math, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DISC = ROOT / "work" / "BCES00484"
NEW = ROOT / "work" / "BCES00484_106"
ELF_DISC = ROOT / "game" / "BCES00484" / "EBOOT.elf"
ELF_NEW = ROOT / "game" / "BCES00484_106" / "EBOOT.elf"


def as_int(v):
    return int(v, 16) if isinstance(v, str) else int(v)


class Image:
    def __init__(self, elf, fjson):
        d = elf.read_bytes()
        phoff = struct.unpack(">Q", d[32:40])[0]
        phentsize, phnum = struct.unpack(">HH", d[54:58])
        self.segs = []     # (va, off, fsz)
        for i in range(phnum):
            t, f, off, va, pa, fsz, msz, al = struct.unpack(">IIQQQQQQ", d[phoff + i * phentsize:phoff + i * phentsize + 56])
            if t == 1 and fsz:
                self.segs.append((va, off, fsz))
        self.d = d
        funcs = json.loads(Path(fjson).read_text())
        funcs = funcs if isinstance(funcs, list) else funcs["functions"]
        self.funcs = {}
        for fn in funcs:
            s, e = as_int(fn["start"]), as_int(fn["end"])
            self.funcs[s] = struct.unpack(">%dI" % ((e - s) // 4), self.read(s, e - s))

    def read(self, va, n):
        for sva, off, fsz in self.segs:
            if sva <= va < sva + fsz:
                return self.d[off + va - sva: off + va - sva + n]
        return b""

    def cstr(self, va):
        b = self.read(va, 96)
        if not b:
            return None
        n = b.find(b"\0")
        if n < 4:
            return None
        s = b[:n]
        if all(32 <= c < 127 or c in (9, 10, 13) for c in s):
            return s
        return None


def opkey(w):
    op = w >> 26
    if op in (19, 30, 31, 59, 60, 63, 4):
        return (op << 12) | ((w >> 1) & 0x3FF)
    if op == 18:
        return (op << 12) | (w & 3)
    if op == 16:
        return (op << 12) | ((w >> 16) & 0x3FF) | ((w & 3) << 10)
    return op << 12


def features(img, s, words):
    keys = [opkey(w) for w in words]
    toks = collections.Counter()
    for i in range(len(keys) - 2):
        toks[("t", keys[i], keys[i + 1], keys[i + 2])] += 1
    # strings: lis rA,hi ; addi/addic/ori rX,rA,lo
    regs = {}
    strs = set()
    calls = []
    for i, w in enumerate(words):
        op = w >> 26
        rt, ra = (w >> 21) & 31, (w >> 16) & 31
        imm = w & 0xFFFF
        if op == 15 and ra == 0:                       # lis
            regs[rt] = (imm << 16) & 0xFFFFFFFF
        elif op in (14, 12) and ra in regs:            # addi / addic
            v = (regs[ra] + (imm - 0x10000 if imm & 0x8000 else imm)) & 0xFFFFFFFF
            c = img.cstr(v)
            if c:
                strs.add(c)
            regs[rt] = v
        elif op == 24 and ra in regs:                  # ori (rs=rt field is the source, ra the dest)
            v = regs[rt] | imm if rt in regs else None
            if v is not None:
                c = img.cstr(v)
                if c:
                    strs.add(c)
                regs[ra] = v
        elif op == 24 and rt in regs:
            v = regs[rt] | imm
            c = img.cstr(v)
            if c:
                strs.add(c)
            regs[ra] = v
        if op == 18 and (w & 1) and not (w & 2):
            li = w & 0x03FFFFFC
            if li & 0x02000000:
                li -= 0x04000000
            calls.append((s + i * 4 + li) & 0xFFFFFFFF)
    for c in strs:
        toks[("s", c)] += 3
    return toks, calls, strs


def wjaccard(a, b):
    inter = sum(min(v, b[k]) for k, v in a.items() if k in b)
    union = sum(a.values()) + sum(b.values()) - inter
    return inter / union if union else 0.0


def build(args):
    t0 = time.time()
    A = Image(ELF_DISC, DISC / "ppu" / "functions.code.json")
    B = Image(ELF_NEW, NEW / "ppu" / "functions.code.json")
    print("functions: disc %d, new %d (%.0fs)" % (len(A.funcs), len(B.funcs), time.time() - t0))
    fa = {s: features(A, s, w) for s, w in A.funcs.items()}
    fb = {s: features(B, s, w) for s, w in B.funcs.items()}
    print("features done (%.0fs)" % (time.time() - t0))
    # inverted index on the new image: token -> functions (rare tokens only)
    idx = collections.defaultdict(list)
    for s, (toks, _, _) in fb.items():
        for k in toks:
            idx[k].append(s)
    df_cap = 40
    match = {}
    used = {}
    scores = {}

    def candidates(toks, ln):
        cnt = collections.Counter()
        for k in toks:
            lst = idx.get(k)
            if lst and len(lst) <= df_cap:
                w = 4 if k[0] == "s" else 1
                for s in lst:
                    cnt[s] += w
        return [s for s, _ in cnt.most_common(12)]

    pairs = []
    for s, (toks, calls, strs) in fa.items():
        ln = len(A.funcs[s])
        if ln < 8:
            continue
        best, second = (0.0, None), 0.0
        for c in candidates(toks, ln):
            lc = len(B.funcs[c])
            if lc > ln * 1.6 + 6 or ln > lc * 1.6 + 6:
                continue
            sc = wjaccard(toks, fb[c][0])
            if sc > best[0]:
                second, best = best[0], (sc, c)
            elif sc > second:
                second = sc
        if best[1] is not None and best[0] >= 0.6 and best[0] - second >= 0.08:
            pairs.append((best[0], s, best[1]))
    pairs.sort(reverse=True)
    for sc, s, c in pairs:
        if s in match or c in used:
            continue
        match[s] = (c, "anchor")
        used[c] = s
        scores[s] = sc
    print("anchors: %d (%.0fs)" % (len(match), time.time() - t0))

    # graph voting: neighbours already matched vote for the candidates of an unmatched function
    callers_a = collections.defaultdict(list)
    callers_b = collections.defaultdict(list)
    for s, (_, calls, _) in fa.items():
        for c in calls:
            callers_a[c].append(s)
    for s, (_, calls, _) in fb.items():
        for c in calls:
            callers_b[c].append(s)
    callees_a = {s: sorted(set(v[1])) for s, v in fa.items()}
    callees_b = {s: sorted(set(v[1])) for s, v in fb.items()}
    callers_a = {k: sorted(set(v)) for k, v in callers_a.items()}
    callers_b = {k: sorted(set(v)) for k, v in callers_b.items()}

    def lens_ok(x, y):
        la, lb = len(A.funcs[x]), len(B.funcs[y])
        return abs(la - lb) <= max(6, la // 3)

    def deg_ok(x, y):
        na, nb = len(callers_a.get(x, [])), len(callers_b.get(y, []))
        return abs(na - nb) <= max(2, int(0.3 * max(na, nb)))

    rounds = 0
    while rounds < 25:
        rounds += 1
        votes = collections.defaultdict(collections.Counter)
        for x in A.funcs:
            if x in match:
                continue
            v = votes[x]
            for c in callers_a.get(x, []):
                m = match.get(c)
                if m:
                    for y in callees_b.get(m[0], []):
                        v[y] += 1
            for c in callees_a.get(x, []):
                m = match.get(c)
                if m:
                    for y in callers_b.get(m[0], []):
                        v[y] += 1
        newpairs = []
        for x, v in votes.items():
            if not v:
                continue
            nx = len(callers_a.get(x, [])) + len(callees_a.get(x, []))
            best = []
            for y, n in v.most_common(8):
                if y in used or y not in B.funcs or not lens_ok(x, y) or not deg_ok(x, y):
                    continue
                ny = len(callers_b.get(y, [])) + len(callees_b.get(y, []))
                vs = n / max(nx, ny, 1)
                js = wjaccard(fa[x][0], fb[y][0])
                best.append((0.6 * vs + 0.4 * js, vs, y))
            if not best:
                continue
            best.sort(reverse=True)
            sc, vs, y = best[0]
            sec = best[1][0] if len(best) > 1 else 0.0
            if sc >= 0.45 and sc - sec >= 0.08 and (vs >= 0.4 or len(A.funcs[x]) >= 10):
                newpairs.append((sc, x, y))
        newpairs.sort(reverse=True)
        added = 0
        for sc, x, y in newpairs:
            if x in match or y in used:
                continue
            match[x] = (y, "vote")
            used[y] = x
            scores[x] = sc
            added += 1
        print("  round %d: +%d" % (rounds, added))
        if not added:
            break
    print("after voting: %d, %d rounds (%.0fs)" % (len(match), rounds, time.time() - t0))

    # ---- order-preserving alignment: the linker keeps the order of the translation units, so between
    # two consistent anchors the functions of both images are the same sequence, give or take a few.
    def chain_of(pairs):
        """Longest increasing subsequence of new addresses over disc order: [(d, n), ...]."""
        import bisect as _b
        pairs = sorted(pairs)
        tails, idxs, prev = [], [], [-1] * len(pairs)
        for i, (d, n) in enumerate(pairs):
            k = _b.bisect_left(tails, n)
            if k == len(tails):
                tails.append(n); idxs.append(i)
            else:
                tails[k] = n; idxs[k] = i
            prev[i] = idxs[k - 1] if k else -1
        out, i = [], idxs[-1] if idxs else -1
        while i >= 0:
            out.append(pairs[i]); i = prev[i]
        return out[::-1]

    ka = sorted(A.funcs)
    kb = sorted(B.funcs)
    opk = {}

    def opseq(img, key, x):
        r = opk.get((key, x))
        if r is None:
            r = tuple(opkey(w) for w in img.funcs[x])
            opk[(key, x)] = r
        return r

    def sim(x, y):
        lx, ly = len(A.funcs[x]), len(B.funcs[y])
        if min(lx, ly) <= 3:
            base = 1.0 if opseq(A, "a", x) == opseq(B, "b", y) else 0.0
        else:
            base = wjaccard(fa[x][0], fb[y][0])
        return base * (1.0 - min(0.5, abs(lx - ly) / max(lx, ly)))

    import bisect
    for rnd in range(4):
        remaining = [(d, n[0]) for d, n in match.items() if d not in chained]  if rnd else [(d, n[0]) for d, n in match.items()]
        if rnd == 0:
            chained = set()
        chain = chain_of(remaining)
        for d, n in chain:
            chained.add(d)
        if len(chain) < 20:
            break
        bounds = [(0, 0)] + chain + [(0xFFFFFFFF, 0xFFFFFFFF)]
        added = 0
        for (d1, n1), (d2, n2) in zip(bounds, bounds[1:]):
            D = [x for x in ka[bisect.bisect_right(ka, d1):bisect.bisect_left(ka, d2)] if x not in match]
            N = [y for y in kb[bisect.bisect_right(kb, n1):bisect.bisect_left(kb, n2)] if y not in used]
            if not D or not N or len(D) * len(N) > 4_000_000:
                continue
            # Needleman-Wunsch, gap cost 0.15
            gp = 0.15
            R, C = len(D), len(N)
            S = [[0.0] * (C + 1) for _ in range(R + 1)]
            T = [[0] * (C + 1) for _ in range(R + 1)]
            for i in range(1, R + 1):
                S[i][0] = -gp * i; T[i][0] = 1
            for j in range(1, C + 1):
                S[0][j] = -gp * j; T[0][j] = 2
            for i in range(1, R + 1):
                Di = D[i - 1]
                Si, Sp, Ti = S[i], S[i - 1], T[i]
                for j in range(1, C + 1):
                    sc = sim(Di, N[j - 1])
                    diag = Sp[j - 1] + (sc if sc >= 0.3 else -0.6)
                    up, left = Sp[j] - gp, Si[j - 1] - gp
                    if diag >= up and diag >= left:
                        Si[j] = diag; Ti[j] = 0
                    elif up >= left:
                        Si[j] = up; Ti[j] = 1
                    else:
                        Si[j] = left; Ti[j] = 2
            i, j = R, C
            while i > 0 or j > 0:
                t = T[i][j]
                if i > 0 and j > 0 and t == 0:
                    sc = sim(D[i - 1], N[j - 1])
                    if sc >= 0.3:
                        match[D[i - 1]] = (N[j - 1], "align")
                        used[N[j - 1]] = D[i - 1]
                        scores[D[i - 1]] = sc
                        added += 1
                    i -= 1; j -= 1
                elif i > 0 and (t == 1 or j == 0):
                    i -= 1
                else:
                    j -= 1
        print("  alignment pass %d: chain %d anchors, +%d" % (rnd, len(chain), added))
    print("after alignment: %d (%.0fs)" % (len(match), time.time() - t0))
    cov_w = sum(len(A.funcs[s]) for s in match)
    tot_w = sum(len(w) for w in A.funcs.values())
    print("coverage: %.1f%% of disc functions, %.1f%% of disc instructions" %
          (100 * len(match) / len(A.funcs), 100 * cov_w / tot_w))
    out = {"0x%08X" % s: {"new": "0x%08X" % n, "how": how, "score": round(scores.get(s, 0), 3),
                          "len": len(A.funcs[s]), "len_new": len(B.funcs[n])}
           for s, (n, how) in sorted(match.items())}
    Path(args.out).write_text(json.dumps(out, indent=0))
    print("written", args.out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(NEW / "addr_map.json"))
    ap.add_argument("--load", default=None)
    ap.add_argument("--query", nargs="*", default=[])
    a = ap.parse_args()
    m = json.loads(Path(a.load).read_text()) if a.load else build(a)
    starts = sorted(int(k, 16) for k in m)
    funcs_a = json.loads((DISC / "ppu" / "functions.code.json").read_text())
    bounds = sorted((as_int(f["start"]), as_int(f["end"])) for f in funcs_a)
    import bisect
    keys = [b[0] for b in bounds]
    for q in a.query:
        s = int(q, 0)
        i = bisect.bisect_right(keys, s) - 1
        base, end = bounds[i]
        k = "0x%08X" % base
        if k in m:
            e = m[k]
            print("%s (fn %08X +%x len %d) -> %s +%x [%s %.2f] len %d" %
                  (q, base, s - base, (end - base) // 4, e["new"], s - base, e["how"], e["score"], e["len_new"]))
        else:
            print("%s (fn %08X len %d): NO MATCH" % (q, base, (end - base) // 4))


if __name__ == "__main__":
    main()
