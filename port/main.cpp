/*
 * ps3recomp game project -- entry point template.
 *
 * This is the runner. It boots a lifted title through the toolkit's PPU
 * scaffold: allocate the flat guest VM, load the PPU ELF named on the command
 * line, register the lifted function table and the HLE NID handlers, start a
 * frame clock, and dispatch the entry OPD.
 *
 * The scaffold does the work; nothing below reimplements it. ppu_load_elf,
 * ppu_recomp_register, ppu_hle_init, ppu_sysprx_register, ppu_fs_register,
 * lv2_init_syscalls and ppu_run all come from the toolkit, compiled into this
 * project from PS3RECOMP_DIR (see CMakeLists.txt). What is left here is the
 * part a port owns: which backend to present through, how the frame clock is
 * paced, and whatever diagnostics the title turns out to need.
 *
 * runtime/ppu/tests/boot_main.cpp in the toolkit is the same boot in its
 * fully-instrumented form -- crash filter, hang watchdog, guest-PC sampling
 * profiler. Read it when a boot goes wrong; copy from it what the title
 * needs. It is deliberately not what a fresh project starts with.
 *
 * The one part that IS duplicated from it is the frame clock below, because a
 * port is expected to change its pacing and a shared one would be the wrong
 * shape for that. It was copied faithfully, comments and all. If a pacing bug
 * is fixed in one of the two, look at the other.
 *
 * This builds on Windows, macOS and Linux. CI builds and runs it against the
 * boot smoke title on the last two, and compile-checks it against clang-cl on
 * the first (tools/check_ppu_scaffold.py).
 */

/* The lifter's generated header, which declares ppu_context and the function
 * table. It comes first: everything below is written against that struct. */
#include "ppu_recomp.h"

/* The Win32 names -- Sleep, GetTickCount64, CreateThread, InterlockedIncrement,
 * VirtualAlloc, the scalar typedefs -- from one place. On Windows this is a
 * passthrough to <windows.h>; off Windows the toolkit's shim supplies the same
 * names over pthreads and mmap, so the call sites below are written once. */
#include "win32_compat.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <vector>

#ifndef _WIN32
#include <sys/mman.h>   /* mmap: the guest arena, see alloc_guest_vm */
#endif

#if defined(__APPLE__)
#include <CoreFoundation/CoreFoundation.h>   /* the main thread's run loop, see run_guest */
#include <pthread.h>
#endif

#ifdef _WIN32
/* timeBeginPeriod: <windows.h> arrives with WIN32_LEAN_AND_MEAN set, which
 * excludes the multimedia timer API, so it is asked for by name -- and after
 * windows.h, since timeapi.h uses UINT. No shim exists off Windows because
 * there is nothing to shim: the 15.6 ms default timer granularity this works
 * around is a Windows problem. */
#include <timeapi.h>
#endif

/* ---------------------------------------------------------------------------
 * What the scaffold gives this file
 * -----------------------------------------------------------------------*/
extern "C" {
uint32_t ppu_load_elf(const char* path);      /* ELF -> guest RAM, returns entry OPD */
void     ppu_recomp_register(void);           /* generated: lifted table -> address map */
void     ppu_hle_init(void);                  /* firmware import NID -> HLE handler */
void     ppu_sysprx_register(void);           /* boot-critical CRT (sys_initialize_tls, ...) */
void     ppu_fs_register(void);               /* cellFs over the real game directory */
}
extern "C" const char* g_hle_inflight[];   /* ppu_hle.cpp (PORT_WATCH) */
extern "C" const char* g_last_hle_name;
extern "C" void ppu_report_guest_lrs(void);
extern "C" void port_hwwatch_start(void);   /* port_hwwatch.cpp */
extern "C" void port_listdump(void);
extern "C" {
void     lv2_init_syscalls(void);             /* the lv2 syscall table */
int      ppu_run(uint32_t entry_opd, uint32_t stack_top);

/* This project's own: load whatever real system PRX modules the title needs
 * into guest RAM and register their exports. stubs.cpp has the empty version
 * a game with no lifted PRX wants. */
void     ps3_load_prx_modules(void);

extern const char* ppu_vfs_root;              /* host dir the PS3 mount points map into */
void     ps3_host_quit(const char* why);      /* cellSysutil.c: REQUEST_EXITGAME, then exit 0 */

/* sys_ppu_thread.c: the main thread's stack, as sys_ppu_thread_get_stack_information
 * reports it. Left at 0 it names VM_STACK_BASE, the first created thread's stack. */
extern uint32_t g_ppu_main_stack_addr;
extern uint32_t g_ppu_main_stack_size;

/* The status the guest handed to sys_process_exit. A title that exits that way
 * never returns through ppu_run, so this is only read on the path where the
 * entry function unwound instead. */
extern int     g_sys_process_exit_called;
extern int32_t g_sys_process_exit_code;

/* Host-provided symbols the runtime and the HLE libraries link against. */
uint8_t* vm_base = nullptr;
extern uint32_t ppu_vm_size;                  /* ppu_loader.cpp: the OOB guard */

/* Guest-callback dispatch. g_ps3_guest_caller is the hook the HLE runtime
 * calls back into recompiled code through -- cellSysutil events and the GCM
 * vblank/flip handlers. ppu_guest_call does the OPD -> dispatch. */
typedef void (*ps3_guest_caller_fn)(uint32_t, uint64_t, uint64_t, uint64_t, uint64_t,
                                    uint64_t, uint64_t, uint64_t, uint64_t);
extern ps3_guest_caller_fn g_ps3_guest_caller;
uint64_t ppu_guest_call(uint32_t, uint64_t, uint64_t, uint64_t, uint64_t,
                        uint64_t, uint64_t, uint64_t, uint64_t);

/* The GCM half of the frame clock. */
void     cellGcmTickVBlank(void);
void     cellGcmTickFlip(void);
int      cellGcm_take_flip_pending(void);
void     cellGcm_rsx_process_fifo(void);      /* drain get -> put */
unsigned cellGcm_flip_request_count(void);
}

/* ---------------------------------------------------------------------------
 * RSX present backend
 * -----------------------------------------------------------------------*/
/* D3D12 on Windows, Metal on Apple, and the null backend's headless software
 * path anywhere else -- the same selection runtime/host/host_posix.c and the
 * toolkit's boot harness make. All three expose the same three entry points,
 * so the frame clock below is backend-agnostic. */
#if defined(_WIN32)
extern "C" int  rsx_d3d12_backend_init(uint32_t w, uint32_t h, const char* title);
extern "C" void rsx_d3d12_backend_present(void);
extern "C" int  rsx_d3d12_backend_pump_messages(void);
#  define rsx_backend_init    rsx_d3d12_backend_init
#  define rsx_backend_present rsx_d3d12_backend_present
#  define rsx_backend_pump    rsx_d3d12_backend_pump_messages
#  define RSX_BACKEND_NAME    "D3D12"
#elif defined(__APPLE__)
extern "C" int  rsx_metal_backend_init(uint32_t w, uint32_t h, const char* title);
extern "C" void rsx_metal_backend_present(void);
extern "C" int  rsx_metal_backend_pump_messages(void);
#  define rsx_backend_init    rsx_metal_backend_init
#  define rsx_backend_present rsx_metal_backend_present
#  define rsx_backend_pump    rsx_metal_backend_pump_messages
#  define RSX_BACKEND_NAME    "Metal"
#elif defined(PS3RECOMP_RSX_VULKAN)
extern "C" int  rsx_vulkan_backend_init(uint32_t w, uint32_t h, const char* title);
extern "C" void rsx_vulkan_backend_present(void);
extern "C" int  rsx_vulkan_backend_pump_messages(void);
#  define rsx_backend_init    rsx_vulkan_backend_init
#  define rsx_backend_present rsx_vulkan_backend_present
#  define rsx_backend_pump    rsx_vulkan_backend_pump_messages
#  define RSX_BACKEND_NAME    "Vulkan"
#else
extern "C" int  rsx_null_backend_init(uint32_t w, uint32_t h, const char* title);
extern "C" void rsx_null_backend_present(void);
extern "C" int  rsx_null_backend_pump_messages(void);
#  define rsx_backend_init    rsx_null_backend_init
#  define rsx_backend_present rsx_null_backend_present
#  define rsx_backend_pump    rsx_null_backend_pump_messages
#  define RSX_BACKEND_NAME    "null (headless software)"
#endif

/* ---------------------------------------------------------------------------
 * Configuration
 * -----------------------------------------------------------------------*/
/* The flat VM must span every region the PS3 memory map uses, not just the
 * game image: sys_ppu_thread_create puts thread stacks at 0xD0000000, so a
 * smaller arena makes every spawned thread's stack access out of bounds. */
#define VM_SIZE       0x100010000ull   /* the full 32-bit guest space + a 64K guard */
#define STACK_TOP     0x0FF00000u      /* main-thread stack, below the 0x10000000 segment */
#define STACK_SIZE    0x00100000u      /* what the main thread is told it has */
#define WINDOW_WIDTH  1280
#define WINDOW_HEIGHT 720

/* ---------------------------------------------------------------------------
 * Frame clock
 * -----------------------------------------------------------------------*/
/* On real hardware the RSX raises a vblank interrupt about 60 times a second
 * and that is what drives the game's frame loop. With no RSX it is synthesized
 * here: a host thread calls cellGcmTickVBlank/TickFlip, which invoke the
 * handlers the guest registered, and drains the GCM FIFO. Without this the
 * title initialises, registers its handlers and then waits forever.
 *
 * The ticks are driven off real elapsed time rather than off how long present()
 * took. A hidden or occluded window makes present block hard, and pacing the
 * ticks behind it paces the whole game behind it. */
static volatile LONG g_frames_presented = 0;

/* Frames handed to the backend at a guest FLIP boundary -- one per frame the
 * guest actually finished. The presents made before the guest's first flip, so
 * a fresh window is not left blank through a long boot, carry no guest frame
 * and are deliberately not counted. */
extern "C" unsigned ppu_boot_frames_presented(void)
{
    return (unsigned)g_frames_presented;
}

/* PORT_MAX_FPS=<n> (default 60, 0 = no limit): guest frames are presented at most n times a
 * second, as the console's 60 Hz display did. Without it the menus ran at 100-170 FPS (the
 * display's refresh rate): their logic counts frames, so they scrolled several entries per
 * press and scripted input (PAD_FILE) landed at random. The wait is before the present, on the
 * frame clock: the guest's next flip waits behind it, which is what paces the title. */
static void frame_limit(void)
{
    static double period = -1.0;
    static LARGE_INTEGER freq, last;
    if (period < 0.0) {
        const char* e = getenv("PORT_MAX_FPS");
        const int n = e ? atoi(e) : 60;
        period = n > 0 ? 1.0 / n : 0.0;
        QueryPerformanceFrequency(&freq); QueryPerformanceCounter(&last);
        fprintf(stderr, "[port] PORT_MAX_FPS=%d%c", n, 10);
    }
    if (period <= 0.0) return;
    for (;;) {
        LARGE_INTEGER t; QueryPerformanceCounter(&t);
        const double left = period - (double)(t.QuadPart - last.QuadPart) / (double)freq.QuadPart;
        if (left <= 0.0) break;
        if (left > 0.002) Sleep((DWORD)(left * 1000.0) - 1); else SwitchToThread();
    }
    QueryPerformanceCounter(&last);
}

static void present_guest_frame(void)
{
    frame_limit();
    rsx_backend_present();
    /* This thread increments and guest threads read, so interlocked rather
     * than a volatile ++, which on arm64 is neither atomic nor a fence. */
    InterlockedIncrement(&g_frames_presented);
}

/* The pause between two passes of the frame clock. It was a fixed Sleep(4): commands the
 * guest had just queued waited up to 4-5 ms for the next drain, and so did every RSX label
 * (render-pass fence) and the flip the title's main thread polls for -- several times a frame
 * in MotorStorm Apocalypse's race. Now the pause ends as soon as the FIFO has work
 * (put != get in the control register), and lasts 4 ms at most as before.
 * PORT_FIFO_WAIT=0: the fixed Sleep(4); 1 (default): poll put every 1 ms sleep;
 * 2: poll while yielding (no sleep: lowest latency, one busy host thread).
 * A drain that could not advance (walker parked on a semaphore, flip pending) must not turn
 * this into a spin: after a pass that left get where it was, the pause is a plain sleep. */
extern "C" uint32_t cellGcm_control_guest_addr(void);
extern "C" int      cellGcm_sema_wait_state(void);   /* toolkit patch #44 */
static inline uint32_t fifo_ctl(uint32_t off)
{
    extern uint8_t* vm_base;
    uint32_t v; memcpy(&v, vm_base + cellGcm_control_guest_addr() + off, 4);
    return __builtin_bswap32(v);
}
static void fifo_wait(void)
{
    static int mode = -1;
    static uint32_t last_get = 0xFFFFFFFFu, last_put = 0xFFFFFFFFu;
    if (mode < 0) { const char* e = getenv("PORT_FIFO_WAIT"); mode = e ? atoi(e) : 1;
                    fprintf(stderr, "[port] PORT_FIFO_WAIT=%d%c", mode, 10); }
    extern uint8_t* vm_base;
    /* The walker is parked on a SEMAPHORE_ACQUIRE (GCM_SEMA_ACQUIRE=1). In a race that is the
     * title's own frame pacing: it queues ACQUIRE(label 72 == 1) in front of every flip and its
     * vblank handler writes the 1 two vblanks after the previous flip. The flip must follow the
     * label closely, so look every millisecond instead of sleeping the whole pause. */
    if (vm_base && cellGcm_sema_wait_state() == 1) {
        for (int i = 0; i < 4 && cellGcm_sema_wait_state() == 1; i++) Sleep(1);
        return;
    }
    if (mode <= 0 || !vm_base) { Sleep(4); return; }
    const uint32_t get = fifo_ctl(4), put = fifo_ctl(0);
    /* same get and put as before the last pass: it made no progress, nothing new was queued */
    const int stuck = (get != put && get == last_get && put == last_put);
    last_get = get; last_put = put;
    if (get != put && !stuck) return;            /* work queued: drain now */
    if (stuck) { Sleep(1); return; }
    LARGE_INTEGER f, t0, t; QueryPerformanceFrequency(&f); QueryPerformanceCounter(&t0);
    for (;;) {
        if (mode >= 2) SwitchToThread(); else Sleep(1);
        if (fifo_ctl(0) != fifo_ctl(4)) return;
        QueryPerformanceCounter(&t);
        if ((t.QuadPart - t0.QuadPart) * 1000 >= f.QuadPart * 4) return;
    }
}

#ifdef _WIN32
/* PORT_PIN=<n> (experiment, default 0): give the critical threads a physical core of their own
 * through Windows CPU sets. 1 = the guest main thread owns core 0 (both logical processors),
 * every other thread of the process runs on the remaining cores; 2 = and the FIFO thread owns
 * core 1. With 5 SPU lanes, the render thread and Multistream busy, the main thread otherwise
 * shares its core with an SMT sibling much of the frame. */
static int port_pin_mode(void)
{
    static int m = -1;
    if (m < 0) { const char* e = getenv("PORT_PIN"); m = e ? atoi(e) : 0; }
    return m;
}
/* which: 0 = process default (every core from `first_free` up), 1 = this thread on core `core`. */
static void port_pin_apply(int which, unsigned core, unsigned first_free)
{
    ULONG len = 0;
    GetSystemCpuSetInformation(NULL, 0, &len, GetCurrentProcess(), 0);
    if (!len) return;
    std::vector<unsigned char> buf(len);
    if (!GetSystemCpuSetInformation((PSYSTEM_CPU_SET_INFORMATION)buf.data(), len, &len, GetCurrentProcess(), 0)) return;
    std::vector<unsigned char> cores;          /* distinct CoreIndex values, in order */
    std::vector<ULONG> ids;
    for (ULONG off = 0; off < len; ) {
        auto* i = (PSYSTEM_CPU_SET_INFORMATION)(buf.data() + off);
        if (i->Type == CpuSetInformation) {
            unsigned ci = 0;
            for (; ci < cores.size(); ci++) if (cores[ci] == i->CpuSet.CoreIndex) break;
            if (ci == cores.size()) cores.push_back(i->CpuSet.CoreIndex);
            if (which == 0 ? ci >= first_free : ci == core) ids.push_back(i->CpuSet.Id);
        }
        off += i->Size;
    }
    if (ids.empty() || cores.size() <= first_free) return;
    BOOL ok = which == 0 ? SetProcessDefaultCpuSets(GetCurrentProcess(), ids.data(), (ULONG)ids.size())
                         : SetThreadSelectedCpuSets(GetCurrentThread(), ids.data(), (ULONG)ids.size());
    fprintf(stderr, "[port] PORT_PIN: %s -> %u logical processors (%s)\n",
            which == 0 ? "process default" : core == 0 ? "main thread, core 0" : "FIFO thread, core 1",
            (unsigned)ids.size(), ok ? "ok" : "FAILED");
}
#endif

/* The vblank clock, on a thread of its own (PORT_VBLANK_THREAD, default 1; 0 = the 16 ms ticks
 * of the frame clock below, as before 2026-11-23).
 * This title paces itself on vblanks: its handler counts them and lets the RSX flip two vblanks
 * after the previous flip (30 FPS), so the game runs exactly as fast as this clock says. The
 * frame clock's ticks were 16 ms apart on GetTickCount64 (62.5 Hz: 4 % fast) and came late and
 * in bursts whenever a FIFO pass was long. Here: 59.94 Hz (PORT_VBLANK_HZ) on the performance
 * counter, one tick per period; a tick this thread missed by more than a period is dropped, not
 * made up in a burst. */
/* The title's simulation clock in real time (PORT_SIM_RT=1; default 0 = the game as shipped).
 * As shipped every frame advances the simulation by a fixed 1/30 s and the RSX flips every second
 * vblank: above 30 FPS the title holds itself back, under 30 FPS the game slows down. The clock
 * source the title constructs (func_005EE2A4, at +0x40 of the object whose vtable is 0x01188348;
 * a static pointer to that object is at 0x014E3D10) has a real-time mode of its own: +0x1C = 1
 * makes each frame add the wall time since the previous one (times the slow-motion scale, +0x14),
 * and +0x18 is the flip interval in vblanks, which the present copies into the display object
 * every frame. The title's setup (func_002D6F30) writes flag 0 / interval 2 and may write them
 * again (race load, menus), so this runs on every vblank and puts real time and
 * PORT_SIM_INTERVAL (default 1: up to 60 FPS; 2: 30 FPS at most, real time under 30) back.
 * Two constants go with it, rewritten once after checking the shipped value:
 *  - the frame dt clamp of func_001DA398, 0.04 s (float 0x001DA384, double 0x001DA388): with it a
 *    frame longer than 40 ms slows the game; raised to PORT_SIM_DT_MAX_MS (default 66.7 = 1/15 s);
 *  - func_00EC8A98 snaps a dt of 0.031..0.035 s to exactly 1/30 (low bound: double 0x00EC8A80),
 *    a 5 % error per frame around 30 FPS for a real-time clock: bound raised to 1e30 (never).
 * Layout and addresses: notes of millennium-h4x0r's port ("Simulation pacing"), checked against
 * our EBOOT; live experiment: scripts/sim_clock.py. docs/hle.md "Frame pacing". */
void port_net_tick(void);      /* net_hooks.cpp: LAN mode state kept on every vblank */

static void port_sim_clock_tick(void)
{
    port_net_tick();
    static int rt = -1, interval = 1, fixes = 0, consts = 0;
    static double dt_max_ms = 66.7;
    if (rt < 0) {
        const char* e = getenv("PORT_SIM_RT");
        rt = (e && e[0] == '1') ? 1 : 0;
        e = getenv("PORT_SIM_INTERVAL");
        interval = e ? atoi(e) : 1;
        if (interval < 1 || interval > 4) interval = 1;
        e = getenv("PORT_SIM_DT_MAX_MS");
        if (e) { const double v = atof(e); if (v >= 20.0 && v <= 200.0) dt_max_ms = v; }
        if (rt) fprintf(stderr, "[port] PORT_SIM_RT=1: real-time simulation clock, flip interval %d, dt clamp %.1f ms%c",
                        interval, dt_max_ms, 10);
    }
    extern uint8_t* vm_base;
    if (!rt || !vm_base) return;
    auto rd32 = [](uint32_t ea) { uint32_t v; memcpy(&v, vm_base + ea, 4); return __builtin_bswap32(v); };
    auto wr32 = [](uint32_t ea, uint32_t v) { v = __builtin_bswap32(v); memcpy(vm_base + ea, &v, 4); };
    if (!consts && rd32(0x001DA384u) == 0x3D23D70Au) {          /* the image is loaded */
        consts = 1;
        const float fc = (float)(dt_max_ms / 1000.0);
        const double dc = (double)fc, never = 1e30;
        uint32_t fw; uint64_t dw, nw;
        memcpy(&fw, &fc, 4); memcpy(&dw, &dc, 8); memcpy(&nw, &never, 8);
        if (rd32(0x001DA388u) == 0x3FA47AE1u && rd32(0x001DA38Cu) == 0x40000000u) {
            wr32(0x001DA384u, fw);
            wr32(0x001DA388u, (uint32_t)(dw >> 32)); wr32(0x001DA38Cu, (uint32_t)dw);
            fprintf(stderr, "[port] sim clock: frame dt clamp 40 -> %.1f ms%c", dt_max_ms, 10);
        } else fprintf(stderr, "[port] sim clock: dt clamp constants not as expected, left alone%c", 10);
        if (rd32(0x00EC8A80u) == 0x3F9FBE76u && rd32(0x00EC8A84u) == 0xC8B43958u) {
            wr32(0x00EC8A80u, (uint32_t)(nw >> 32)); wr32(0x00EC8A84u, (uint32_t)nw);
            fprintf(stderr, "[port] sim clock: 1/30 s snap of the frame dt turned off%c", 10);
        } else fprintf(stderr, "[port] sim clock: snap constant not as expected, left alone%c", 10);
    }
    const uint32_t owner = rd32(0x014E3D10u);
    if (owner < 0x10000000u || owner >= 0x40000000u || (owner & 3u)) return;
    if (rd32(owner) != 0x01188348u) return;
    const uint32_t clk = owner + 0x40u, hz = rd32(clk + 0x10u);
    if (hz != 60u && hz != 50u && hz != 30u) return;            /* not constructed yet */
    const uint32_t flag = rd32(clk + 0x1Cu), iv = rd32(clk + 0x18u);
    if (flag == 1u && iv <= (uint32_t)interval) return;
    if (flag != 1u) wr32(clk + 0x1Cu, 1u);
    if (iv > (uint32_t)interval) wr32(clk + 0x18u, (uint32_t)interval);
    if (fixes++ < 16)
        fprintf(stderr, "[port] sim clock 0x%08X made real-time (flag %u -> 1, interval %u -> %u, %u Hz)%c",
                clk, flag, iv, iv > (uint32_t)interval ? (uint32_t)interval : iv, hz, 10);
}

static int vblank_thread_on(void)
{
    static int v = -1;
    if (v < 0) { const char* e = getenv("PORT_VBLANK_THREAD"); v = !(e && e[0] == '0'); }
    return v;
}
static DWORD WINAPI vblank_clock(LPVOID)
{
    const char* e = getenv("PORT_VBLANK_HZ");
    double hz = e ? atof(e) : 59.94;
    if (!(hz >= 1.0 && hz <= 1000.0)) hz = 59.94;
    LARGE_INTEGER f, t;
    QueryPerformanceFrequency(&f); QueryPerformanceCounter(&t);
    const double period = (double)f.QuadPart / hz;            /* counter units per vblank */
    double next = (double)t.QuadPart + period;
    /* CREATE_WAITABLE_TIMER_HIGH_RESOLUTION (Windows 10 1803+): ~0.5 ms without spinning. */
    HANDLE timer = CreateWaitableTimerExW(NULL, NULL, 0x00000002, TIMER_ALL_ACCESS);
    SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_TIME_CRITICAL);
    fprintf(stderr, "[port] vblank clock: %.3f Hz, %s timer%c", hz, timer ? "high-resolution" : "Sleep", 10);
    for (;;) {
        for (;;) {
            QueryPerformanceCounter(&t);
            const double left = (next - (double)t.QuadPart) / (double)f.QuadPart;   /* seconds */
            if (left <= 0.0) break;
            if (timer) {
                LARGE_INTEGER due; due.QuadPart = -(LONGLONG)(left * 1e7);           /* 100 ns units */
                if (due.QuadPart < 0 && SetWaitableTimer(timer, &due, 0, NULL, NULL, FALSE))
                    WaitForSingleObject(timer, 100);
            } else if (left > 0.002) Sleep((DWORD)(left * 1000.0) - 1);
            else SwitchToThread();
        }
        cellGcmTickVBlank();
        port_sim_clock_tick();
        next += period;
        QueryPerformanceCounter(&t);
        if ((double)t.QuadPart - next > period) next = (double)t.QuadPart + period;
    }
    return 0;
}

static DWORD WINAPI frame_clock(LPVOID)
{
#ifdef _WIN32
    if (port_pin_mode() >= 2) port_pin_apply(1, 1, 2);
#endif
    const char* title = getenv("PS3_TITLE");
    if (!title || !*title) title = "ps3recomp";

#ifdef _WIN32
    /* PORT_RES=<W>x<H>: the size the picture is RENDERED at (true Full HD and above, toolkit patch
     * #63; docs/lanceur.md). The title composes its frame in 1280x1080 targets whatever the display
     * mode (720 rows shown: the display copy squeezes them), so the backend is asked for a swap
     * chain of W x H (RSX_OUT) and for offscreen targets W/1280 by H/1080 times their size
     * (RSX_RT_SCALE): 1920x1080 = x1.5 by x1, 2560x1440 = x2 by x1.33, 3840x2160 = x3 by x2. The
     * picture is 16:9: the largest 16:9 size inside what is asked. Unset or 1280x720 = as before. */
    if (const char* pr = getenv("PORT_RES"); pr && *pr) {
        int w = 0, h = 0;
        if (sscanf(pr, "%dx%d", &w, &h) == 2 && w >= 640 && h >= 360 && w <= 15360 && h <= 8640) {
            if (w * 9 > h * 16) w = h * 16 / 9; else h = w * 9 / 16;
            w &= ~1; h &= ~1;
            char buf[64];
            if (!getenv("RSX_OUT")) { snprintf(buf, sizeof buf, "%dx%d", w, h); _putenv_s("RSX_OUT", buf); }
            if (!getenv("RSX_RT_SCALE")) {
                double sx = w / 1280.0, sy = h / 1080.0;
                if (sx < 1.0) sx = 1.0;
                if (sy < 1.0) sy = 1.0;
                snprintf(buf, sizeof buf, "%.9gx%.9g", sx, sy);
                _putenv_s("RSX_RT_SCALE", buf);
            }
            /* The fragment programs that turn WPOS into a per-pixel pattern (the sun shadows' 2x2
             * rotation of their PCF taps) keep host pixels: in guest pixels the pattern had three
             * phases at x1.5, a comb along every shadow edge. "[RS] fp=... reads WPOS" in the log
             * lists the candidates (the tyre tracks, 0x00344881, index the screen: guest pixels). */
            if (!getenv("RSX_WPOS_HOST")) _putenv_s("RSX_WPOS_HOST", "002A4441,002A3D41");
            /* The programs written for the guest's pixel grid (the depth-aware upsample that lays
             * the half-size particle buffer over the scene: weights from the pixel's parity) are
             * evaluated at guest pixel centres; scaled, they sprinkled smoke and glows with dots. */
            if (!getenv("RSX_FP_GUEST_GRID")) _putenv_s("RSX_FP_GUEST_GRID", "003A8C41");
            fprintf(stderr, "[port] PORT_RES=%s: swap chain %s, offscreen targets x%s\n", pr,
                    getenv("RSX_OUT"), getenv("RSX_RT_SCALE"));
        } else fprintf(stderr, "[port] PORT_RES=%s ignored (expected <width>x<height>)\n", pr);
    }
#endif
    int rsx_ok = (rsx_backend_init(WINDOW_WIDTH, WINDOW_HEIGHT, title) == 0);
    fprintf(stderr, "[rsx] %s backend init %s\n", RSX_BACKEND_NAME,
            rsx_ok ? "OK -- window open" : "FAILED");
#ifdef _WIN32
    /* PORT_WINDOW=<w>x<h> (client size) or PORT_WINDOW=fullscreen (borderless, the whole monitor):
     * the size of the WINDOW only. The swap chain keeps its size (1280x720, or PORT_RES above)
     * and DXGI stretches it to the window (the backend has no WM_SIZE / ResizeBuffers): a bigger
     * picture, not a sharper one. The sharper one is PORT_RES; without PORT_WINDOW the window
     * opens at the size of the swap chain. */
    if (const char* pw = getenv("PORT_WINDOW"); rsx_ok && pw && *pw) {
        struct Ctx { HWND hwnd; } found = { NULL };
        EnumWindows([](HWND h, LPARAM p) -> BOOL {
            DWORD pid = 0; char cls[64] = "";
            GetWindowThreadProcessId(h, &pid);
            if (pid == GetCurrentProcessId() && GetClassNameA(h, cls, sizeof cls) && !strcmp(cls, "ps3recomp_d3d12")) {
                ((Ctx*)p)->hwnd = h; return FALSE;
            }
            return TRUE;
        }, (LPARAM)&found);
        int w = 0, h = 0;
        const bool stretch = !_stricmp(pw, "stretch");
        if (found.hwnd && (stretch || !_stricmp(pw, "fullscreen"))) {
            /* fullscreen: the picture keeps the shape of the swap chain (16:9), centred, as large
             * as the monitor allows, on a black window that covers the rest (a 32:9 or 21:9
             * monitor: black bands left and right). stretch: the whole monitor, distorted when
             * the monitor is not 16:9 (what "fullscreen" did before 2026-11-25). */
            MONITORINFO mi = { sizeof mi };
            GetMonitorInfoA(MonitorFromWindow(found.hwnd, MONITOR_DEFAULTTONEAREST), &mi);
            const LONG mw = mi.rcMonitor.right - mi.rcMonitor.left, mh = mi.rcMonitor.bottom - mi.rcMonitor.top;
            RECT cr = { 0, 0, 0, 0 };
            GetClientRect(found.hwnd, &cr);                     /* the swap chain's size, still */
            LONG pw_ = mw, ph_ = mh;
            if (!stretch && cr.right > 0 && cr.bottom > 0) {
                if ((long long)mw * cr.bottom > (long long)mh * cr.right) pw_ = (LONG)((long long)mh * cr.right / cr.bottom);
                else ph_ = (LONG)((long long)mw * cr.bottom / cr.right);
            }
            HWND back = NULL;
            if (pw_ != mw || ph_ != mh) {
                WNDCLASSA wc = {};
                wc.lpfnWndProc = DefWindowProcA;
                wc.hInstance = GetModuleHandleA(NULL);
                wc.hbrBackground = (HBRUSH)GetStockObject(BLACK_BRUSH);
                wc.lpszClassName = "port_backdrop";
                RegisterClassA(&wc);
                /* Served by the backend's message loop (same thread, PeekMessage on every window). */
                back = CreateWindowExA(WS_EX_NOACTIVATE, "port_backdrop", "", WS_POPUP | WS_VISIBLE,
                                       mi.rcMonitor.left, mi.rcMonitor.top, mw, mh, NULL, NULL, wc.hInstance, NULL);
                /* Owned windows stay above their owner: the game can never slip behind its bands. */
                if (back) SetWindowLongPtrA(found.hwnd, GWLP_HWNDPARENT, (LONG_PTR)back);
            }
            SetWindowLongPtrA(found.hwnd, GWL_STYLE, WS_POPUP | WS_VISIBLE);
            SetWindowPos(found.hwnd, HWND_TOP, mi.rcMonitor.left + (mw - pw_) / 2, mi.rcMonitor.top + (mh - ph_) / 2,
                         pw_, ph_, SWP_FRAMECHANGED | SWP_SHOWWINDOW);
            SetForegroundWindow(found.hwnd);
            fprintf(stderr, "[port] window: borderless full screen, picture %ldx%ld on a %ldx%ld monitor%s\n",
                    pw_, ph_, mw, mh, back ? " (black bands)" : "");
        } else if (found.hwnd && sscanf(pw, "%dx%d", &w, &h) == 2 && w >= 320 && h >= 180) {
            RECT wr = { 0, 0, w, h };
            AdjustWindowRect(&wr, WS_OVERLAPPEDWINDOW, FALSE);
            const BOOL ok = SetWindowPos(found.hwnd, NULL, 0, 0, wr.right - wr.left, wr.bottom - wr.top, SWP_NOMOVE | SWP_NOZORDER);
            RECT cr = { 0, 0, 0, 0 };
            GetClientRect(found.hwnd, &cr);
            fprintf(stderr, "[port] window: %dx%d asked (the picture is the swap chain's, stretched): "
                            "SetWindowPos %d (error %lu), client now %ldx%ld, hwnd %p\n",
                    w, h, (int)ok, ok ? 0ul : GetLastError(), cr.right, cr.bottom, (void*)found.hwnd);
        }
    }
#endif

    unsigned  last_flip = 0;
    ULONGLONG next_tick = GetTickCount64();

    for (;;) {
        fifo_wait();
        ULONGLONG now = GetTickCount64();

        int fired = 0;
        while ((long long)(now - next_tick) >= 0 && fired < 240) {
            if (!vblank_thread_on()) { cellGcmTickVBlank(); port_sim_clock_tick(); }
            cellGcmTickFlip();
            /* Present a pending flip BEFORE draining any further. The flip
             * fires at a get==put frame boundary on the guest thread, so the
             * batch held right now is exactly the completed frame; presenting
             * after the drain races the guest's next-frame writes and shows a
             * mixed one. */
            if (rsx_ok && cellGcm_take_flip_pending()) {
                present_guest_frame();
                last_flip = cellGcm_flip_request_count();
            }
            /* Drain the FIFO every tick. This is what writes the RSX sync-fence
             * labels the game's per-frame logic blocks on, so it has to keep
             * advancing at 60 Hz even while present() throttles. */
            if (rsx_ok) cellGcm_rsx_process_fifo();
            next_tick += 16;             /* ~60 Hz */
            fired++;
        }
        if (fired >= 240) next_tick = now;   /* fell too far behind -- resync */

        /* Drain at the outer cadence too, not only on the 16 ms tick: titles
         * fence every render pass on a label the drain writes, and one wave of
         * those at 16 ms apiece paces the guest into single-figure frame rates.
         * The real RSX writes them in microseconds. */
        if (rsx_ok) {
            if (cellGcm_take_flip_pending()) {
                present_guest_frame();
                last_flip = cellGcm_flip_request_count();
            }
            cellGcm_rsx_process_fifo();

            if (rsx_backend_pump() != 0) {
                rsx_ok = 0;              /* window closed */
                /* ...so quit, as the console's Quit Game does, instead of
                 * leaving the game running with no window. */
                ps3_host_quit("window closed");
                continue;
            }
            /* Present on a guest flip. A present on a fixed clock can catch the
             * drain mid-frame and flash a partial one. Before the first flip
             * present freely, so the window is not blank during boot. */
            unsigned fc = cellGcm_flip_request_count();
            if (fc != last_flip) {
                present_guest_frame();
                last_flip = fc;
            } else if (fc == 0) {
                rsx_backend_present();
            }
        }
    }
    return 0;
}

/* ---------------------------------------------------------------------------
 * VFS root
 * -----------------------------------------------------------------------*/
/* Derive the directory holding PS3_GAME from the EBOOT path
 * <root>/PS3_GAME/USRDIR/EBOOT.elf -> <root>. $PS3_VFS_ROOT overrides. */
static char s_vfs_root[1024];

static void derive_vfs_root(const char* eboot)
{
    const char* env = getenv("PS3_VFS_ROOT");
    if (env && *env) { ppu_vfs_root = env; return; }

    strncpy(s_vfs_root, eboot, sizeof s_vfs_root - 1);
    for (char* p = s_vfs_root; *p; p++) if (*p == '\\') *p = '/';
    /* strip EBOOT.elf, USRDIR and PS3_GAME */
    for (int i = 0; i < 3; i++) { char* s = strrchr(s_vfs_root, '/'); if (s) *s = 0; }
    if (!s_vfs_root[0]) strcpy(s_vfs_root, ".");
    ppu_vfs_root = s_vfs_root;
}

/* ---------------------------------------------------------------------------
 * Guest VM
 * -----------------------------------------------------------------------*/
#ifdef _WIN32
/* Demand-paging for the flat VM: reserve the whole 4 GB guest space, which
 * costs no commit, and commit each 64 KB page on first access. Every 32-bit
 * guest offset is then valid, so a garbage guest pointer reads zero instead of
 * killing the process. Faults outside the arena fall through untouched. */
static LONG WINAPI vm_commit_veh(EXCEPTION_POINTERS* ep)
{
    if (ep->ExceptionRecord->ExceptionCode == EXCEPTION_ACCESS_VIOLATION) {
        ULONG_PTR fault = ep->ExceptionRecord->ExceptionInformation[1];
        uintptr_t base  = (uintptr_t)vm_base;
        if (vm_base && fault >= base && fault < base + VM_SIZE) {
            void* page = (void*)(fault & ~(uintptr_t)0xFFFF);
            if (VirtualAlloc(page, 0x10000, MEM_COMMIT, PAGE_READWRITE))
                return EXCEPTION_CONTINUE_EXECUTION;
        }
    }
    return EXCEPTION_CONTINUE_SEARCH;
}
#endif

static bool alloc_guest_vm(void)
{
#ifdef _WIN32
    AddVectoredExceptionHandler(1, vm_commit_veh);
    vm_base = (uint8_t*)VirtualAlloc(NULL, VM_SIZE, MEM_RESERVE, PAGE_READWRITE);
    ppu_vm_size = 0;              /* the whole space is backed; no OOB guard needed */
#else
    /* No vectored exception handlers off Windows, so the arena is mapped up
     * front and lazily backed by the OS: only pages the title touches cost
     * anything. It spans the whole 32-bit space plus the guard, as on Windows.
     * It used to stop below 0xE0000000, but the raw SPU windows (local store
     * and problem-state registers, runtime/spu/spu_raw.c) live from there up.
     * Every load and store a title made into one was reported as an
     * out-of-bounds access and dropped, so a raw SPU was never loaded or
     * started, and sys_raw_spu_create, which clears the registers through
     * vm_base directly, wrote past the end of the mapping. With the whole
     * space backed, ppu_vm_size 0 also gives the loader's bounds check the
     * one-compare fast path Windows already has.
     *
     * mmap, not calloc: vm_commit() hands vm_base + addr to mprotect, which
     * takes page-aligned addresses only. glibc serves an allocation this big
     * from its own mmap chunk and returns a pointer 16 bytes past the page
     * start, so every commit failed with EINVAL and sys_memory_allocate
     * answered ENOMEM to every call. mmap's base is page-aligned and zeroed. */
    void* p = mmap(NULL, VM_SIZE, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);
    vm_base = (p == MAP_FAILED) ? nullptr : (uint8_t*)p;
    ppu_vm_size = 0;              /* the whole space is backed; no OOB guard needed */
#endif
    return vm_base != nullptr;
}

/* ---------------------------------------------------------------------------
 * Main
 * -----------------------------------------------------------------------*/
static void harness_guest_caller(uint32_t opd, uint64_t a0, uint64_t a1,
                                 uint64_t a2, uint64_t a3, uint64_t a4,
                                 uint64_t a5, uint64_t a6, uint64_t a7)
{
    ppu_guest_call(opd, a0, a1, a2, a3, a4, a5, a6, a7);
}

/* ---------------------------------------------------------------------------
 * Running the guest
 * -----------------------------------------------------------------------*/
#if defined(__APPLE__)
/* AppKit only runs on the process's main thread. The Metal backend creates
 * its window and pumps its events with dispatch_sync onto the main queue
 * when it is called from any other thread, as it is from the frame clock.
 * With the guest on the main thread nothing ever serviced that queue: the
 * frame clock blocked in its first rsx_backend_init, no vblank or flip was
 * ever delivered and the FIFO never drained. A title that waits for a flip
 * hangs there. So the guest runs on a thread of its own, with the same
 * 256 MB host stack every guest thread gets (sys_ppu_thread.c), and the
 * main thread turns the run loop until ppu_run returns. Headless runs never
 * touch the main queue, which is why CI does not see the difference. */
struct guest_run { uint32_t entry, stack_top; int rc; volatile int done; };

static void* guest_thread(void* arg)
{
    guest_run* g = (guest_run*)arg;
    g->rc = ppu_run(g->entry, g->stack_top);
    __atomic_store_n(&g->done, 1, __ATOMIC_RELEASE);
    CFRunLoopStop(CFRunLoopGetMain());
    return nullptr;
}

static int run_guest(uint32_t entry, uint32_t stack_top)
{
    static guest_run g;
    g.entry = entry; g.stack_top = stack_top; g.rc = 0; g.done = 0;
    pthread_attr_t attr;
    pthread_attr_init(&attr);
    pthread_attr_setstacksize(&attr, 256u * 1024u * 1024u);
    pthread_t th;
    int err = pthread_create(&th, &attr, guest_thread, &g);
    pthread_attr_destroy(&attr);
    if (err != 0) {
        fprintf(stderr, "[boot] could not start the guest thread (%d)\n", err);
        return -1;
    }
    /* Short slices: CFRunLoopStop only ends a run that is already going. */
    while (!__atomic_load_n(&g.done, __ATOMIC_ACQUIRE))
        CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.05, false);
    pthread_join(th, nullptr);
    return g.rc;
}
#else
static int run_guest(uint32_t entry, uint32_t stack_top) { return ppu_run(entry, stack_top); }
#endif

const char* port_portable_elf(void);    /* portable.cpp: the exe at the root of the game folder */

int main(int argc, char** argv)
{
    const char* elf_path = argc >= 2 ? argv[1] : port_portable_elf();
    if (!elf_path) {
        printf("usage: %s <PPU ELF>   (or no argument, the exe at the root of the game folder)\n", argv[0]);
        return 2;
    }

#ifdef _WIN32
#pragma comment(lib, "winmm.lib")
    /* 1 ms timer resolution. The default granularity is about 15.6 ms, which
     * inflates every shorter wait the title makes and throttles the whole
     * thing. POSIX timers are already fine-grained. */
    timeBeginPeriod(1);
    if (port_pin_mode() >= 1) {
        port_pin_apply(0, 0, port_pin_mode() >= 2 ? 2u : 1u);
        port_pin_apply(1, 0, port_pin_mode() >= 2 ? 2u : 1u);
    }
    /* No sleep and no display power-off while the game runs (a pad does not count as
     * user activity for Windows, and a scripted measurement run has no input at all).
     * Ends with the process. PORT_KEEP_AWAKE=0 = leave the power plan alone. */
    { const char* e = getenv("PORT_KEEP_AWAKE");
      if (!(e && e[0] == '0'))
          SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED); }
    setvbuf(stdout, NULL, _IONBF, 0);   /* unbuffered: do not lose prints on a kill */
#endif

    printf("=== ps3recomp game runner ===\n");

    if (!alloc_guest_vm()) {
        fprintf(stderr, "ERROR: could not allocate the guest address space\n");
        return 1;
    }

    uint32_t entry = ppu_load_elf(elf_path);
    if (!entry) {
        fprintf(stderr, "ERROR: could not load %s\n", elf_path);
        return 1;
    }

    derive_vfs_root(elf_path);
    printf("[boot] VFS root: %s\n", ppu_vfs_root);

    ppu_recomp_register();   /* lifted function table -> address map */
    ps3_load_prx_modules();  /* this game's lifted system PRX, if it has any */
    ppu_hle_init();          /* firmware import NID -> HLE handlers */
    ppu_sysprx_register();   /* boot-critical CRT */
    ppu_fs_register();       /* cellFs over the game directory */
    lv2_init_syscalls();     /* the lv2 syscall table */
    { extern void ps3_sampler_start(void); ps3_sampler_start(); }   /* PS3_SAMPLE=<ms> profiler */
    port_hwwatch_start();    /* PORT_HWWATCH=<ea,...>: hardware write watchpoints (port_hwwatch.cpp) */
    /* PORT_WATCH=<s>: every <s> seconds, which HLE each guest thread is inside and every guest
     * thread's lr (ppu_report_guest_lrs) -- names a hang that no blocking probe sees. */
    if (const char* w = getenv("PORT_WATCH"); w && atoi(w) > 0) {
        CreateThread(NULL, 0, [](LPVOID p) -> DWORD {
            for (unsigned n = 1;; n++) {
                Sleep((DWORD)(uintptr_t)p * 1000u);
                fprintf(stderr, "[WATCH] #%u last HLE=%s\n", n, g_last_hle_name ? g_last_hle_name : "");
                for (unsigned t = 0; t < 64u; t++)
                    if (g_hle_inflight[t]) fprintf(stderr, "[WATCH]   guest-tid %u in %s\n", t, g_hle_inflight[t]);
                ppu_report_guest_lrs();
                port_listdump();     /* PORT_LISTDUMP=<ea> */
                fflush(stderr);
            }
        }, (LPVOID)(uintptr_t)atoi(w), 0, NULL);
    }

    /* Install the guest-callback hook, then start the frame clock. It no-ops
     * until the title registers its vblank and flip handlers during init. */
    g_ps3_guest_caller = harness_guest_caller;
    CreateThread(NULL, 4u * 1024 * 1024, frame_clock, NULL, 0, NULL);
    if (vblank_thread_on()) CreateThread(NULL, 0, vblank_clock, NULL, 0, NULL);

    printf("\n[boot] dispatching entry OPD 0x%08X (stack top 0x%08X)\n\n",
           entry, STACK_TOP);

    /* A title that reads its own stack bounds (to find data its parent left
     * below the top, say) gets the stack it really runs on. */
    g_ppu_main_stack_addr = STACK_TOP - STACK_SIZE;
    g_ppu_main_stack_size = STACK_SIZE;

    int rc = run_guest(entry, STACK_TOP);
    printf("\n[boot] ppu_run returned %d (entry function unwound)\n", rc);

    /* A title that called sys_process_exit never reaches this line: that path
     * ends in the host exit(). Getting here means the entry function returned
     * instead, so hand back the status the guest published if it published
     * one. Returning a hardcoded 0 would report success for a run that never
     * got anywhere. */
    return g_sys_process_exit_called ? (int)g_sys_process_exit_code : 0;
}
