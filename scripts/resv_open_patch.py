"""Add the open-reservation notes to ALREADY lifted PPU code, without a relift.

    I:/Projets/Recomp/.venv/Scripts/python.exe scripts/resv_open_patch.py [--dry-run] [--backup DIR]

Same text change as `ppu_lifter.py --resv-open-count` (upstream ps3recomp
585c8efa): every lwarx/ldarx calls ppu_resv_open_note() before it reads, and the
header declares it. Needed for PS3RECOMP_PPU_RESV_OPEN_COUNT=1 (reservation
breaks skip the scan of every context). Done in place because the lifted files
carry hand edits a relift would lose; lift_title.py / lift_libsre.py pass the
lifter option, so a future relift gives the same result.

Targets: work/BCES00484/recomp (ppu_recomp.h + .cpp) and
work/firmware/libsre/recomp (libsre_recomp.h/.c). Idempotent. Every file that
changes is copied to --backup first (default E:/ms_perf/backup_resv_open_patch).
After it: port\\build.bat (the header changes, so every lifted TU rebuilds).
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [(ROOT / "work/BCES00484/recomp", "ppu_recomp.h", "ppu_recomp_*.cpp", "func_"),
           (ROOT / "work/firmware/libsre/recomp", "libsre_recomp.h", "libsre_recomp.c", "libsre_func_")]

NOTE = "if (g_resv_open_active) ppu_resv_open_note(ctx, (uint32_t)ea); "
# Exactly what the lifter emits for lwarx / ldarx.
LOAD_RESERVE = re.compile(
    r"(\{ uint64_t ea = ctx->gpr\[\d+\](?: \+ ctx->gpr\[\d+\])?; )"
    r"(ctx->gpr\[\d+\] = vm_read(?:32|64)\(ea\); ctx->reserve_addr = \(uint32_t\)ea; )")
DECL = ('#ifdef __cplusplus\nextern "C" {\n#endif\n'
        "/* --resv-open-count: see ppu_resv_open_note in the runtime. */\n"
        "extern int g_resv_open_active;\n"
        "void ppu_resv_open_note(ppu_context* ctx, uint32_t ea);\n"
        "#ifdef __cplusplus\n}\n#endif\n")


def read(p):
    with open(p, "r", encoding="latin-1", newline="") as f:
        return f.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--backup", default="E:/ms_perf/backup_resv_open_patch")
    a = ap.parse_args()
    changes = []          # (path, new text)
    total = 0
    for d, header, srcs, prefix in TARGETS:
        h = d / header
        text = read(h)
        if "ppu_resv_open_note" not in text:
            m = re.search(r"^void %s[0-9A-F]{8}\(ppu_context\* ctx\);" % prefix, text, re.M)
            if not m:
                sys.exit(f"{h}: no forward declaration found")
            nl = "\r\n" if "\r\n" in text[:4096] else "\n"
            changes.append((h, text[:m.start()] + DECL.replace("\n", nl) + text[m.start():]))
        n_dir = 0
        for src in sorted(d.glob(srcs)):
            text = read(src)
            left = len(re.findall(r"ctx->reserve_addr = \(uint32_t\)ea; ctx->reserve_value", text))
            done = text.count(NOTE)
            new, n = LOAD_RESERVE.subn(lambda m: m.group(1) + NOTE + m.group(2), text)
            if n + done != left:
                sys.exit(f"{src}: {left} load-reserves, {done} already noted, {n} matched: "
                         "an unexpected form, nothing written")
            if n:
                changes.append((src, new))
            n_dir += n
        print(f"{d}: {n_dir} load-reserve(s) to note")
        total += n_dir
    print(f"{len(changes)} file(s) to change, {total} note(s)")
    if a.dry_run or not changes:
        return
    for p, new in changes:
        dst = Path(a.backup) / p.relative_to(ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            shutil.copy2(p, dst)
        with open(p, "w", encoding="latin-1", newline="") as f:
            f.write(new)
    print(f"written; originals in {a.backup}")


if __name__ == "__main__":
    main()
