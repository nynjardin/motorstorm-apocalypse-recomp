---
name: ps3-lift
description: Lift (or relift) a decrypted PS3 title's PPU code to C++ with ps3recomp in this MotorStorm project — loader, seeded function finder, non-code filtering, ppu_lifter, optional SPU extraction — then reconfigure the port. Use when the user asks to lift/relift/recompile a title, after a ps3recomp update, after changing the function list, or when adding a new MotorStorm title.
---

# ps3-lift

Runs the ps3recomp PPU pipeline for one title through `scripts/lift_title.py`.

## Before starting

1. `game/<ID>/EBOOT.elf` must exist and start with `7F 45 4C 46`. If only `EBOOT.BIN` exists
   (magic `SCE\0`), **stop and ask the user to decrypt it** — Claude does not run decryption:
   ```powershell
   & "I:\Projets\Recomp\tools\rpcs3\rpcs3.exe" --decrypt "I:\Projets\Recomp\MotorStorm\game\<ID>\EBOOT.BIN"
   ```
2. Make sure no build of that title is running (`port\build.log` still growing, ninja/clang-cl
   processes): relifting rewrites the sources under the compiler. Check, don't assume.
3. If ps3recomp was updated (`git -C I:/Projets/Recomp/ps3recomp log -1`), a relift is required:
   generated code must match the toolkit revision.

## Run

```bash
cd /i/Projets/Recomp/MotorStorm
/i/Projets/Recomp/.venv/Scripts/python.exe scripts/lift_title.py <ID> --dry-run   # sanity check
/i/Projets/Recomp/.venv/Scripts/python.exe scripts/lift_title.py <ID> [--spu] [--chunks 64] [--jobs 12]
```

- `--skip-find` reuses `work/<ID>/ppu/functions.json` (use it after hand-editing that list).
- `--code-end 0x...` overrides the detected end of code (rarely needed: the script takes the end of
  the last SHF_EXECINSTR section).
- Takes ~1 min for Apocalypse (52k functions), ~4 min for Pacific Rift.

## Check the result

Read `work/<ID>/lift_summary.json`:
- `dropped` > 0 is normal when data follows code (Pacific Rift: 836). `clipped` should be ~0.
- `warning_lines` should be 0; otherwise grep `work/<ID>/lift.log` for `warn|error|unresolved`.
- The "largest" functions printed should be a few thousand instructions at most. A function of
  100k+ instructions is data or a missed boundary: inspect it before building.

## After lifting

- Reconfigure and rebuild the port: `port\build.bat configure` (sources are globbed, so new or
  removed chunks are only picked up by a configure). Run it in the background; it is long.
- With `--spu`, SPU images land in `work/<ID>/spu/`. Lifting them is a separate step
  (`PORT_SPU_INPUTS` in the port's CMake, or `tools/build_spu_workloads.py`), see
  `ps3recomp/templates/project/README.md`.
- Tell the user the counts (found / kept / lifted) and anything abnormal.
