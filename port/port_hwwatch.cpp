/* PORT_HWWATCH=<ea>[,<ea>...]: x86 hardware write watchpoints on guest words.
 *
 * Debugging aid (opt-in, no effect when unset). Up to 4 guest addresses (DR0..DR3, 4-byte
 * write watch each). The debug registers are per host thread, so a background thread
 * re-applies them to every thread of the process every 20 ms (guest threads created later get
 * them too). On a hit (single-step exception raised AFTER the store), the vectored handler logs:
 * the guest word's new value, the host RIP mapped to the lifted function that holds it, the
 * next lifted functions on the host stack, the guest lr/thread and a guest back-chain walk.
 *
 *   PORT_HWWATCH_VAL=<hex>   only log hits whose new value equals this (still counts the others)
 *   PORT_HWWATCH_MAX=<n>     stop logging after n hits (default 200)
 *
 * Found the writer of a corrupted glyph-cache link (docs/PROGRESS.md, 2026-11-20).
 */
#ifdef _WIN32
#include <windows.h>
#include <tlhelp32.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ppu_recomp.h"

extern uint8_t* vm_base;
extern "C" PPU_THREAD_LOCAL ppu_context* g_active_ctx;

namespace {
uint32_t s_ea[4];
int      s_n = 0;
uint32_t s_val = 0; bool s_has_val = false;
long     s_max = 200;
volatile long s_hits = 0, s_logged = 0;

struct HG { uintptr_t h; uint32_t g; };
HG*      s_map = nullptr;
uint64_t s_mapn = 0;

void build_map()
{
    s_map = (HG*)malloc((size_t)function_table_count * sizeof(HG));
    if (!s_map) return;
    for (uint64_t k = 0; k < function_table_count; k++) {
        s_map[k].h = (uintptr_t)function_table[k].func;
        s_map[k].g = (uint32_t)function_table[k].addr;
    }
    s_mapn = function_table_count;
    qsort(s_map, (size_t)s_mapn, sizeof(HG), [](const void* a, const void* b) -> int {
        uintptr_t x = ((const HG*)a)->h, y = ((const HG*)b)->h;
        return x < y ? -1 : (x > y ? 1 : 0); });
}

/* host address -> lifted guest function (upper_bound - 1), 0 if outside the lifted code */
uint32_t lookup(uintptr_t h, uintptr_t* off)
{
    if (!s_mapn || h < s_map[0].h) return 0;
    uint64_t lo = 0, hi = s_mapn;
    while (lo < hi) { uint64_t mid = (lo + hi) / 2; if (s_map[mid].h <= h) lo = mid + 1; else hi = mid; }
    if (lo == 0) return 0;
    if (lo == s_mapn && h - s_map[lo - 1].h > 0x200000) return 0;
    if (off) *off = h - s_map[lo - 1].h;
    return s_map[lo - 1].g;
}

uint32_t rd32(uint32_t ea) { uint32_t v; memcpy(&v, vm_base + ea, 4); return _byteswap_ulong(v); }
uint64_t rd64(uint32_t ea) { uint64_t v; memcpy(&v, vm_base + ea, 8); return _byteswap_uint64(v); }

LONG WINAPI hw_veh(EXCEPTION_POINTERS* ep)
{
    if (ep->ExceptionRecord->ExceptionCode != EXCEPTION_SINGLE_STEP) return EXCEPTION_CONTINUE_SEARCH;
    CONTEXT* c = ep->ContextRecord;
    DWORD64 dr6 = c->Dr6;
    if (!(dr6 & 0xF)) return EXCEPTION_CONTINUE_SEARCH;
    c->Dr6 = 0;
    for (int i = 0; i < s_n; i++) {
        if (!(dr6 & (1ull << i))) continue;
        long hit = InterlockedIncrement(&s_hits);
        uint32_t v = rd32(s_ea[i]);
        if (s_has_val && v != s_val) continue;
        if (InterlockedIncrement(&s_logged) > s_max) continue;
        uintptr_t off = 0;
        uint32_t g = lookup((uintptr_t)c->Rip, &off);
        ppu_context* ctx = g_active_ctx;
        char line[1024]; int n = 0;
        n += snprintf(line + n, sizeof line - n,
                      "[hwwatch] #%ld ea=0x%08X new=0x%08X host-tid=%lu rip=func_%08X+0x%llX",
                      hit, s_ea[i], v, GetCurrentThreadId(), g, (unsigned long long)off);
        if (ctx)
            n += snprintf(line + n, sizeof line - n, " guest-tid=%u lr=0x%08X r3=0x%08X sp=0x%08X",
                          (unsigned)ctx->thread_id, (uint32_t)ctx->lr, (uint32_t)ctx->gpr[3],
                          (uint32_t)ctx->gpr[1]);
        /* host stack: lifted callers */
        void* fr[48]; USHORT k = RtlCaptureStackBackTrace(0, 48, fr, NULL);
        n += snprintf(line + n, sizeof line - n, "\n[hwwatch]    host:");
        uint32_t last = g; int got = 0;
        for (USHORT j = 0; j < k && got < 8 && n < (int)sizeof line - 32; j++) {
            uint32_t h = lookup((uintptr_t)fr[j], nullptr);
            if (h && h != last) { n += snprintf(line + n, sizeof line - n, " %08X", h); last = h; got++; }
        }
        /* guest back-chain: 64-bit ABI, saved lr at back+0x10 */
        if (ctx) {
            n += snprintf(line + n, sizeof line - n, "\n[hwwatch]    guest:");
            uint32_t sp = (uint32_t)ctx->gpr[1];
            for (int d = 0; d < 10 && sp && sp < 0xF0000000u && n < (int)sizeof line - 16; d++) {
                uint32_t back = (uint32_t)rd64(sp);
                if (!back || back <= sp) break;
                n += snprintf(line + n, sizeof line - n, " %08X", (uint32_t)rd64(back + 0x10));
                sp = back;
            }
        }
        fprintf(stderr, "%s\n", line);
        fflush(stderr);
    }
    return EXCEPTION_CONTINUE_EXECUTION;
}

void apply(HANDLE h)
{
    CONTEXT c; memset(&c, 0, sizeof c);
    c.ContextFlags = CONTEXT_DEBUG_REGISTERS;
    if (!GetThreadContext(h, &c)) return;
    DWORD64 want7 = 0;
    DWORD64 addr[4] = {0, 0, 0, 0};
    for (int i = 0; i < s_n; i++) {
        addr[i] = (DWORD64)(uintptr_t)(vm_base + s_ea[i]);
        want7 |= 1ull << (i * 2);                 /* local enable */
        want7 |= 1ull << (16 + i * 4);            /* R/W = 01: write */
        want7 |= 3ull << (18 + i * 4);            /* LEN = 11: 4 bytes */
    }
    if (c.Dr0 == addr[0] && c.Dr1 == addr[1] && c.Dr2 == addr[2] && c.Dr3 == addr[3] && c.Dr7 == want7)
        return;
    c.Dr0 = addr[0]; c.Dr1 = addr[1]; c.Dr2 = addr[2]; c.Dr3 = addr[3]; c.Dr7 = want7;
    c.ContextFlags = CONTEXT_DEBUG_REGISTERS;
    SetThreadContext(h, &c);
}

DWORD WINAPI hw_thread(LPVOID)
{
    const DWORD pid = GetCurrentProcessId(), self = GetCurrentThreadId();
    for (;;) {
        HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
        if (snap != INVALID_HANDLE_VALUE) {
            THREADENTRY32 te; te.dwSize = sizeof te;
            if (Thread32First(snap, &te)) do {
                if (te.th32OwnerProcessID != pid || te.th32ThreadID == self) continue;
                HANDLE h = OpenThread(THREAD_SUSPEND_RESUME | THREAD_GET_CONTEXT | THREAD_SET_CONTEXT,
                                      FALSE, te.th32ThreadID);
                if (!h) continue;
                if (SuspendThread(h) != (DWORD)-1) { apply(h); ResumeThread(h); }
                CloseHandle(h);
            } while (Thread32Next(snap, &te));
            CloseHandle(snap);
        }
        Sleep(20);
    }
}
} // namespace

extern "C" void port_hwwatch_start(void)
{
    const char* e = getenv("PORT_HWWATCH");
    if (!e || !*e || !vm_base) return;
    for (const char* p = e; *p && s_n < 4;) {
        char* end; unsigned long v = strtoul(p, &end, 16);
        if (end == p) break;
        s_ea[s_n++] = (uint32_t)v & ~3u;
        p = (*end == ',') ? end + 1 : end;
    }
    if (const char* v = getenv("PORT_HWWATCH_VAL")) { s_val = (uint32_t)strtoul(v, 0, 16); s_has_val = true; }
    if (const char* m = getenv("PORT_HWWATCH_MAX")) s_max = atol(m);
    build_map();
    AddVectoredExceptionHandler(1, hw_veh);
    CreateThread(NULL, 0, hw_thread, NULL, 0, NULL);
    for (int i = 0; i < s_n; i++) fprintf(stderr, "[hwwatch] watching guest 0x%08X (writes)\n", s_ea[i]);
    fflush(stderr);
}
/* PORT_LISTDUMP=<ea>: (called from the PORT_WATCH thread) walk the circular doubly linked list
 * whose sentinel node is at <ea> (next at +0, prev at +4) and print each node's first 0x30
 * bytes, flagging broken prev links and a cycle that does not come back to the sentinel. */
static void port_lock_report(void);
extern "C" void port_listdump(void)
{
    port_lock_report();   /* PORT_LOCKTRACE=1 */
    const char* e = getenv("PORT_LISTDUMP");
    if (!e || !vm_base) return;
    uint32_t sent = (uint32_t)strtoul(e, 0, 16);
    uint32_t prev = sent, cur = rd32(sent);
    fprintf(stderr, "[listdump] sentinel 0x%08X next=0x%08X prev=0x%08X\n", sent, cur, rd32(sent + 4));
    for (int i = 0; i < 200 && cur && cur != sent; i++) {
        char w[200]; int n = 0;
        for (int k = 0; k < 0x30; k += 4) n += snprintf(w + n, sizeof w - n, " %08X", rd32(cur + k));
        fprintf(stderr, "[listdump] %3d 0x%08X%s%s\n", i, cur, w, rd32(cur + 4) != prev ? "  <-- prev mismatch" : "");
        prev = cur; cur = rd32(cur);
    }
    fprintf(stderr, "[listdump] end at 0x%08X (%s)\n", cur, cur == sent ? "sentinel" : "NOT the sentinel");
    fflush(stderr);
}
/* Lock ownership trace (diagnostic). Lifted lock primitives instrumented by hand call
 * port_lock_trace(lock, op, ctx) with op 1 = acquired, 2 = trylock acquired, 0 = released.
 * The last operation per lock is kept (lock-free open addressing); PORT_LOCKTRACE=1 makes the
 * PORT_WATCH report list every traced lock whose word is still non-zero, with its holder. */
namespace {
struct LockRec { volatile long key; uint32_t op, tid, lr, chain[4]; uint64_t seq; };
constexpr int LOCK_SLOTS = 16384;
LockRec s_locks[LOCK_SLOTS];
volatile long long s_lock_seq = 0;
}
extern "C" void port_lock_trace(uint32_t lock, int op, ppu_context* ctx)
{
    if (!lock) return;
    uint32_t h = (lock >> 2) * 2654435761u;
    for (int i = 0; i < LOCK_SLOTS; i++) {
        LockRec* r = &s_locks[(h + i) & (LOCK_SLOTS - 1)];
        long k = r->key;
        if (k == 0) {
            if (InterlockedCompareExchange(&r->key, (long)lock, 0) != 0 && r->key != (long)lock) continue;
        } else if (k != (long)lock) continue;
        r->op = (uint32_t)op;
        r->seq = (uint64_t)InterlockedIncrement64(&s_lock_seq);
        if (op) {
            r->tid = (uint32_t)ctx->thread_id;
            r->lr = (uint32_t)ctx->lr;
            uint32_t sp = (uint32_t)ctx->gpr[1];
            for (int d = 0; d < 4; d++) {
                uint32_t back = sp && sp < 0xF0000000u ? (uint32_t)rd64(sp) : 0;
                r->chain[d] = (back && back > sp) ? (uint32_t)rd64(back + 0x10) : 0;
                sp = back > sp ? back : 0;
            }
        }
        return;
    }
}
static void port_lock_report(void)
{
    static int on = -1;
    if (on < 0) on = getenv("PORT_LOCKTRACE") ? 1 : 0;
    if (!on || !vm_base) return;
    int n = 0;
    for (int i = 0; i < LOCK_SLOTS && n < 40; i++) {
        const LockRec* r = &s_locks[i];
        if (!r->key || !r->op) continue;
        const uint32_t lock = (uint32_t)r->key;
        const uint32_t v = rd32(lock);
        if (!v) continue;
        n++;
        fprintf(stderr, "[locktrace] lock 0x%08X = 0x%X held by guest-tid %u (op %u, seq %llu) lr=0x%08X chain %08X %08X %08X %08X\n",
                lock, v, r->tid, r->op, (unsigned long long)r->seq, r->lr,
                r->chain[0], r->chain[1], r->chain[2], r->chain[3]);
    }
    fprintf(stderr, "[locktrace] %d held lock(s), %lld ops traced\n", n, (long long)s_lock_seq);
}
#else
extern "C" void port_hwwatch_start(void) {}
extern "C" void port_listdump(void) {}
#endif
