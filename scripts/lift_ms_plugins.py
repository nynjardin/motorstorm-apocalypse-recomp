#!/usr/bin/env python3
"""Lift Multistream's runtime-loaded SPU plugin banks (MotorStorm: Apocalypse).

The Multistream mixer task (SPU image 7, spu_3f69ca9ef76f) streams a 12 KB "bank" of
position-independent codec/DSP modules into its local store at LS 0x37000 (one 0x3000-byte
GET from a heap buffer the PPU prepared) and calls into it with bisl. Without a lift that
code runs in the SPU interpreter (SPU_INTERP_UNLIFTED=1), ~40x too slow: the whole game
then waits on the audio flag 0x0153E700 (~4 mixer cycles/s, ~2 FPS).

Inputs: bank snapshots captured at run time with the overlay dump
(SPU_DUMP_OVL=<dir>,0x37000; one file per distinct content) copied to
work/BCES00484/spu_ms/ms_bank<X>.bin. Each bank is lifted at its LS address and registered
with spu_overlay_register_verified_region: keyed by the DMA source EA, and checked byte for
byte against the lifted code at the first dispatch after each load, so a different bank at
that EA falls back to the interpreter instead of running the wrong lift.

Usage (cwd anywhere):
    I:/Projets/Recomp/.venv/Scripts/python.exe scripts/lift_ms_plugins.py
then `port\\build.bat configure` (new sources).
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "..", "ps3recomp", "tools")
WORK = os.path.join(ROOT, "work", "BCES00484", "spu_ms")
PORT = os.path.join(ROOT, "port")

LOAD_LSA = 0x37000
SPAN = 0x3000

# name, DMA source EA of the bank (heap, stable across runs so far), extra function entries
# (module base+0x10 / +0x18 are the module entry stubs; the rest were seen as interpreter
# entries with SPU_INTERP_STATS), image id (unused by the lifted SPU images 1..21; 22/23
# have special meaning in the runtime).
BANKS = [
    ("ms_bankA", 0x193C0280, [0x37010, 0x37018, 0x37490, 0x37C20, 0x38230,
                              0x39810, 0x39818, 0x39B48], 30),
    ("ms_bankB", 0x193C3280, [0x37010, 0x37018, 0x37490, 0x37498, 0x38230], 31),
]

# The firmware MP3 decoder (dev_flash/sys/external/flashMP3.pic, an SPU ELF with symbols):
# Multistream keeps the file in its heap and GETs its first segment (file offset 0x100 =
# vaddr 0x80, text + rodata, then .data) into LS 0x1A900 in four 0x4000 transfers from EA
# 0x193C7600 before every decode slice -- the area is its scratch space in between, so the
# codec is reloaded hundreds of times in a race. It ran interpreted (64 % of the Multistream
# thread, itself at 95 % of a core: the stuttering race music). Found with SPU_GETLOG /
# SPU_GETLOG_WORD and scripts/ms_ls_snap.py (journal 2026-11-23). The generated C holds
# firmware bytes: local only, like everything derived from the firmware.
V106_PATCH = {"ms_bankA": [(0x2D4B, 0x37), (0x2D57, 0x39), (0x2D58, 0x39)],
              "ms_bankB": [(0x46B, 0x37), (0x477, 0x39), (0x478, 0x39), (0x14EB, 0x37), (0x14F7, 0x39), (0x14F8, 0x39)]}

MP3_PIC = os.path.join(ROOT, "..", "tools", "rpcs3", "dev_flash", "sys", "external", "flashMP3.pic")
MP3 = dict(name="ms_mp3", ea=0x193C7600, lsa=0x1A900, img=32,
           file_off=0x100, vaddr=0x80, seg_size=0xFF10, text_end=0x9430, span=0x10000)


def lift_mp3(py, out, regs):
    import struct
    d = open(MP3_PIC, "rb").read()
    m = MP3
    blob = d[m["file_off"]:m["file_off"] + m["seg_size"]]
    to_ls = lambda va: m["lsa"] + va - m["vaddr"]
    # function symbols of the ELF
    shoff, shnum = struct.unpack(">I", d[32:36])[0], struct.unpack(">H", d[48:50])[0]
    sh = [struct.unpack(">10I", d[shoff + 40 * i:shoff + 40 * i + 40]) for i in range(shnum)]
    sym = next(x for x in sh if x[1] == 2)
    entries = set()
    for i in range(sym[5] // 16):
        _, val, _, info, _, shn = struct.unpack(">IIIBBH", d[sym[4] + 16 * i:sym[4] + 16 * i + 16])
        if (info & 15) == 2 and 0 < shn < 0xFF00 and m["vaddr"] <= val < m["text_end"]:
            entries.add(to_ls(val))
    entry = to_ls(struct.unpack(">I", d[24:28])[0])
    code_end = to_ls(m["text_end"])
    words = [int.from_bytes(blob[i:i + 4], "big") for i in range(0, m["text_end"] - m["vaddr"], 4)]
    for i, w in enumerate(words):                      # first instruction after every `bi $r0`
        if w != 0x35000000:
            continue
        j = i + 1
        while j < len(words) and words[j] in (0x00200000, 0x40200000):
            j += 1
        if j < len(words) and words[j] != 0:
            entries.add(m["lsa"] + 4 * j)
    os.makedirs(WORK, exist_ok=True)
    binp = os.path.join(WORK, m["name"] + ".bin")
    elfp = os.path.join(WORK, m["name"] + ".elf")
    open(binp, "wb").write(blob)
    print(f"{m['name']}: entry 0x{entry:X}, {len(entries)} extra entries, code end 0x{code_end:X}")
    run([py, "wrap_spu_elf.py", binp, "--base", hex(m["lsa"]), "--entry", hex(entry), "--out", elfp])
    run([py, "spu_lifter.py", elfp, "--auto-functions", elfp, "--symbol-prefix", m["name"] + "_",
         "-o", os.path.join(PORT, "spu", m["name"]), "--code-end", hex(code_end),
         "--extra-funcs", ",".join(hex(e) for e in sorted(entries))])
    # verified bytes: the text only (vaddr 0x90 .. text_end); rodata and .data are not code
    t0 = 0x10
    code = blob[t0:m["text_end"] - m["vaddr"]]
    out.append(f"extern void {m['name']}_spu_recomp_register(void);")
    out.append(f"static const uint8_t {m['name']}_code[0x{len(code):X}] = {{")
    for i in range(0, len(code), 16):
        out.append("    " + ",".join(f"0x{b:02X}" for b in code[i:i + 16]) + ",")
    out.append("};")
    out.append("")
    regs.append((m["name"], m["ea"], m["img"], len(code), m["lsa"], m["span"], m["lsa"] + t0))


def run(cmd):
    print(">", " ".join(cmd))
    if subprocess.run(cmd, cwd=TOOLS).returncode != 0:
        sys.exit(f"failed: {cmd}")


def main():
    py = sys.executable
    out = []
    out.append("/* GENERATED by scripts/lift_ms_plugins.py -- Multistream plugin banks loaded at")
    out.append(" * run time into LS 0x%05X by SPU image 7. See that script. */" % LOAD_LSA)
    out.append("#include <stdint.h>")
    out.append("#include <stddef.h>")
    out.append("#include <string.h>")
    out.append("")
    out.append("typedef struct spu_context spu_context;")
    out.append("typedef struct { uint32_t lsa; uint32_t size; const uint8_t* bytes; } spu_overlay_code_segment;")
    out.append("extern void spu_begin_image(int image_id);")
    out.append("extern int spu_overlay_register_verified_region(uint32_t content_ea, uint32_t load_lsa,")
    out.append("    uint32_t span, int image_id, const spu_overlay_code_segment* code, unsigned count);")
    out.append("")
    regs = []
    for name, ea, extra, img in BANKS:
        binp = os.path.join(WORK, name + ".bin")
        elfp = os.path.join(WORK, name + ".elf")
        data = open(binp, "rb").read()
        assert len(data) == SPAN, (name, len(data))
        end = max(i for i in range(len(data)) if data[i]) + 1
        end = (end + 15) & ~15
        # Functions reached only through pointers (bisl from image 7) are invisible to the
        # call-graph scan: take the first real instruction after every `bi $r0` as an entry.
        # A string tail lifted as a "function" is never called, so a wrong guess is harmless.
        words = [int.from_bytes(data[i:i + 4], "big") for i in range(0, end, 4)]
        guessed = set()
        for i, w in enumerate(words):
            if w != 0x35000000:          # bi $r0
                continue
            j = i + 1
            while j < len(words) and words[j] in (0x00200000, 0x40200000):  # lnop / nop
                j += 1
            if j < len(words) and words[j] != 0:
                guessed.add(LOAD_LSA + 4 * j)
        entries = sorted(set(extra) | guessed)
        print(f"{name}: {len(entries)} extra entries ({len(guessed)} after bi $r0)")
        run([py, "wrap_spu_elf.py", binp, "--base", hex(LOAD_LSA), "--entry", hex(LOAD_LSA),
             "--out", elfp])
        run([py, "spu_lifter.py", elfp, "--auto-functions", elfp, "--symbol-prefix", name + "_",
             "-o", os.path.join(PORT, "spu", name),
             "--extra-funcs", ",".join(hex(e) for e in entries)])
        out.append(f"extern void {name}_spu_recomp_register(void);")
        out.append(f"static const uint8_t {name}_code[0x{end:X}] = {{")
        for i in range(0, end, 16):
            out.append("    " + ",".join(f"0x{b:02X}" for b in data[i:i + 16]) + ",")
        out.append("};")
        out.append("")
        regs.append((name, ea, img, end, LOAD_LSA, end, LOAD_LSA))
    if os.path.exists(MP3_PIC):
        lift_mp3(py, out, regs)
    else:
        print("no flashMP3.pic (dev_flash): MP3 decoder left to the interpreter")
    out.append("#ifdef __cplusplus")
    out.append('extern "C"')
    out.append("#endif")
    out.append("void port_register_ms_overlays(void)")
    out.append("{")
    for name, ea, img, end, lsa, span, code_lsa in regs:
        out.append(f"    spu_begin_image({img}); {name}_spu_recomp_register();")
        out.append(f"    {{ static const spu_overlay_code_segment seg = {{ 0x{code_lsa:X}, 0x{end:X}, {name}_code }};")
        out.append(f"      spu_overlay_register_verified_region(0x{ea:08X}u, 0x{lsa:X}, 0x{span:X}, {img}, &seg, 1);")
        # the 1.06 EBOOT: same code, heap 0x10A700 lower (found with SPU_DUMP_OVL; the MP3 buffer is flashMP3.pic);
        # only the SDK version string inside the banks differs (350 / Rev 3420 -> 370 / Rev 3499), patched in a copy
        # because the verification is byte for byte
        out.append("#ifdef PORT_V106")
        pats = " ".join("c[0x%X]=0x%02X;" % x for x in V106_PATCH.get(name, []))
        out.append("      { static uint8_t c[0x%X]; static spu_overlay_code_segment s106;" % end)
        out.append("        memcpy(c, %s_code, sizeof c); %s s106.lsa = seg.lsa; s106.size = seg.size; s106.bytes = c;" % (name, pats))
        out.append(f"        spu_overlay_register_verified_region(0x{ea - 0x10A700:08X}u, 0x{lsa:X}, 0x{span:X}, {img}, &s106, 1); }}")
        out.append("#endif")
        out.append("    }")
    out.append("    spu_begin_image(0);")
    out.append("}")
    out.append("")
    out.append("__attribute__((constructor)) static void port_register_ms_overlays_ctor(void)")
    out.append("{")
    out.append("    port_register_ms_overlays();")
    out.append("}")
    dst = os.path.join(PORT, "spu_ms_overlays.c")
    open(dst, "w", newline="\n").write("\n".join(out) + "\n")
    print("Wrote", dst)


if __name__ == "__main__":
    main()
