---
name: hle-stub
description: Add or fix an HLE answer for a PS3 library function the MotorStorm port needs (an "[hle] unresolved NID" line, a toolkit function that answers wrongly for this title, a firmware call to replace) as a port override in port/hle_overrides.cpp, or change what a GAME function does with an entry hook. Use when the log shows unresolved NIDs, when a toolkit HLE behaves differently from the console for this title, or when a game function must be answered by the port (network, community server).
---

# hle-stub

Two different tools, do not confuse them:

| What must change | Tool | Where |
|---|---|---|
| A **library import** (cell*, sce*, sys_*: called through a NID) | port override | `port/hle_overrides.cpp` |
| A **function of the game itself** (lifted code calls it directly) | entry hook | `port/func_hooks.txt`, `scripts/func_hooks.py`, `port/net_hooks.cpp` |

Port-specific behaviour goes in `port/`, never in the toolkit (a toolkit change = a numbered
local patch, `docs/toolkit-patches.md`). Background: `docs/hle.md`.

## A. Library import

1. **Find it.** `grep -a "unresolved NID" port/run.log | sort | uniq -c`. Name the NID:
   `python scripts/nid_names.py --all | grep -i <hex>` (names are hashed from the strings of
   `tools/rpcs3/rpcs3.exe`: SHA1(name + suffix), first four bytes little-endian). A named import
   that misbehaves: read its toolkit source under `I:/Projets/Recomp/ps3recomp/libs/`.
2. **Know what the console answers.** RPCS3's source for that function is the reference
   (`tools/rpcs3` is the binary only: read the function on GitHub through the `web-fetch`
   agent), then the title's own use: `scripts/strref.py --callers func_<stub>` (the stub address
   is in `work/BCES00484/ppu/EBOOT.imports.json`) and the lifted caller.
3. **Write the override** in `port/hle_overrides.cpp`, registered in the list at the end of the
   file with `ps3_hle_register_ctx(0x<NID>u, "<name>", fn)` (a ctx handler wins over the
   generated NID table):
   - arguments: `c->gpr[3]`..`c->gpr[10]` (32-bit pointers: cast to `uint32_t`), floats in
     `c->fpr[1]`.. (the toolkit's generic dispatch never passes them: a float argument is a
     reason for a port override), more arguments on the guest stack;
   - result: `c->gpr[3]` (an error code is a negative 32-bit value: sign-extend it);
   - guest memory: `vm_read8/16/32/64`, `vm_write*` (big-endian handled); port-owned guest
     scratch memory starts at `0x02040000`;
   - **never** take `spu_lockline_lock()` around `vm_write*` (deadlock: the coherent stores take
     the same non-recursive lock);
   - log the first few calls only (`static std::atomic<int> n; if (n.fetch_add(1) < 3) ...`),
     with a `[port]` prefix; give a behaviour switch an env variable and put its default in
     `port\run.bat`, `run_lan.bat` AND `port\portable.cpp` (the three repeat each other).
4. **Network / PSN**: the answer "offline" lives in ONE place (`port_cellNetCtlGetState`, and
   `port/net_hooks.cpp` for the title's own online code). Never scatter such answers.

## B. Function of the game

1. Find the function: `scripts/strref.py "<a string it uses>"`, `--callers`, the title's debug
   log (`PORT_GAME_LOG=1`), a live object (`scripts/guest_find_obj.py`).
2. Add its address to `port/func_hooks.txt` (one `0x........  # comment` per line), write
   `int port_hook_<ADDR>(ppu_context* c)` in `port/net_hooks.cpp`: return 0 = the game's function
   runs (arguments may be changed in `c->gpr[]`), nonzero = replaced, result in `c->gpr[3]`.
3. `python scripts/func_hooks.py` (inserts the call at the top of the lifted function; **redo
   after any PPU relift**), then build.
4. To call a game function from a hook: save `*c`, set the arguments, call `func_X(c)`, drain
   `g_trampoline_fn`, put `*c` back (`save_profile_now` in `net_hooks.cpp`). Only from a guest
   thread, at a call boundary.

## Build and check

`cmd //c "port\\build.bat" 2>&1 | grep -a "error\|FAILED"` (the link fails while a game runs).
Then one run and the proof in the log: the override's own line, and the unresolved line gone.
Record it: a line in `docs/hle.md` (override) or `docs/reseau.md` (network hook), the journal.
