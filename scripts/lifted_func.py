"""Print one lifted PPU function in a compact, readable form.

    python scripts/lifted_func.py func_009F3A14 [func_... ...] [--title BCES00484] [--raw]

Finds `void func_XXXXXXXX(ppu_context* ctx)` in work/<title>/recomp/ppu_recomp_*.cpp and prints
its body with the lifter's noise folded: `ctx->gpr[n]` -> rN, the compare blocks -> `cr0 = cmp
r3, 0` (signed) / `cmpl` (unsigned) with the CR field, the carry adds -> `r3 = r4 + 0x10`, the
branch tests -> `if lt/gt/eq/ge/le/ne(crN)`, saves/restores of callee-saved registers and TOC
reloads dropped. Syscalls keep `lv2_syscall` (the number is the r11 set just before).
"""
import argparse, glob, os, re, sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "work")


def find(title, name):
    pat = ("void %s(ppu_context* ctx) {" % name).encode()
    for p in sorted(glob.glob(os.path.join(ROOT, title, "recomp", "ppu_recomp_*.cpp"))):
        data = open(p, "rb").read()
        i = data.find(b"\n" + pat)
        if i < 0:
            continue
        m = re.compile(rb"\n}\r?\n").search(data, i)
        j = m.start() if m else len(data) - 2
        return p, data[i + 1:j + 2].decode("latin-1").replace("\r", "")
    return None, None


CMP = re.compile(r"\{ (u?)int64_t a = \(u?int(32|64)_t\)(.+?); u?int64_t b = \(u?int(?:32|64)_t\)(.+?); "
                 r"uint32_t cr_val.*?<< (\d+)\)\) \| \(cr_val << \d+\); \}")
ADD = re.compile(r"\{ uint64_t _a = (\w+); uint64_t _r = _a \+ \(uint64_t\)\(int64_t\)\((.+?)\); (\w+) = _r;.*\}")
ADDC = re.compile(r"\{ uint64_t result = (\w+) \+ (\w+); xer = .*?; (\w+) = result; \}")
SUBF = re.compile(r"\{ uint64_t result = ~(\w+) \+ (\w+) \+ 1; xer = .*?; (\w+) = result; \}")
BR = re.compile(r"\(\(cr >> (\d+)\) & 1\)")
NAMES = {0: "lt", 1: "gt", 2: "eq", 3: "so"}
NEG = {"lt": "ge", "gt": "le", "eq": "ne", "so": "ns"}


def branch(m, neg):
    bit = 31 - int(m.group(1))
    n = NAMES[bit % 4]
    return "%s(cr%d)" % (NEG[n] if neg else n, bit // 4)


def compact(text):
    out = []
    for ln in text.splitlines():
        s = ln.strip()
        s = re.sub(r"ctx->gpr\[(\d+)\]", r"r\1", s).replace("ctx->", "")
        s = s.replace(" DRAIN_TRAMPOLINE(ctx);", "").replace("(int64_t)(int32_t)", "")
        if (not s or "TOCFIX" in s or s == "/* nop */;" or "_cs_" in s or s == "PPU_MM_SNAP"
                or s == "vm_write64(r1 + 0x28, r2);"):
            continue
        m = CMP.match(s)
        if m:
            fld = (28 - int(m.group(5))) // 4
            s = "cr%d = %s%s %s, %s" % (fld, "cmpl" if m.group(1) else "cmp",
                                        "w" if m.group(2) == "32" else "d", m.group(3), m.group(4))
        s = ADD.sub(lambda m: "%s = %s + %s;" % (m.group(3), m.group(1), m.group(2)), s)
        s = ADDC.sub(lambda m: "%s = %s + %s;" % (m.group(3), m.group(1), m.group(2)), s)
        s = SUBF.sub(lambda m: "%s = %s - %s;" % (m.group(3), m.group(2), m.group(1)), s)
        s = re.sub(r"\(!" + BR.pattern + r"\)", lambda m: branch(m, True), s)
        s = BR.sub(lambda m: branch(m, False), s)
        s = s.replace("if (1) { ps3_indirect_call(ctx); }", "call [ctr]")
        out.append(s if s.startswith(("loc_", "void", "}")) else "    " + s)
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("funcs", nargs="+")
    ap.add_argument("--title", default="BCES00484")
    ap.add_argument("--raw", action="store_true")
    a = ap.parse_args()
    for f in a.funcs:
        if not f.startswith("func_"):
            f = "func_" + f.upper().replace("0X", "").rjust(8, "0")
        p, text = find(a.title, f)
        if not text:
            print("%s: not found" % f)
            continue
        print("// %s" % os.path.basename(p))
        print(text if a.raw else compact(text))
        print()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
