/* MotorStorm: Apocalypse port -- network: hooks on the title's own online code.
 *
 * Plan and findings: docs/reseau.md. The title links Sony's SCE-RT stack (Net / DME / Medius) and
 * has two matchmaking back ends behind one interface: NetComMatchWan (Medius servers, gone since
 * 2018) and NetComMatchLan (source/online/core/NetComWorlds/NetComWorldsLan.cpp: peer-to-peer
 * host, LAN find by broadcast, no server). Which one runs is the word at NetGlobalData + 0xC40
 * ("LanOrWan"), written by the menus through NetGlobalData/LanOrWan; every retail menu writes 1.
 * func_00378654 turns it into the net mode: > 0 -> mode 2 (Internet, Medius), < 0 -> mode 1
 * (LAN), 0 -> mode 3 (no network: the Net library is never initialised and hosting fails with
 * NetErrorNotInitialized, seen 2026-11-24 when this hook stored 0).
 *
 * The hooks here are entry hooks in lifted functions (scripts/func_hooks.py, port/func_hooks.txt):
 * return 0 = the game's function runs, nonzero = replaced.
 *
 *   PORT_NET_LAN=1   the title's LAN back end instead of the Medius one (default 0 = as shipped)
 */
#include "ppu_recomp.h"     /* ppu_context, vm_read32 / vm_write32 */

#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>

/* ---------------------------------------------------------------------------------------------
 * The title's own debug log (PORT_GAME_LOG).
 * func_00B229CC(format = r3, args = r4..r10, then the caller's parameter save area) is the
 * printf of Evolution's debug output, compiled to an empty variadic stub in the retail build:
 * 4156 call sites still pass it their messages ("NetHostPeerToPeer(): FAIL FAIL FAIL",
 * "Lan::WorldCreate", "(NetError = %d)"...). The hook formats and prints them.
 *   PORT_GAME_LOG=1            every message
 *   PORT_GAME_LOG=<a,b,...>    only messages whose FORMAT contains one of these substrings
 *   PORT_GAME_LOG_MAX=<n>      lines per distinct format string (default 100): per-frame
 *                              messages do not drown the log
 * Lines are prefixed "[game] ". Off (unset or 0): one predictable branch per call.
 * ------------------------------------------------------------------------------------------- */
#include <cstring>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

extern "C" PPU_THREAD_LOCAL void (*g_trampoline_fn)(void*);     /* lifted tail calls (DRAIN_TRAMPOLINE) */

static bool guest_str(uint32_t ea, std::string& out, size_t max = 400)
{
    out.clear();
    if (ea < 0x10000u || ea >= 0xE0000000u) return false;
    for (size_t i = 0; i < max; i++) {
        const uint8_t ch = vm_read8(ea + (uint32_t)i);
        if (!ch) return true;
        out.push_back((ch >= 32 && ch < 127) || ch >= 0xA0 ? (char)ch : (ch == '\n' || ch == '\t') ? ' ' : '?');
    }
    return true;
}

static void chips_save_poll(ppu_context* c);        /* below: the save asked after chips were added */

int port_hook_00B229CC(ppu_context* c)
{
    chips_save_poll(c);                             /* one relaxed load when nothing is due */
    static int s_mode = -1, s_max = 100;            /* 0 off, 1 all, 2 filtered */
    static std::vector<std::string> s_filters;
    static std::mutex s_mu;
    static std::unordered_map<uint32_t, int> s_seen;
    if (s_mode < 0) {
        std::lock_guard<std::mutex> g(s_mu);
        if (s_mode < 0) {
            const char* e = std::getenv("PORT_GAME_LOG");
            int mode = 0;
            if (e && *e && std::strcmp(e, "0")) {
                mode = 1;
                if (std::strcmp(e, "1")) {
                    mode = 2;
                    std::string s(e);
                    for (size_t p = 0; p <= s.size(); ) {
                        const size_t q = s.find(',', p);
                        const std::string part = s.substr(p, q == std::string::npos ? std::string::npos : q - p);
                        if (!part.empty()) s_filters.push_back(part);
                        if (q == std::string::npos) break;
                        p = q + 1;
                    }
                }
            }
            if (const char* m = std::getenv("PORT_GAME_LOG_MAX")) s_max = std::atoi(m);
            s_mode = mode;
        }
    }
    if (!s_mode) return 0;
    const uint32_t fmt_ea = (uint32_t)c->gpr[3];
    std::string fmt;
    if (!guest_str(fmt_ea, fmt) || fmt.empty()) return 0;
    if (s_mode == 2) {
        bool hit = false;
        for (const auto& f : s_filters) if (fmt.find(f) != std::string::npos) { hit = true; break; }
        if (!hit) return 0;
    }
    {
        std::lock_guard<std::mutex> g(s_mu);
        int& n = s_seen[fmt_ea];
        if (n >= s_max) return 0;
        n++;
    }
    /* argument i (0 = the first after the format): r4..r10, then the caller's parameter save area */
    const uint32_t sp = (uint32_t)c->gpr[1];
    auto arg = [&](int i) -> uint64_t {
        return i < 7 ? c->gpr[4 + i] : vm_read64(sp + 0x30u + 8u * (uint32_t)(i + 1));
    };
    std::string out;
    int ai = 0;
    for (size_t i = 0; i < fmt.size(); i++) {
        if (fmt[i] != '%') { out.push_back(fmt[i]); continue; }
        if (i + 1 < fmt.size() && fmt[i + 1] == '%') { out.push_back('%'); i++; continue; }
        std::string spec = "%";
        size_t j = i + 1;
        int longs = 0;
        while (j < fmt.size() && std::strchr("-+ #0123456789.", fmt[j])) spec.push_back(fmt[j++]);
        while (j < fmt.size() && std::strchr("lhzjt", fmt[j])) { if (fmt[j] == 'l') longs++; j++; }
        if (j >= fmt.size()) { out += fmt.substr(i); break; }
        const char conv = fmt[j];
        char buf[512];
        buf[0] = 0;
        if (ai > 23) { out += "<...>"; i = j; continue; }
        switch (conv) {
        case 'd': case 'i':
            spec += "lld";
            std::snprintf(buf, sizeof buf, spec.c_str(), longs >= 1 ? (long long)(int64_t)arg(ai) : (long long)(int32_t)arg(ai));
            ai++; break;
        case 'u': case 'x': case 'X': case 'o':
            spec += "ll"; spec.push_back(conv);
            std::snprintf(buf, sizeof buf, spec.c_str(), longs >= 1 ? (unsigned long long)arg(ai) : (unsigned long long)(uint32_t)arg(ai));
            ai++; break;
        case 'p':
            std::snprintf(buf, sizeof buf, "0x%08X", (uint32_t)arg(ai)); ai++; break;
        case 'c':
            std::snprintf(buf, sizeof buf, "%c", (int)(arg(ai) & 0x7F) >= 32 ? (int)(arg(ai) & 0x7F) : '?'); ai++; break;
        case 'f': case 'g': case 'e': case 'F': case 'G': case 'E': {
            const uint64_t bits = arg(ai++); double d; std::memcpy(&d, &bits, 8);
            spec.push_back(conv);
            std::snprintf(buf, sizeof buf, spec.c_str(), d); break; }
        case 's': {
            std::string s;
            if (!guest_str((uint32_t)arg(ai), s, 200)) s = "<bad ptr>";
            ai++;
            spec.push_back('s');
            std::snprintf(buf, sizeof buf, spec.c_str(), s.c_str()); break; }
        default:
            std::snprintf(buf, sizeof buf, "%%%c", conv); break;
        }
        out += buf;
        i = j;
    }
    while (!out.empty() && (out.back() == ' ' || out.back() == '\r')) out.pop_back();
    std::fprintf(stderr, "[game] %s\n", out.c_str());
    return 0;
}

static int net_lan(void)
{
    static const int v = [] { const char* e = std::getenv("PORT_NET_LAN"); return (e && e[0] == '1') ? 1 : 0; }();
    return v;
}

/* NetGlobalData::SetLanOrWan(this = r3, value = r4), func_0038A8D0.
 * The game's body: logs "LANorWAN set[%d]"; a value > 0 is stored at this + 0xC40; a value <= 0 is
 * stored only while the byte at this + [this + 0xD48] + 0xD3B is not positive (a guard whose
 * meaning is not read yet). With PORT_NET_LAN=1 every write of a non-zero value stores -1 (LAN);
 * a write of 0 (the title leaving its online mode) is kept. */
static std::atomic<uint32_t> s_net_global_data{0};      /* NetGlobalData, for port_net_tick */

int port_hook_0038A8D0(ppu_context* c)
{
    const uint32_t self = (uint32_t)c->gpr[3];
    s_net_global_data.store(self, std::memory_order_relaxed);
    const int32_t asked = (int32_t)c->gpr[4];
    static std::atomic<int> s_n{0};
    const int n = s_n.fetch_add(1);
    if (!net_lan()) {
        if (n < 16) std::fprintf(stderr, "[port-net] LanOrWan <- %d (was %d), lr 0x%08X\n",
                                 asked, (int32_t)vm_read32(self + 0xC40), (uint32_t)c->lr);
        return 0;
    }
    const int32_t was = (int32_t)vm_read32(self + 0xC40);
    const uint32_t idx = vm_read32(self + 0xD48);
    const int32_t stored = asked ? -1 : 0;
    vm_write32(self + 0xC40, (uint32_t)stored);
    if (n < 16)
        std::fprintf(stderr, "[port-net] LanOrWan <- %d asked, %d stored (was %d, guard byte %d), "
                             "NetGlobalData 0x%08X, lr 0x%08X\n",
                     asked, stored, was, (int)(int8_t)vm_read8(self + idx + 0xD3B), self, (uint32_t)c->lr);
    return 1;
}

/* ---------------------------------------------------------------------------------------------
 * The "OTG" community server (motorstorm3ps3.ws.online.scee.com, gone) in LAN mode.
 * Every request the title makes to it is a "community action" object (TicketLoginAction,
 * QueryFormAction, CreateGameAction, UpdatePlayerStatsAction... ~80 of them, pointers at
 * manager + 0xDB70..0xDDC8), run by a small runner that the game logic polls:
 *   action + 0x1BC  name (char*)   + 0x1C0 busy   + 0x1C1 succeeded   + 0x1C2 finished   + 0x1C3 failed
 *   action + 0x1FC  request object    + 0x200 response object (both allocated with the action)
 * (state of a failed QueryFormAction read in a running game: 00 00 01 01; its runner then stays
 * "started, not done": func_003B4B3C only marks it done when + 0x1C1 is set.)
 * Without the server every action ends "completed on error with result OTG_ERROR_GENERAL", and a
 * LAN race never starts (seen 2026-11-24 with two instances):
 *   - after the perks stage, QueryFormLogic (the players' "form", shown on the betting screen)
 *     waits for ever for "logged into OTG" before it even sends its query;
 *   - after the bets, the failure of CreateGameAction is fatal: "Une erreur s'est produite lors
 *     de la creation de la partie", the world is torn down, back to the menu.
 * With PORT_NET_LAN=1 the two answers below are given from here (PORT_LAN_OTG_OK=0: as shipped):
 *   func_002EC270  CommunityAction::Succeeded(this): succeeded OR failed, and
 *   func_002EC280  CommunityAction::HasError(this): 0. A finished action is then a successful
 *                  one whose response object keeps its default (empty) content. (HasError alone
 *                  was not enough: QueryFormLogic then waited for a success that never came.)
 *   func_003B5948  "logged into OTG" (static byte 0x014D9F66, set by a successful
 *                  TicketLoginAction; also QueryFormLogic's enter-phase test, vtable + 0x40): 1.
 * ------------------------------------------------------------------------------------------- */
static int lan_otg_ok(void)
{
    static const int v = [] {
        if (!net_lan()) return 0;
        const char* e = std::getenv("PORT_LAN_OTG_OK");
        return (e && e[0] == '0') ? 0 : 1;
    }();
    return v;
}

int port_hook_002EC280(ppu_context* c)
{
    if (!lan_otg_ok()) return 0;
    const uint32_t self = (uint32_t)c->gpr[3];
    if (vm_read8(self + 0x1C3)) {
        static std::mutex s_mu;
        static std::unordered_map<uint32_t, int> s_seen;
        std::lock_guard<std::mutex> g(s_mu);
        if (s_seen[self]++ == 0) {
            std::string name;
            guest_str(vm_read32(self + 0x1BC), name, 64);
            std::fprintf(stderr, "[port-net] OTG action %s (0x%08X) failed, no server: reported as done (LAN mode)\n",
                         name.c_str(), self);
        }
    }
    c->gpr[3] = 0;
    return 1;
}

int port_hook_002EC270(ppu_context* c)
{
    if (!lan_otg_ok()) return 0;
    const uint32_t self = (uint32_t)c->gpr[3];
    c->gpr[3] = (vm_read8(self + 0x1C1) || vm_read8(self + 0x1C3)) ? 1 : 0;
    return 1;
}

int port_hook_003B5948(ppu_context* c)
{
    if (!lan_otg_ok()) return 0;
    c->gpr[3] = 1;
    return 1;
}

/* ---------------------------------------------------------------------------------------------
 * The online progression (chips = experience, rank) is LOCAL: chunk "form" of the player's profile
 * (AUTOSAVE.DAT), keys player_xp_curr_total / player_xp_prev_total / player_rank_level.
 * func_002BD2D8(xp manager = r3, chips = r4, player = r5) adds the chips a race earned:
 * prev_total = curr_total, curr_total = min(curr_total + chips, cap). Its callers: func_00218E0C
 * ("BankUsersChips": the per-player chip counter of the race, then zeroed), func_002BD428,
 * func_00536DA8... The hook only reports (first 64 calls), and
 *   PORT_XP_BONUS=<n>   adds n chips to the FIRST call of the run: a test knob, to see the rank
 *                       move and the total come back after a restart without winning a race.
 * ------------------------------------------------------------------------------------------- */
/* The title writes the profile when it leaves a race (BEFORE the chips of that race are added)
 * and when it leaves the multiplayer menus: a game closed from the lobby lost the chips of its
 * last race (on the console the server's copy made up for it). So the port asks for one more
 * save, PORT_CHIPS_SAVE_MS (default 2500, 0 = off) after chips were added: the profile object
 * (func_002D932C(manager, player), manager = [[[[0x0144FB4C] + 0x29C] + 0x294] + 0x84]) has the
 * method the title's own transitions use, func_0028FEB8 (virtual + 0x10: it starts the save
 * thread unless a save already runs). The call is made from the debug-printf hook, on the guest
 * thread that added the chips, with every register put back afterwards. */
static std::atomic<ppu_context*> s_save_ctx{nullptr};
static std::atomic<int32_t>      s_save_player{0};
static std::atomic<int64_t>      s_save_due_ms{0};

static int64_t now_ms(void)
{
    return std::chrono::duration_cast<std::chrono::milliseconds>(
               std::chrono::steady_clock::now().time_since_epoch()).count();
}

static void guest_call(void (*fn)(ppu_context*), ppu_context* c)
{
    fn(c);
    while (g_trampoline_fn) {                       /* DRAIN_TRAMPOLINE */
        void (*tf)(void*) = g_trampoline_fn;
        g_trampoline_fn = nullptr;
        tf(c);
    }
}

static void save_profile_now(ppu_context* c, int32_t player)
{
    const uint32_t g = vm_read32(0x0144FB4Cu);
    const uint32_t a = g ? vm_read32(g + 0x29C) : 0;
    const uint32_t b = a ? vm_read32(a + 0x294) : 0;
    const uint32_t mgr = b ? vm_read32(b + 0x84) : 0;
    if (!mgr) return;
    const ppu_context saved = *c;
    c->gpr[3] = mgr; c->gpr[4] = (uint64_t)(int64_t)player; c->lr = 0;
    guest_call(func_002D932C, c);
    const uint32_t profile = (uint32_t)c->gpr[3];
    if (profile >= 0x10000u) {
        c->gpr[3] = profile; c->lr = 0;
        guest_call(func_0028FEB8, c);
    }
    const uint64_t ra = c->reserve_addr, rv = c->reserve_value;
    const int rvalid = c->reserve_valid;
    *c = saved;                                     /* every register as it was */
    c->reserve_addr = ra; c->reserve_value = rv; c->reserve_valid = rvalid;
    std::fprintf(stderr, "[port-net] profile save asked after the chips (player %d, profile 0x%08X)\n", player, profile);
}

static void chips_save_poll(ppu_context* c)
{
    const int64_t due = s_save_due_ms.load(std::memory_order_relaxed);
    if (!due || c != s_save_ctx.load(std::memory_order_relaxed) || now_ms() < due) return;
    int64_t expect = due;
    if (!s_save_due_ms.compare_exchange_strong(expect, 0)) return;
    save_profile_now(c, s_save_player.load(std::memory_order_relaxed));
}

int port_hook_002BD2D8(ppu_context* c)
{
    static std::atomic<int> s_n{0};
    static const int s_bonus = [] { const char* e = std::getenv("PORT_XP_BONUS"); return e ? std::atoi(e) : 0; }();
    static const int s_save_ms = [] { const char* e = std::getenv("PORT_CHIPS_SAVE_MS"); return e ? std::atoi(e) : 2500; }();
    const int n = s_n.fetch_add(1);
    const int32_t chips = (int32_t)c->gpr[4];
    if (n == 0 && s_bonus) c->gpr[4] = (uint64_t)(int64_t)(chips + s_bonus);
    if (n < 64)
        std::fprintf(stderr, "[port-net] chips banked: %d (player %d, lr 0x%08X)%s\n", chips, (int32_t)c->gpr[5],
                     (uint32_t)c->lr, (n == 0 && s_bonus) ? " + PORT_XP_BONUS" : "");
    if (s_save_ms > 0) {
        s_save_ctx.store(c, std::memory_order_relaxed);
        s_save_player.store((int32_t)c->gpr[5], std::memory_order_relaxed);
        s_save_due_ms.store(now_ms() + s_save_ms, std::memory_order_relaxed);
    }
    return 0;
}

/* func_007625C8: the title's save writer (the only caller of cellSaveDataUserAutoSave), reached
 * from func_0028F8A8. The profile is written on game-state transitions only (leaving a race,
 * leaving the multiplayer menus): to find who asks, PORT_SAVE_TRACE=1 prints the guest call
 * chain of the first 24 calls (return addresses read from the stack frames: back chain at
 * [sp], saved LR at [frame + 0x10]). */
int port_hook_007625C8(ppu_context* c)
{
    static const int s_on = [] { const char* e = std::getenv("PORT_SAVE_TRACE"); return (e && e[0] == '1') ? 1 : 0; }();
    static std::atomic<int> s_n{0};
    if (!s_on || s_n.fetch_add(1) >= 24) return 0;
    char line[512];
    int o = std::snprintf(line, sizeof line, "[port-net] save requested: r3 0x%08X r4 0x%08X r5 0x%08X r6 0x%08X, lr 0x%08X <-",
                          (uint32_t)c->gpr[3], (uint32_t)c->gpr[4], (uint32_t)c->gpr[5], (uint32_t)c->gpr[6], (uint32_t)c->lr);
    uint32_t sp = (uint32_t)c->gpr[1];
    for (int i = 0; i < 14 && sp >= 0x10000u && sp < 0xE0000000u && o < (int)sizeof line - 16; i++) {
        const uint32_t next = vm_read32(sp + 4);            /* back chain: 64-bit word, low half */
        if (next <= sp || next - sp > 0x100000u) break;
        o += std::snprintf(line + o, sizeof line - o, " 0x%08X", vm_read32(next + 0x14));   /* saved LR, low half */
        sp = next;
    }
    std::fprintf(stderr, "%s\n", line);
    return 0;
}

/* Called on every vblank (main.cpp). The "logged into OTG" byte is also read in line by other
 * logic (JoinGameLogic: func_0039D6C8, whose PostStats step after a race then neither succeeds
 * nor fails: "Quitting the race!!! because im stuck???" and both players leave the game instead
 * of going back to the lobby, seen 2026-11-24). So the byte itself is held at 1 while the title
 * is in its LAN mode (NetGlobalData + 0xC40 < 0, i.e. inside the multiplayer screens). */
void port_net_tick(void)
{
    if (!lan_otg_ok()) return;
    const uint32_t ngd = s_net_global_data.load(std::memory_order_relaxed);
    if (!ngd) return;
    if ((int32_t)vm_read32(ngd + 0xC40) < 0 && !vm_read8(0x014D9F66u)) {
        static std::atomic<int> s_n{0};
        if (s_n.fetch_add(1) < 8) std::fprintf(stderr, "[port-net] \"logged into OTG\" set (LAN mode)\n");
        vm_write8(0x014D9F66u, 1);
    }
}
