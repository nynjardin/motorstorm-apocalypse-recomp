"""Relocate and lift the firmware SPURS/Sync library (libsre.prx) for the port.

    I:/Projets/Recomp/.venv/Scripts/python.exe scripts/lift_libsre.py [--prx PATH] [--base 0x02000000]

Input: game/firmware/libsre.prx, decrypted by the user from their own firmware
(rpcs3 --installfw PS3UPDAT.PUP, then rpcs3 --decrypt dev_flash/sys/external/libsre.sprx).
Output: work/firmware/libsre/
    libsre_image.bin              relocated image, loaded at --base by port/libsre_lle.cpp
    libsre_{functions,exports,imports}.json, libsre_hle_stubs.json
    recomp/libsre_recomp.{h,c}    lifted C (compiled as C++ by port/CMakeLists.txt)

Firmware-derived files: local only, never distribute or commit them.

Post-lift patch: the functions in REPLACED are renamed `..._lle` so the port
defines the symbol: the taskset scheduler is HLE, so lookups and signals must
reach it, not the real kernel's bookkeeping.
After a relift: port\\build.bat configure.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT.parent / "ps3recomp" / "tools"
PY = sys.executable

# Functions whose lifted body is replaced by a port definition (address -> why).
# _cellSpursSendSignal (cellSpurs 0xE0A6DBE4): HLE taskset scheduler owns signals.
# cellSpursLookUpTasksetAddress (cellSpurs 0x4CCE88A9): HLE tasksets are not
# SPURS workloads (no wklInfo entry, tasks see wid 0), so the port resolves them.
REPLACED = {0x020125D8: "_cellSpursSendSignal -> HLE (port/libsre_lle.cpp)",
            0x020134B8: "cellSpursLookUpTasksetAddress -> port (port/libsre_lle.cpp)"}


def run(cmd):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], cwd=TOOLS, check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prx", default=str(ROOT / "game/firmware/libsre.prx"))
    ap.add_argument("--base", default="0x02000000")
    ap.add_argument("--out", default=str(ROOT / "work/firmware/libsre"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    fwd = lambda p: str(p).replace("\\", "/")

    run([PY, "lift_prx.py", fwd(a.prx), "--base", a.base, "--output", fwd(out)])

    exp = json.loads((out / "libsre_exports.json").read_text())
    toc = exp["toc"]
    if int(a.base, 16) != 0x02000000:
        sys.exit("REPLACED addresses assume --base 0x02000000; update them for another base")

    imports = json.loads((out / "libsre_imports.json").read_text())
    stubs = [{"library": lib, "nid": nid.lower(), "stub": hex(int(slot, 16))}
             for lib, m in imports.items() for nid, slot in m.items()]
    (out / "libsre_hle_stubs.json").write_text(json.dumps(stubs, indent=1))

    recomp = out / "recomp"
    run([PY, "ppu_lifter.py", fwd(out / "libsre_image.bin"), "--raw", "--base", a.base, "--toc", toc,
         "--functions", fwd(out / "libsre_functions.json"),
         "--hle-stubs", fwd(out / "libsre_hle_stubs.json"),
         "--symbol-prefix", "libsre_", "--header-name", "libsre_recomp.h",
         "--source-name", "libsre_recomp.c", "--single-file", "--jobs", "8",
         "--resv-open-count",   # PS3RECOMP_PPU_RESV_OPEN_COUNT (upstream 585c8efa)
         "--output", fwd(recomp)])

    src = recomp / "libsre_recomp.c"
    text = src.read_text(encoding="latin-1")
    for addr, why in REPLACED.items():
        name = "libsre_func_%08X" % addr
        pat = re.compile(r"^void %s\(ppu_context\* ctx\) \{" % name, re.M)
        text, n = pat.subn("/* %s */\nvoid %s_lle(ppu_context* ctx) {" % (why, name), text)
        if n != 1:
            sys.exit(f"patch {name}: expected 1 definition, found {n}")
    src.write_text(text, encoding="latin-1")
    print(f"libsre lifted (toc {toc}), {len(REPLACED)} function(s) handed to the port")


if __name__ == "__main__":
    main()
