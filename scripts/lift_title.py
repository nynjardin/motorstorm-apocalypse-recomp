#!/usr/bin/env python3
"""Run the full ps3recomp PPU pipeline for one decrypted title.

    loader -> find_functions (seeded) -> drop non-code ranges -> ppu_lifter
    (+ optional SPU image extraction)

Usage (from anywhere, with the project venv):
    I:/Projets/Recomp/.venv/Scripts/python.exe scripts/lift_title.py BCES00484
    ... --chunks 64 --jobs 12 --spu --skip-find

Inputs : game/<TITLE>/EBOOT.elf           (decrypted by the user with RPCS3)
Outputs: work/<TITLE>/ppu/                (loader json, functions.json, functions.code.json)
         work/<TITLE>/recomp/             (ppu_recomp.h + ppu_recomp_NNN.cpp)
         work/<TITLE>/spu/                (with --spu)
         work/<TITLE>/lift.log, work/<TITLE>/lift_summary.json
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import subprocess
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent          # i:/Projets/Recomp/MotorStorm
PS3RECOMP = PROJECT.parent / "ps3recomp"
TOOLS = PS3RECOMP / "tools"
PY = PROJECT.parent / ".venv" / "Scripts" / "python.exe"
SHF_EXECINSTR = 0x4


def exec_range(elf: Path) -> tuple[int, int]:
    """[start, end) covering every SHF_EXECINSTR section (names are stripped on retail)."""
    d = elf.read_bytes()
    if d[:4] != b"\x7fELF":
        sys.exit(f"{elf} is not a decrypted ELF (magic {d[:4]!r}); decrypt EBOOT.BIN with RPCS3 first")
    shoff, = struct.unpack(">Q", d[0x28:0x30])
    shes, shn, _ = struct.unpack(">HHH", d[0x3A:0x40])
    lo, hi = None, 0
    for i in range(shn):
        _, _, flags, addr, _, size, *_ = struct.unpack(">IIQQQQIIQQ", d[shoff + i * shes:shoff + i * shes + 64])
        if addr and flags & SHF_EXECINSTR:
            lo = addr if lo is None else min(lo, addr)
            hi = max(hi, addr + size)
    if lo is None:
        sys.exit("no executable section headers found; pass --code-end manually")
    return lo, hi


def run(step: str, args: list[str], log) -> None:
    t = time.time()
    print(f"[{step}] ...", flush=True)
    log.write(f"\n===== {step}: {' '.join(args)}\n")
    log.flush()
    # cwd=tools and no -I: the tools import their siblings (spu_elf, nid_database...).
    r = subprocess.run([str(PY), *args], cwd=TOOLS, stdout=log, stderr=subprocess.STDOUT)
    if r.returncode:
        sys.exit(f"[{step}] failed (exit {r.returncode}); see {log.name}")
    print(f"[{step}] ok ({time.time() - t:.0f}s)", flush=True)


def as_int(v) -> int:
    return int(v, 16) if isinstance(v, str) else int(v)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("title", help="title ID folder under game/, e.g. BCES00484")
    ap.add_argument("--chunks", type=int, default=64)
    ap.add_argument("--jobs", type=int, default=12)
    ap.add_argument("--code-end", type=lambda s: int(s, 0), help="override detected end of code")
    ap.add_argument("--skip-find", action="store_true", help="reuse existing ppu/functions.json")
    ap.add_argument("--spu", action="store_true", help="also extract embedded SPU images")
    ap.add_argument("--dry-run", action="store_true",
                    help="only report code range and function filtering; write nothing")
    a = ap.parse_args()

    elf = PROJECT / "game" / a.title / "EBOOT.elf"
    if not elf.exists():
        sys.exit(f"missing {elf}")
    work = PROJECT / "work" / a.title
    ppu, recomp = work / "ppu", work / "recomp"
    ppu.mkdir(parents=True, exist_ok=True)
    recomp.mkdir(parents=True, exist_ok=True)

    lo, hi = exec_range(elf)
    code_end = a.code_end or hi
    print(f"{a.title}: code {lo:#x}..{hi:#x}, --code-end {code_end:#x}")
    if a.dry_run:
        funcs = json.loads((ppu / "functions.json").read_text())
        funcs = funcs if isinstance(funcs, list) else funcs["functions"]
        past = sum(1 for f in funcs if as_int(f["start"]) >= code_end)
        print(f"dry run: {len(funcs)} functions in ppu/functions.json, {past} would be dropped")
        return

    with open(work / "lift.log", "w", encoding="utf-8", errors="replace") as log:
        if not a.skip_find:
            run("loader", ["ppu_loader.py", elf.as_posix(), "-o", ppu.as_posix()], log)
            run("find_functions", ["find_functions.py", elf.as_posix(),
                                   "--seed-json", (ppu / "EBOOT.functions.json").as_posix(),
                                   "--output", (ppu / "functions.json").as_posix()], log)

        funcs = json.loads((ppu / "functions.json").read_text())
        funcs = funcs if isinstance(funcs, list) else funcs["functions"]
        kept = [f for f in funcs if as_int(f["start"]) < code_end]
        clipped = 0
        for f in kept:
            if as_int(f["end"]) > code_end:
                f["end"] = hex(code_end)
                clipped += 1
        (ppu / "functions.code.json").write_text(json.dumps(kept))
        dropped = len(funcs) - len(kept)
        biggest = sorted(kept, key=lambda f: as_int(f["end"]) - as_int(f["start"]))[-3:]
        print(f"functions: {len(funcs)} found, {dropped} dropped past code end, {clipped} clipped")
        print("largest:", [(f["start"], (as_int(f["end"]) - as_int(f["start"])) // 4) for f in biggest])

        run("ppu_lifter", ["ppu_lifter.py", elf.as_posix(),
                           "--functions", (ppu / "functions.code.json").as_posix(),
                           "--hle-stubs", (ppu / "EBOOT.imports.json").as_posix(),
                           "--code-end", hex(code_end),
                           "--resv-open-count",   # PS3RECOMP_PPU_RESV_OPEN_COUNT (upstream 585c8efa)
                           "--chunks", str(a.chunks), "-j", str(a.jobs),
                           "--output", recomp.as_posix()], log)
        if a.spu:
            run("extract_spu", ["extract_spu_images.py", elf.as_posix(),
                                "--output", (work / "spu").as_posix()], log)

    text = (work / "lift.log").read_text(encoding="utf-8", errors="replace")
    lifted = next((l.split()[0] for l in text.splitlines() if "functions lifted" in l), "?")
    warnings = sum(1 for l in text.splitlines() if "warn" in l.lower() or "error" in l.lower())
    summary = {"title": a.title, "code_start": hex(lo), "code_end": hex(code_end),
               "functions_found": len(funcs), "functions_kept": len(kept),
               "dropped": dropped, "clipped": clipped, "functions_lifted": lifted,
               "warning_lines": warnings, "chunks": a.chunks}
    (work / "lift_summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
