@echo off
rem Run the MotorStorm: Apocalypse port. Game data is read in place from the dump.
setlocal
set "PS3_VFS_ROOT=F:\Jeux\PS3\MotorStorm - Apocalypse (Europe) (En,Fr,De,Es,It,Nl,Pt,Sv,No,Da,Fi,Ko,Pl,Ru) (v02.00)"
set "ELF=%~dp0..\game\BCES00484\EBOOT.elf"
rem Firmware files the title reads (Multistream's flashMP3.pic): the user's RPCS3 install.
set "PS3_DEV_FLASH=I:\Projets\Recomp\tools\rpcs3\dev_flash"
rem Multistream loads codec code (flashMP3.pic...) into SPU local store at run time and calls it:
rem no lift can exist for it, so the SPU interpreter runs it (otherwise the mixer task dies).
if not defined SPU_INTERP_UNLIFTED set "SPU_INTERP_UNLIFTED=1"
rem Lifted WWS job modules (x25 in race vs the interpreter). PORT_JOBMODS=0 = all interpreted.
if not defined PORT_JOBMODS set "PORT_JOBMODS=1"
rem The title's main WWS job manager (Wws_Job/EvoDefault) is created with maxContention 1: one
rem SPU ran all its jobs, the race's critical path. Two SPUs: race 8.6 -> 9.4 FPS standing
rem (2026-11-21). Four SPUs: 17 -> 21-22 FPS driving, frame 59 -> 44 ms (2026-11-22 evening, the
rem 12 ms job batch wait at 006BCB6C ran on exactly 2 lanes). EvoDefault:5,EvoHigh:2 is no
rem faster (the instance has 5 SPUs). SPURS_MAXCONT=none = the title's values; EvoDefault:2 =
rem the previous default, to try first if jobs misbehave (wrong physics/animation, freeze).
rem EvoHigh (maxContention 1) chained 4-12 small jobs on one lane while the main thread waited
rem (~5 ms a frame): 2 lanes. No gain while the RSX thread was the limit; with toolkit patch #31
rem driving 22.3 / 22.0 -> 25.6 / 22.7 FPS (2026-11-22 night). EvoDefault:4 = before.
if not defined SPURS_MAXCONT set "SPURS_MAXCONT=EvoDefault:4,EvoHigh:2"
rem Every MFC channel access looks its engine up under a lock + list walk unless this cache is on
rem (toolkit default off). Race 2026-11-21: 16.7 / 11.3 / 12.6 FPS, the best run of the day.
if not defined SPU_MFC_LOOKUP_CACHE set "SPU_MFC_LOOKUP_CACHE=1"
rem Frame clock pause: 0 = the fixed Sleep(4) between FIFO drains (measured no slower than 1 =
rem wake as soon as the FIFO has work, which looked a little worse in the race presentation).
if not defined PORT_FIFO_WAIT set "PORT_FIFO_WAIT=0"
rem render_frame on a worker thread (toolkit patch #17). No gain when it was written (2026-11-21),
rem but since the game side got faster the main thread waits ~9 ms a frame for the RSX to consume
rem the previous frame (func_0085D1A0 polls the gcm "ref" register): race 2026-11-22
rem 17.2 / 11.6 / 13.3 -> 19.5 / 13.5 / 14.5 FPS. RSX_ASYNC=0 = render on the FIFO thread.
if not defined RSX_ASYNC set "RSX_ASYNC=1"
rem sys_timer_usleep under 1 ms spins on PAUSE instead of SwitchToThread system calls (the main
rem thread and JobBatchHandler poll thousands of times a second): +2-5 %. 0 = the old loop.
if not defined PS3_USLEEP_SPIN set "PS3_USLEEP_SPIN=8"
rem Open-reservation counts (upstream 585c8efa): a reservation break skips its scan of every
rem guest context when nobody else holds a reservation on the line. Needs the lwarx/ldarx notes
rem in the lifted code (scripts\resv_open_patch.py, or a lift with --resv-open-count).
rem Race 2026-11-22: drive 16.5 -> 17.5 FPS (3 pairs). 0 = scan every time.
if not defined PS3RECOMP_PPU_RESV_OPEN_COUNT set "PS3RECOMP_PPU_RESV_OPEN_COUNT=1"
rem Per-worker SPURS wake (upstream fcfc3054): a dispatch wakes only the policy-module worker it
rem filled, not every worker of the instance. Race 2026-11-22 (3 pairs): standing 15.1 -> 16.2 FPS,
rem driving unchanged. 0 = one shared condition variable. New freeze: try 0 here too.
if not defined PS3RECOMP_SPURS_WORKER_WAKE set "PS3RECOMP_SPURS_WORKER_WAKE=1"
rem SPU code runs under MXCSR round-toward-zero + flush-to-zero + denormals-are-zero, the SPU's own
rem float behaviour: the port's lifted SPU sources are built with native single-precision floats
rem (PORT_SPU_FLOAT_FAST=1, toolkit patch #40) and expect it. 2026-11-23: race driving 22 -> 25-26
rem FPS, standing +1, and the Multistream music stopped stuttering. 0 = default MXCSR (the native
rem ops then round to nearest and keep denormals: works, a little further from the SPU).
if not defined SPU_FLOAT_RZ set "SPU_FLOAT_RZ=1"
rem Persistent cache of converted indexed geometry (toolkit patch #43): nearly every indexed batch
rem of a race frame is byte for byte one the backend already converted, and converting them again
rem was half of the RSX FIFO thread, which bounded the frame. Content is hashed at every use.
rem 2026-11-23: standing 23 -> 26.6 and 21.3 -> 25.6 FPS, driving +1 to +3.5. 0 = convert every
rem batch every frame; try 0 first if geometry is missing or wrong. GEO_STATS=<frames> = counters.
if not defined GEO_CACHE set "GEO_CACHE=1"
rem The title limits itself to 30 FPS through the RSX: each frame queues SEMAPHORE_ACQUIRE(label
rem 72 == 1) in front of its flip, and its vblank handler writes the 1 two vblanks after the
rem previous flip. The toolkit skips ACQUIRE by default (0): nothing held the title back, and it
rem ran 30 % too fast whenever the machine could do 40 FPS (2026-11-23). 1 = the walker waits,
rem as the RSX does. _MS = how long before an acquire nobody answers is given up (a "[SEMA] ...
rem gave up" line in run.log, 4 FPS instead of a hang). Goes with the vblank clock of main.cpp
rem (PORT_VBLANK_THREAD, PORT_VBLANK_HZ=59.94) and the MLAA labels cleared in hle_overrides.cpp:
rem docs\hle.md "Frame pacing".
rem Above 30 FPS at normal game speed: PORT_SIM_RT=1 puts the title's simulation clock in its
rem real-time mode (each frame advances by the wall time, not by a fixed 1/30 s) and the flip
rem interval at PORT_SIM_INTERVAL vblanks (1 = up to 60 FPS, 2 = 30 at most but no slow-down
rem under 30). 0 = the game as shipped. 2026-11-24, bridge: 41 FPS standing, 46 driving, race
rem clock x0.999 of the wall clock. docs\hle.md "Above 30 FPS at normal speed".
if not defined PORT_SIM_RT set "PORT_SIM_RT=0"
if not defined GCM_SEMA_ACQUIRE set "GCM_SEMA_ACQUIRE=1"
if not defined GCM_SEMA_ACQUIRE_MS set "GCM_SEMA_ACQUIRE_MS=250"
rem D3D12 per-frame vertex buffer: a race frame needs ~2.2M (default 393216: its main pass and
rem post-processing were dropped). Costs n * 512 bytes of upload heap (~1.5 GB here).
if not defined RSX_MAX_VERTICES set "RSX_MAX_VERTICES=3145728"
rem Compiled guest shaders (D3DCompile bytecode), reused across runs: the race start compiles ~1100.
if not defined RSX_SHADER_CACHE set "RSX_SHADER_CACHE=F:\Jeux\PS3\_recomp\BCES00484\shader_cache"
rem The toolkit replaces a VS projection whose c[0].x is outside (0,8) by a fixed perspective
rem (a vkcube workaround): this title's shadow-map matrices have c00 < 0, so every shadow caster
rem got depth ~1/99 and the sun cast no shadows. Off for this title.
if not defined VP_NOFIXPROJ set "VP_NOFIXPROJ=1"
rem Render resolution (toolkit patch #63, docs\lanceur.md): set PORT_RES=1920x1080 (or 2560x1440,
rem 3840x2160) before calling this file; main.cpp turns it into RSX_OUT / RSX_RT_SCALE and the
rem lists of fragment programs that need care under a scale (RSX_WPOS_HOST, RSX_FP_GUEST_GRID).
rem Not set here: 1280x720, the title's own display mode, stays the default.
rem The title's HDD (game data + ~700 cache files, 100+ MB): on F:, next to the dumps, not on I:.
if not defined PS3_HDD0_ROOT set "PS3_HDD0_ROOT=F:\Jeux\PS3\_recomp\BCES00484\dev_hdd0"
if not defined PS3_HDD1_ROOT set "PS3_HDD1_ROOT=F:\Jeux\PS3\_recomp\BCES00484\dev_hdd1"
rem Save data and trophies: the toolkit's default is .\gamedata relative to the CURRENT directory,
rem so a launch from another directory started on a blank save (first-boot screen/pad setup) and
rem left a stray gamedata\ there. Pinned next to this script, wherever the launch comes from.
if not defined PS3_GAMEDATA_ROOT set "PS3_GAMEDATA_ROOT=%~dp0gamedata"
if not exist "%PS3_HDD0_ROOT%" mkdir "%PS3_HDD0_ROOT%"
if not exist "%PS3_HDD1_ROOT%" mkdir "%PS3_HDD1_ROOT%"
rem Files of ms3.psarc replaced at read time (menus: docs\reseau.md), the disc is not touched:
rem the patch list made by scripts\psarc_patch.py, when it exists. PORT_PSARC_PATCHES=0 = off.
if not defined PORT_PSARC_PATCHES if exist "%~dp0psarc_patches.bin" set "PORT_PSARC_PATCHES=%~dp0psarc_patches.bin"
rem PORT_EXE = another build of the port (an A/B exe, the PGO builds on E:: port\build_pgo.bat).
if not defined PORT_EXE set "PORT_EXE=%~dp0build\MotorStormApocalypse.exe"
rem PORT_RUN_LOG = another log file (a second instance on the same machine: run_lan.bat).
if not defined PORT_RUN_LOG set "PORT_RUN_LOG=%~dp0run.log"
"%PORT_EXE%" "%ELF%" "%PS3_VFS_ROOT%" %* > "%PORT_RUN_LOG%" 2>&1
echo exit code %ERRORLEVEL% (log: %PORT_RUN_LOG%)
