"""Main-thread sample shares by category, from `samp_resolve.py` output on stdin.

    python scripts/samp_resolve.py --rvas <file> --map <map> | python scripts/samp_cats.py [label]

Categories: waits (usleep, ntdll, kernel), lifted code (func_*), guest-memory accessors
(vm_*_mm and the out-of-line vm_read/vm_write), coherence / reservations, indirect calls, VMX
helpers, other runtime. Shares of all samples and of the samples outside waits (the CPU the
thread really spends). Written 2026-11-24 for the register-local lift (toolkit patch #58).
"""
import re
import sys

label = sys.argv[1] if len(sys.argv) > 1 else ""
cat, tot, top = {}, 0, []
for line in sys.stdin:
    m = re.match(r"\s*([\d.]+)%\s+(\d+)\s+(.*)", line)
    if not m:
        continue
    n, s = int(m.group(2)), m.group(3)
    tot += n
    if "func_" in s:
        k = "lifted func_*"
    elif re.search(r"vm_(read|write|raw|mm)", s):
        k = "memory accessors"
    elif re.search(r"usleep|ntdll|KERNEL|win32u|kernelbase", s, re.I):
        k = "waits"
    elif re.search(r"coh|resv|lockline|stwcx|stdcx", s):
        k = "coherence / reservations"
    elif re.search(r"indirect|lookup|icall", s):
        k = "indirect calls"
    elif "vmx_" in s:
        k = "vmx helpers"
    else:
        k = "other runtime"
        top.append((n, s))
    cat[k] = cat.get(k, 0) + n
work = tot - cat.get("waits", 0)
print(f"{label}: {tot} samples, {100 * cat.get('waits', 0) / tot:.1f} % in waits")
for k, v in sorted(cat.items(), key=lambda x: -x[1]):
    if k != "waits":
        print(f"  {100 * v / tot:5.1f} % of all  {100 * v / work:5.1f} % of work  {k}")
print("  other runtime, top:", ", ".join(f"{s.split('@')[0].lstrip('?')} {100 * n / tot:.1f}" for n, s in sorted(top, reverse=True)[:6]))
