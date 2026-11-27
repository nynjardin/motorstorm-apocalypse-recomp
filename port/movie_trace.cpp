/* MotorStorm: Apocalypse port -- trace of the title's movie player (diagnostic, off by default).
 *
 *   MOVIE_TRACE=<file>   record the demuxer / ring buffer events in memory (no I/O on the hot path)
 *                        and write the last ones to <file> when the demuxer has delivered nothing
 *                        for 3 s after its first access unit (the stall of docs/hle.md "Real
 *                        movies"), or at the end of the movie's file (seek / EOF marks).
 *
 * Entry hooks (scripts/func_hooks.py, port/func_hooks.txt, section "movie player"):
 *   009E70A4  AVI demuxer: a chunk header is parsed (r4 = the 8 header bytes)
 *   009E00D0  demuxer -> track queue: one access unit delivered (r3 track, r4 data, r5 size)
 *   009F74D0  ring-buffer source: Skip(n) by the reader
 *   009F4040  ring buffer: the writer commits n bytes read from the file
 *   009F7550  ring-buffer source: Seek(pos)
 * Object layout (ring-buffer source S, ring R = S + 0x60): R+0x40 read, R+0x48 write, R+0x50 wrap
 * mark, R+0x58 fill, S+0x118 file position written, S+0x128 bytes consumed since the last seek.
 */
#include "ppu_recomp.h"

#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

namespace {
struct Ev { int64_t t; uint32_t tid, kind; uint64_t a, b, c, d; };
constexpr uint32_t kN = 1u << 18;
Ev* g_ev;
std::atomic<uint32_t> g_n{0};
std::atomic<int> g_on{-1};
std::atomic<int64_t> g_last_deliver{0};
std::atomic<uint32_t> g_delivers{0};
char g_path[512];
const char* const kNames[] = { "hdr", "deliver", "skip", "commit", "seek", "BADDATA", "fsread" };
extern "C" { extern void (*g_ps3_fs_read_hook)(const char* guest_path, long long pos, unsigned char* data,
                                               unsigned long long n); }
extern "C" unsigned char* vm_base;
void (*g_prev_read_hook)(const char*, long long, unsigned char*, unsigned long long);
void ev(uint32_t kind, uint64_t a, uint64_t b, uint64_t c, uint64_t d);
/* every cellFsRead of an .avi: a = file position, b = bytes, c = guest address of the buffer */
void read_hook(const char* path, long long pos, unsigned char* data, unsigned long long n)
{
    if (path && std::strstr(path, ".avi")) ev(6, (uint64_t)pos, n, (uint64_t)(data - vm_base), 0);
    if (g_prev_read_hook) g_prev_read_hook(path, pos, data, n);
}
/* MOVIE_TRACE_FILE=<host path of the movie being played>: every commit is compared with the file. */
unsigned char* g_file; uint64_t g_file_len;

int64_t now() { LARGE_INTEGER q; QueryPerformanceCounter(&q); return q.QuadPart; }

void dump(const char* why)
{
    FILE* f = std::fopen(g_path, "w");
    if (!f) return;
    LARGE_INTEGER fr; QueryPerformanceFrequency(&fr);
    const uint32_t n = g_n.load();
    const uint32_t first = n > kN ? n - kN : 0;
    std::fprintf(f, "# %s; %u events, %u delivers\n", why, n, g_delivers.load());
    const int64_t t0 = g_ev[first & (kN - 1)].t;
    for (uint32_t i = first; i < n; i++) {
        const Ev& e = g_ev[i & (kN - 1)];
        std::fprintf(f, "%10.3f ms tid %5u %-7s %016llX %016llX %016llX %016llX\n",
                     (double)(e.t - t0) * 1000.0 / (double)fr.QuadPart, e.tid, kNames[e.kind],
                     (unsigned long long)e.a, (unsigned long long)e.b, (unsigned long long)e.c, (unsigned long long)e.d);
    }
    std::fclose(f);
    std::fprintf(stderr, "[movie-trace] %s: %u events written to %s\n", why, n - first, g_path);
}

DWORD WINAPI watch(LPVOID)
{
    LARGE_INTEGER fr; QueryPerformanceFrequency(&fr);
    for (;;) {
        Sleep(250);
        const int64_t last = g_last_deliver.load();
        if (last && now() - last > 3 * fr.QuadPart) { dump("no access unit for 3 s"); return 0; }
    }
}

bool on()
{
    int s = g_on.load(std::memory_order_relaxed);
    if (s >= 0) return s != 0;
    static std::atomic<int> once{0};
    if (once.exchange(1)) return false;
    const char* e = std::getenv("MOVIE_TRACE");
    if (e && *e) {
        std::snprintf(g_path, sizeof g_path, "%s", e);
        g_ev = (Ev*)VirtualAlloc(nullptr, sizeof(Ev) * kN, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
        if (g_ev) { HANDLE t = CreateThread(nullptr, 0, watch, nullptr, 0, nullptr); if (t) CloseHandle(t); }
        if (const char* fp = std::getenv("MOVIE_TRACE_FILE")) {
            if (FILE* f = std::fopen(fp, "rb")) {
                _fseeki64(f, 0, SEEK_END); g_file_len = (uint64_t)_ftelli64(f); _fseeki64(f, 0, SEEK_SET);
                g_file = (unsigned char*)VirtualAlloc(nullptr, g_file_len + 16, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
                if (g_file && std::fread(g_file, 1, g_file_len, f) != g_file_len) g_file = nullptr;
                std::fclose(f);
            }
        }
    }
    if (e && *e && g_ev) { g_prev_read_hook = g_ps3_fs_read_hook; g_ps3_fs_read_hook = read_hook; }
    g_on.store(e && *e && g_ev ? 1 : 0);
    return g_on.load() != 0;
}

void ev(uint32_t kind, uint64_t a, uint64_t b, uint64_t c, uint64_t d)
{
    Ev& e = g_ev[g_n.fetch_add(1) & (kN - 1)];
    e.t = now(); e.tid = GetCurrentThreadId(); e.kind = kind; e.a = a; e.b = b; e.c = c; e.d = d;
}
}   // namespace

/* Called once at start-up, after the psarc patches took the read hook (hle_overrides.cpp). */
extern "C" void port_movie_trace_init(void) { (void)on(); }

/* AVI demuxer, chunk header: a = the 8 bytes, b = this+0x128 flag ("header came from the scratch copy"). */
int port_hook_009E70A4(ppu_context* c)
{
    if (!on()) return 0;
    const uint32_t h = (uint32_t)c->gpr[4], self = (uint32_t)c->gpr[3];
    ev(0, vm_read64(h), vm_read32(self + 0x128), h, vm_read32(self + 0xB8));
    return 0;
}

/* Delivery of one access unit: a = track, b = data, c = size, d = copy flag (r8). */
int port_hook_009E00D0(ppu_context* c)
{
    if (!on()) return 0;
    ev(1, (uint32_t)c->gpr[3], (uint32_t)c->gpr[4], c->gpr[5], c->gpr[8]);
    g_delivers.fetch_add(1);
    g_last_deliver.store(now());
    return 0;
}

/* Skip(n): a = n, b = read << 32 | write, c = fill, d = consumed before. */
int port_hook_009F74D0(ppu_context* c)
{
    if (!on()) return 0;
    const uint32_t s = (uint32_t)c->gpr[3], r = s + 0x60;
    ev(2, c->gpr[4], (vm_read64(r + 0x40) << 32) | (uint32_t)vm_read64(r + 0x48), vm_read64(r + 0x58), vm_read64(s + 0x128));
    return 0;
}

/* Commit(n) by the writer: a = n, b = read << 32 | write, c = fill, d = file position before. */
int port_hook_009F4040(ppu_context* c)
{
    if (!on()) return 0;
    const uint32_t r = (uint32_t)c->gpr[3], s = r - 0x60;
    ev(3, c->gpr[4], (vm_read64(r + 0x40) << 32) | (uint32_t)vm_read64(r + 0x48), vm_read64(r + 0x58), vm_read64(s + 0x118));
    /* the bytes just read, against the file: a = first bad offset in the block, b = file position of the
     * block, c = the 8 bytes found there, d = where those 8 bytes are in the file (-1 = nowhere) */
    const uint64_t n = c->gpr[4], pos = vm_read64(s + 0x118);
    if (g_file && n && n <= 0x100000 && pos + n <= g_file_len && vm_read64(r + 0x10) == 0x80000) {
        const uint32_t ea = vm_read32(r + 0x8) + (uint32_t)vm_read64(r + 0x48);
        for (uint64_t i = 0; i < n; i++) {
            if (vm_read8(ea + (uint32_t)i) == g_file[pos + i]) continue;
            unsigned char got[8]; for (int k = 0; k < 8; k++) got[k] = vm_read8(ea + (uint32_t)i + k);
            uint64_t where = ~0ull;
            for (uint64_t o = 0; o + 8 <= g_file_len; o++) if (!std::memcmp(g_file + o, got, 8)) { where = o; break; }
            ev(5, i, pos, vm_read64(ea + (uint32_t)i), where);
            static std::atomic<int> s_lines{0};
            if (s_lines.fetch_add(1) < 40)
                std::fprintf(stderr, "[movie-trace] BAD READ: block at file 0x%llX, wrong from +0x%llX on: bytes of file 0x%llX\n",
                             (unsigned long long)pos, (unsigned long long)i, (unsigned long long)where);
            break;
        }
    }
    return 0;
}

/* Seek(pos): a = pos, b = file position before, c = consumed before, d = end. */
int port_hook_009F7550(ppu_context* c)
{
    if (!on()) return 0;
    const uint32_t s = (uint32_t)c->gpr[3];
    ev(4, c->gpr[4], vm_read64(s + 0x118), vm_read64(s + 0x128), vm_read64(s + 0x120));
    return 0;
}

#else
int port_hook_009E70A4(ppu_context*) { return 0; }
int port_hook_009E00D0(ppu_context*) { return 0; }
int port_hook_009F74D0(ppu_context*) { return 0; }
int port_hook_009F4040(ppu_context*) { return 0; }
int port_hook_009F7550(ppu_context*) { return 0; }
extern "C" void port_movie_trace_init(void) {}
#endif
