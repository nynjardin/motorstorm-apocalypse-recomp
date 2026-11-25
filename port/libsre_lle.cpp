/*
 * Partial LLE of the firmware SPURS/Sync library (libsre.prx).
 *
 * The SPURS LF queue push protocol for direction ANY2ANY is undocumented (even
 * RPCS3 leaves it a TODO), so instead of guessing it, the game's queue imports
 * run Sony's real code, lifted by scripts/lift_libsre.py:
 *   - the relocated image is copied to guest RAM at LIBSRE_BASE,
 *   - the lifted functions are registered by address (indirect calls in libsre,
 *     e.g. the fpSendSignal callback, resolve through the address map),
 *   - selected game imports are bound to lifted exports (BINDINGS below).
 * Everything else in cellSpurs stays HLE. Where the real code reaches into the
 * SPURS kernel, the port answers instead (the lifted bodies are renamed _lle):
 *   - _cellSpursSendSignal          -> the HLE, which owns the taskset scheduler;
 *   - cellSpursLookUpTasksetAddress -> the tasksets recorded below. HLE tasksets
 *     are not SPURS workloads (no wklInfo entry; their tasks see wid 0), so the
 *     real lookup by workload id lands on whatever workload 0 is (Wws_Job here).
 *
 * Firmware-derived code: the lifted source and the image stay local, never
 * distribute them. Without them (PORT_HAVE_LIBSRE undefined) this file only
 * reports that the LLE is unavailable.
 */

#include "ppu_recomp.h"

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <vector>

#ifdef PORT_HAVE_LIBSRE

extern "C" void ps3_hle_register_ctx(uint32_t nid, const char* name, void (*fn)(ppu_context*));
extern "C" void ps3_hle_call(unsigned int nid, ppu_context* ctx);
extern "C" void ppu_register_function(uint64_t addr, void (*fn)(ppu_context*));
extern "C" const func_entry libsre_function_table[];
extern "C" PPU_THREAD_LOCAL void (*g_trampoline_fn)(void*);

/* HLE taskset constructors (libs/spurs/cellSpurs.c), called the way
 * ps3_hle_call calls a registered handler: guest registers r3..r10 in order. */
typedef uint64_t (*hle_generic)(uint64_t, uint64_t, uint64_t, uint64_t,
                                uint64_t, uint64_t, uint64_t, uint64_t);
extern "C" void cellSpursCreateTaskset(void);
extern "C" void cellSpursCreateTasksetWithAttribute(void);
extern "C" void cellSpursCreateTaskset2(void);

/* Lifted exports (libsre_recomp.c, C++ linkage). */
void libsre_func_02017134(ppu_context*);   /* _cellSpursLFQueueInitialize */
void libsre_func_020171B8(ppu_context*);   /* _cellSpursLFQueuePushBody   */

namespace {

constexpr uint32_t LIBSRE_BASE = 0x02000000;   /* free: EBOOT ends 0x0157FE28, heap from 0x10000000 */
constexpr uint32_t LIBSRE_TOC  = 0x02039AB0;
constexpr uint32_t LIBSRE_SIZE = 0x00032340;   /* LOAD segments incl. bss */

constexpr uint32_t CELL_OK                        = 0;
constexpr uint32_t CELL_SPURS_CORE_ERROR_SRCH     = 0x80410705;
constexpr uint32_t CELL_SPURS_CORE_ERROR_NULL_PTR = 0x80410711;

inline void ret(ppu_context* c, uint32_t v) { c->gpr[3] = (uint64_t)(int64_t)(int32_t)v; }

/* Run a lifted libsre export as if the game had called its OPD: libsre's TOC
 * in r2, the caller's r2 and LR restored afterwards. */
template <void (*F)(ppu_context*)>
void call_lle(ppu_context* c)
{
    const uint64_t r2 = c->gpr[2], lr = c->lr;
    c->gpr[2] = LIBSRE_TOC;
    F(c);
    while (g_trampoline_fn) {                   /* DRAIN_TRAMPOLINE */
        void (*tf)(void*) = g_trampoline_fn;
        g_trampoline_fn = nullptr;
        tf(c);
    }
    c->gpr[2] = r2;
    c->lr = lr;
}

/* ---- Tasksets created by the title, per SPURS instance ------------------ */

struct Taskset { uint32_t spurs, taskset; };
std::mutex g_ts_lock;
std::vector<Taskset> g_tasksets;

template <void (*HLE)(void)>
void record_taskset(ppu_context* c)
{
    const uint32_t spurs = (uint32_t)c->gpr[3], taskset = (uint32_t)c->gpr[4];
    const uint64_t r = reinterpret_cast<hle_generic>(HLE)(c->gpr[3], c->gpr[4], c->gpr[5], c->gpr[6],
                                                          c->gpr[7], c->gpr[8], c->gpr[9], c->gpr[10]);
    c->gpr[3] = r;
    if ((uint32_t)r != CELL_OK) return;
    std::lock_guard<std::mutex> g(g_ts_lock);
    for (const Taskset& t : g_tasksets)
        if (t.taskset == taskset) return;
    g_tasksets.push_back({spurs, taskset});
}

const struct { uint32_t nid; const char* name; void (*fn)(ppu_context*); } BINDINGS[] = {
    { 0x011EE38Bu, "_cellSpursLFQueueInitialize",         call_lle<libsre_func_02017134> },
    { 0x8A85674Du, "_cellSpursLFQueuePushBody",           call_lle<libsre_func_020171B8> },
    { 0x52CC6C82u, "cellSpursCreateTaskset",              record_taskset<cellSpursCreateTaskset> },
    { 0xC10931CBu, "cellSpursCreateTasksetWithAttribute", record_taskset<cellSpursCreateTasksetWithAttribute> },
    { 0x4A6465E3u, "cellSpursCreateTaskset2",             record_taskset<cellSpursCreateTaskset2> },
};

bool load_image()
{
    const char* path = std::getenv("PORT_LIBSRE_IMAGE");
    if (!path || !*path) path = PORT_LIBSRE_IMAGE_DEFAULT;
    FILE* f = std::fopen(path, "rb");
    if (!f) { std::fprintf(stderr, "[libsre] cannot open %s\n", path); return false; }
    std::vector<uint8_t> buf(LIBSRE_SIZE);
    const size_t n = std::fread(buf.data(), 1, buf.size(), f);
    std::fclose(f);
    if (n != LIBSRE_SIZE) {
        std::fprintf(stderr, "[libsre] %s: %zu bytes, expected %u (relift?)\n", path, n, LIBSRE_SIZE);
        return false;
    }
    std::memcpy(vm_base + LIBSRE_BASE, buf.data(), buf.size());   /* VM commits on demand */
    return true;
}

} // namespace

/* ---- Lifted bodies replaced by the port (renamed _lle by lift_libsre.py) - */

/* _cellSpursSendSignal(taskset, taskId) */
void libsre_func_020125D8(ppu_context* c)
{
    ps3_hle_call(0xE0A6DBE4u, c);
}

/* cellSpursLookUpTasksetAddress(spurs, u32* taskset, wid). The wid is useless
 * with HLE tasksets (see top); resolve by SPURS instance instead. */
void libsre_func_020134B8(ppu_context* c)
{
    const uint32_t spurs = (uint32_t)c->gpr[3], out = (uint32_t)c->gpr[4], wid = (uint32_t)c->gpr[5];
    if (!out) return ret(c, CELL_SPURS_CORE_ERROR_NULL_PTR);
    uint32_t found = 0, count = 0;
    {
        std::lock_guard<std::mutex> g(g_ts_lock);
        for (const Taskset& t : g_tasksets)
            if (t.spurs == spurs) { if (!count) found = t.taskset; ++count; }
    }
    if (count > 1) {
        static int warned = 0;
        if (warned++ < 4)
            std::fprintf(stderr, "[libsre] LookUpTasksetAddress(spurs=0x%08X wid=%u): %u tasksets, "
                         "using the first (0x%08X) -- ambiguous, see libsre_lle.cpp\n",
                         spurs, wid, count, found);
    }
    if (!count) {
        std::fprintf(stderr, "[libsre] LookUpTasksetAddress(spurs=0x%08X wid=%u): no taskset\n", spurs, wid);
        return ret(c, CELL_SPURS_CORE_ERROR_SRCH);
    }
    vm_write32(out, found);
    ret(c, CELL_OK);
}

extern "C" void port_load_libsre(void)
{
    if (!load_image()) {
        std::fprintf(stderr, "[libsre] LLE disabled: queue imports stay HLE\n");
        return;
    }
    unsigned count = 0;
    for (const func_entry* e = libsre_function_table; e->func; ++e, ++count)
        ppu_register_function(e->addr, e->func);
    for (const auto& b : BINDINGS)
        ps3_hle_register_ctx(b.nid, b.name, b.fn);
    std::printf("[libsre] image at 0x%08X, %u functions, %zu imports bound\n",
                LIBSRE_BASE, count, sizeof(BINDINGS) / sizeof(BINDINGS[0]));
}

#else

extern "C" void port_load_libsre(void)
{
    std::printf("[libsre] not lifted (scripts/lift_libsre.py): queue imports stay HLE\n");
}

#endif
