---
name: crash-triage
description: Triage a freeze, an endless loading, a hang or a wrong-data bug of the MotorStorm port with the game LEFT RUNNING - which guest thread is stuck where, what data it is looking at, which game function produced it. Use when a run freezes (window title FPS unchanged 10 s), a loading never ends, the log shows HOTREAD / null-read / BLOCKED lines, or the user reports a freeze or a crash.
---

# crash-triage

A frozen game is evidence: **do not stop it**. Everything below works from outside, on the
live process (`MS_PID=<pid>` picks one instance when several run). Tools: `scripts/`, how-to:
`docs/debugging.md` ("Freezes and hangs"). Python: `I:/Projets/Recomp/.venv/Scripts/python.exe`.

## 1. Is it frozen, and what does the log say

- Window title (`Get-Process MotorStormApocalypse | Select MainWindowTitle`): FPS and frame
  number unchanged 10 s = frozen. FPS still moving with `draws: 7` for minutes = the loading
  screen animates while the MAIN thread is stuck (the title prints `TOO LONG LOADING!!!!` with
  `PORT_GAME_LOG=1`).
- Last lines of `port\run.log` (`run_p<k>.log`), then grep the whole log:
  `HOTREAD|null-read|null-write|BLOCKED|sleeping .* in WAIT_SIGNAL|PUTLLC: a store|FATAL|MISS fp=`.
  `[HOTREAD8] spinning on 0x000000NN ... guest-fn=0x...` = a guest loop reading the null page:
  on the console this would be a crash, the cause is upstream (a null object).
- Copy the log(s) before any scripted run overwrites them.

## 2. Where is each thread

```bash
MS_PID=<pid> python scripts/host_stacks.py --name main     # call chain of the main thread
MS_PID=<pid> python scripts/host_stacks.py                 # every named thread
MS_PID=<pid> python scripts/host_ppuctx.py                 # guest registers of main (run it 3 times)
MS_PID=<pid> python scripts/host_locks.py                  # lv2 mutexes / conds: who owns, who waits
MS_PID=<pid> python scripts/host_spuctx.py --name ""       # SPU contexts: pc, lr (= where a task waits)
```

The stack scan is heuristic: the first frames are reliable, later ones can be stale. Registers
that keep the same values over three samples = a tight loop; `r3` flipping between two values =
a compare loop (`strcmp` = `func_00ABCBDC`).

## 3. What is it looking at

- `guest_peek.py <ea> <len>` (hex + ASCII) on the pointers found in the registers, and on the
  guest stack (`r1`): the back chain is at `[sp]`, the saved LR of each frame at `[frame+0x10]`
  (64-bit words: the address is the low half), and local `std::string`s show as text.
- `guest_find.py <hex bytes>` finds a value or a text anywhere in guest memory;
  `guest_find_obj.py <pid|0> <name>` finds game objects by the static string they point to.
- Compare with a healthy instance or run (same address in another `MS_PID`): the difference is
  the bug. Dump both sides to files before concluding.

## 4. Which code

- Lifted source of a function: `work/BCES00484/recomp/ppu_recomp_NNN.cpp`,
  `grep -l "^void func_XXXXXXXX"`. The call sites carry the guest return address
  (`ctx->lr = 0x...; func_...(ctx)`): grep `ctx->lr = 0x<saved LR>` to find the caller of a frame.
- `strref.py "<text>"` (functions that use a string), `strref.py --callers func_X` (direct
  callers; none = virtual method or callback: look for its OPD in a vtable, see the journal of
  2026-11-25 "Qui écrit le profil").
- `PORT_GAME_LOG=1` on the next run: the title's own debug messages around the event.
- An entry hook to log arguments or a guest call chain: `port/func_hooks.txt` +
  `scripts/func_hooks.py` + `port/net_hooks.cpp` (`port_hook_007625C8` prints a chain).

## 5. Before writing "cause found"

- State what is PROVEN (seen in memory / in the log) and what is a hypothesis.
- Rare event: count the tries (`freeze_stress.ps1`, `lan_test.ps1 -Players 3 -Races n` for load).
  A fix for a rare event is validated by a count, or by a log line that shows the event was
  caught (as `[spu] PUTLLC: a store reached word` does for toolkit patch #65), not by one good run.
- First switches to try: `SPU_ASYNC_POOL=0`, `RSX_ASYNC=0`, `SPU_PUTLLC_CAS=0`, `GEO_CACHE=0`.
- Write the autopsy in the journal (`docs/journal/<date>.md`) even without a fix.

## Past cases (journal)

- 2026-11-20 "cause des gels jobs liftés", 2026-11-22 (signal merged on a loaded host: the owed
  signal), 2026-11-24 23 h 20 (endless loading = corrupted decompressed XML, PUTLLC race).
