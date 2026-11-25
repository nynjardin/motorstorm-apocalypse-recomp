/* MotorStorm: Apocalypse port -- replacement of files inside ms3.psarc, without touching the disc.
 *
 * The title reads everything (menus, tracks, textures) from one 3.3 GB archive,
 * /dev_bdvd/PS3_GAME/USRDIR/ms3.psarc, with cellFsLseek + cellFsRead. To change a file of it (a
 * menu page: docs/reseau.md) the port rewrites the bytes the title reads:
 *   - scripts/psarc_patch.py compresses each replacement (port/psarc_overlay/<path in archive>)
 *     into the room of the original entry and writes port/psarc_patches.bin: a list of
 *     (file offset, bytes) = the new zlib blocks, the entry's size in the table of contents and
 *     its block sizes;
 *   - here, a read hook of the toolkit (ppu_fs.cpp, local patch #60) copies those bytes over
 *     whatever part of them a read of ms3.psarc covers.
 * The archive on disc is never written. No patch file = no hook.
 *   PORT_PSARC_PATCHES=<file>   the patch list (run.bat: port\psarc_patches.bin when it exists)
 *   PORT_PSARC_PATCHES=0        off
 */
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

extern "C" { extern void (*g_ps3_fs_read_hook)(const char* guest_path, long long pos, unsigned char* data,
                                                unsigned long long n); }

namespace {
struct Patch { uint64_t off; std::vector<unsigned char> bytes; };
std::vector<Patch> g_patches;
unsigned long long g_applied = 0;

void read_hook(const char* path, long long pos, unsigned char* data, unsigned long long n)
{
    const size_t len = std::strlen(path);
    if (len < 9 || std::strcmp(path + len - 9, "ms3.psarc") != 0) return;
    const uint64_t a = (uint64_t)pos, b = a + n;
    for (const Patch& p : g_patches) {
        const uint64_t pa = p.off, pb = p.off + p.bytes.size();
        if (pb <= a || pa >= b) continue;
        const uint64_t lo = pa > a ? pa : a, hi = pb < b ? pb : b;
        std::memcpy(data + (lo - a), p.bytes.data() + (lo - pa), (size_t)(hi - lo));
        if (g_applied++ < 8)
            std::fprintf(stderr, "[port] psarc patch: %llu bytes at 0x%llX (read of %llu at 0x%llX)\n",
                         (unsigned long long)(hi - lo), (unsigned long long)lo, n, (unsigned long long)a);
    }
}
}   // namespace

extern "C" void port_psarc_patch_init(void)
{
    const char* path = std::getenv("PORT_PSARC_PATCHES");
    if (!path || !*path || !std::strcmp(path, "0")) return;
    FILE* f = std::fopen(path, "rb");
    if (!f) { std::fprintf(stderr, "[port] psarc patches: cannot open %s\n", path); return; }
    char magic[8];
    uint32_t count = 0;
    bool ok = std::fread(magic, 1, 8, f) == 8 && !std::memcmp(magic, "PSPATCH1", 8) && std::fread(&count, 4, 1, f) == 1;
    size_t total = 0;
    for (uint32_t i = 0; ok && i < count; i++) {
        uint64_t off = 0;
        uint32_t len = 0;
        ok = std::fread(&off, 8, 1, f) == 1 && std::fread(&len, 4, 1, f) == 1 && len <= (64u << 20);
        if (!ok) break;
        Patch p;
        p.off = off;
        p.bytes.resize(len);
        ok = std::fread(p.bytes.data(), 1, len, f) == len;
        total += len;
        if (ok) g_patches.push_back(std::move(p));
    }
    std::fclose(f);
    if (!ok) { g_patches.clear(); std::fprintf(stderr, "[port] psarc patches: %s is not a valid patch list\n", path); return; }
    if (g_patches.empty()) return;
    g_ps3_fs_read_hook = read_hook;
    std::fprintf(stderr, "[port] psarc patches: %u ranges, %zu bytes, from %s\n", (unsigned)g_patches.size(), total, path);
}
