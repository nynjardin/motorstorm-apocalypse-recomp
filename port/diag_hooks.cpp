/* MotorStorm port -- diagnostic entry hooks (1.06 build only, PORT_DIAG_FENCE=1).
 *
 * The engine's "fence" (1.06 addresses): a Fence object holds an Event at +0xC (vtable 0x01098A08, locks at
 * +8 = guard A and +0xC = value B, B starts at 0 for an event created "initially set"). Wait = func_00639FDC,
 * Signal = func_0063A3C4, Event constructor = func_0063C3E4. Wait takes A and then B (spins until B == 0, then
 * B = 1) and keeps A while it waits; Signal takes A, sets B = 0. So a Wait that finds B == 1 blocks, and the
 * Signal that should release it can never take A: the 1.06 boot stalled like that (docs/PROGRESS.md "Port de
 * l'EBOOT 1.06"). These hooks count Waits and Signals per event and log a Wait that will block.
 * Return 0 always: the game's function runs. Redo scripts/func_hooks.py after a relift. */
#include "ppu_recomp.h"

#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <mutex>
#include <unordered_map>

#ifdef PORT_V106
namespace {
struct EvStat { uint32_t nw = 0, ns = 0, last_set_lr = 0, last_wait_lr = 0; int last_set_tid = 0, last_wait_tid = 0; };
std::mutex g_mu;
std::unordered_map<uint32_t, EvStat> g_ev;

bool diag_on()
{
    static int s = -1;
    if (s < 0) { const char* e = std::getenv("PORT_DIAG_FENCE"); s = (e && *e && *e != '0') ? 1 : 0; }
    return s == 1;
}
}   // namespace

int port_hook_00639FDC(ppu_context* c)
{
    if (!diag_on()) return 0;
    const uint32_t obj = (uint32_t)c->gpr[3], ev = vm_read32(obj + 0xC);
    std::lock_guard<std::mutex> g(g_mu);
    EvStat& s = g_ev[ev];
    s.nw++;
    s.last_wait_lr = (uint32_t)c->lr;
    s.last_wait_tid = (int)c->thread_id;
    const uint32_t B = vm_read32(ev + 0xC), A = vm_read32(ev + 8);
    static std::atomic<int> n{0};
    if (B != 0 && n.fetch_add(1) < 200)
        std::fprintf(stderr, "[fence] BLOCKING WAIT tid=%d this=0x%08X ev=0x%08X A=%u B=%u waits=%u sets=%u lr=0x%08X (last set tid=%d lr=0x%08X, previous wait tid=%d)\n",
                     (int)c->thread_id, obj, ev, A, B, s.nw, s.ns, (uint32_t)c->lr, s.last_set_tid, s.last_set_lr, s.last_wait_tid);
    return 0;
}

int port_hook_0063A3C4(ppu_context* c)
{
    if (!diag_on()) return 0;
    const uint32_t obj = (uint32_t)c->gpr[3], ev = vm_read32(obj + 0xC);
    std::lock_guard<std::mutex> g(g_mu);
    EvStat& s = g_ev[ev];
    s.ns++;
    s.last_set_lr = (uint32_t)c->lr;
    s.last_set_tid = (int)c->thread_id;
    const uint32_t A = vm_read32(ev + 8);
    static std::atomic<int> n{0};
    if (A != 0 && n.fetch_add(1) < 200)
        std::fprintf(stderr, "[fence] SET finds the guard taken tid=%d ev=0x%08X A=%u B=%u waits=%u sets=%u (last wait tid=%d lr=0x%08X)\n",
                     (int)c->thread_id, ev, A, vm_read32(ev + 0xC), s.nw, s.ns, s.last_wait_tid, s.last_wait_lr);
    return 0;
}

int port_hook_0063C3E4(ppu_context* c)
{
    (void)c;
    return 0;
}

/* WORKAROUND (PORT_FENCE_FIX=0 turns it off). func_00E9B9DC is the Event method behind Wait (flag 0) and Signal
 * (flag != 0): both take guard A (+8) first, and Wait keeps A while it spins on B (+0xC). When the main thread
 * calls Wait before the job thread's Signal of the previous round has run, the Signal blocks on A for ever and
 * the game stalls at the first movie (1.06: fence 0x1B65CE90, 749 waits / 747 signals). Nothing in the game
 * prevents that order, only thread timing did on the console. A Signal only has to put B back to 0: do it
 * without the guard (an aligned 32-bit store, as the original release does after its lwsync), so the pending
 * Wait takes B and finishes. Wait is untouched. */
int port_hook_00E9B9DC(ppu_context* c)
{
    static int fix = -1;
    if (fix < 0) { const char* e = std::getenv("PORT_FENCE_FIX"); fix = (e && *e == '0') ? 0 : 1; }
    if (!fix || (c->gpr[4] & 0xFF) == 0) return 0;
    std::atomic_thread_fence(std::memory_order_seq_cst);
    vm_write32((uint32_t)c->gpr[3] + 0xC, 0);
    return 1;
}
#endif
