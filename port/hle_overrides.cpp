/*
 * MotorStorm: Apocalypse (BCES00484) -- firmware imports the ps3recomp HLE
 * library does not implement (or implements wrongly for this title).
 *
 * Registered as context handlers from port_register_hle_overrides(), which
 * stubs.cpp calls from ps3_load_prx_modules() at boot. Context handlers are
 * searched before the generated NID table, so an entry here also overrides a
 * toolkit implementation of the same NID.
 *
 * NIDs were resolved by computing the NID of every REG_FUNC name in RPCS3's
 * modules; behaviour follows RPCS3's implementation of each function.
 */

#include "ppu_recomp.h"     /* ppu_context, vm_read32 / vm_write32 */
#include "title_addrs.h"   /* addresses of the disc EBOOT or of the 1.06 one (PORT_V106) */

#include <direct.h>     /* _mkdir */

#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <string>

extern "C" void ps3_hle_register_ctx(uint32_t nid, const char* name, void (*fn)(ppu_context*));
extern "C" const char* ppu_vfs_root;          /* runtime/ppu/ppu_fs.cpp */
extern "C" void port_psarc_patch_init(void);  /* psarc_patch.cpp */
extern "C" void port_movie_trace_init(void);  /* movie_trace.cpp (MOVIE_TRACE) */
extern "C" void ppu_dump_guest_stack(ppu_context*, const char*);   /* runtime/ppu/ppu_loader.cpp */
extern "C" void cellFontOpenFontFile(void);   /* libs/font/cellFont.c (HLE), called raw */
/* libs/font/cellFont.c (HLE) C functions; the font and metrics pointers are guest EAs. */
extern "C" void cellAdecOpen(void);            /* libs/codec/cellAdec.c (HLE), called raw */
extern "C" int32_t cellFontSetScalePixel(void* font, float w, float h);
extern "C" int32_t cellFontSetupRenderScalePixel(void* font, float w, float h);
extern "C" int32_t cellFontGetRenderCharGlyphMetrics(void* font, uint32_t code, void* metrics);
extern "C" int32_t cellFontRenderCharGlyphImage(void* font, uint32_t code, void* surface, float x, float y,
                                             void* metrics, void* image);
typedef uint64_t (*hle_generic)(uint64_t, uint64_t, uint64_t, uint64_t,
                                uint64_t, uint64_t, uint64_t, uint64_t);

namespace {

constexpr uint32_t CELL_OK                                = 0;
constexpr uint32_t CELL_EINVAL                            = 0x80010002;
constexpr uint32_t CELL_VIDEO_OUT_PRIMARY                 = 0;
constexpr uint32_t CELL_VIDEO_OUT_ERROR_ILLEGAL_PARAMETER = 0x8002b222;
constexpr uint32_t CELL_VIDEO_OUT_ERROR_UNSUPPORTED_VIDEO_OUT = 0x8002b225;
constexpr uint32_t CELL_VIDEO_OUT_ERROR_VALUE_IS_NOT_SET  = 0x8002b228;
constexpr uint32_t CELL_GAME_ERROR_PARAM                  = 0x8002cb07;
constexpr uint32_t CELL_GAME_ERROR_NOAPP                  = 0x8002cb08;
constexpr uint32_t CELL_FONT_ERROR_INVALID_PARAMETER      = 0x80540002;

/* Guest scratch owned by the port: unclaimed main memory past the libsre image
 * (0x02000000..0x02032340, libsre_lle.cpp). */
constexpr uint32_t PORT_SCRATCH_FONT_LIBRARY = 0x02040000;   /* CellFontLibrary, 12 B */
constexpr uint32_t PORT_SCRATCH_FONT_PATH    = 0x02040100;   /* host path, 1 KB */
constexpr uint32_t PORT_SCRATCH_FONT_PATH_SZ = 0x400;

inline uint32_t arg(ppu_context* c, int n) { return (uint32_t)c->gpr[3 + n]; }
inline void ret(ppu_context* c, uint32_t v) { c->gpr[3] = (uint64_t)(int64_t)(int32_t)v; }

/* cellSysutilAvconfExt: cellVideoOutGetScreenSize(u32 videoOut, f32* screenSize)
 * Physical screen size in inches, only meaningful for 3D displays. Not set ->
 * the title falls back to its 2D path. */
void cellVideoOutGetScreenSize(ppu_context* c)
{
    const uint32_t videoOut = arg(c, 0), screenSize = arg(c, 1);
    if (!screenSize)                       return ret(c, CELL_VIDEO_OUT_ERROR_ILLEGAL_PARAMETER);
    if (videoOut != CELL_VIDEO_OUT_PRIMARY) return ret(c, CELL_VIDEO_OUT_ERROR_UNSUPPORTED_VIDEO_OUT);
    ret(c, CELL_VIDEO_OUT_ERROR_VALUE_IS_NOT_SET);
}

/* sysPrxForUser: sys_prx_get_module_list(u64 flags, sys_prx_get_module_list_t* info)
 *   +0x00 u64 size, +0x08 u32 max, +0x0C u32 count, +0x10 u32 idlist (EA)
 * No title-loaded PRX in this port: report an empty list. */
void sys_prx_get_module_list(ppu_context* c)
{
    const uint32_t info = arg(c, 1);
    if (!info || !vm_read32(info + 0x10)) return ret(c, CELL_EINVAL);
    vm_write32(info + 0x0C, 0);
    ret(c, CELL_OK);
}

/* cellGameExec: cellGameGetHomeDataExportPath(char* exportPath)
 * PlayStation Home is defunct: no Home application installed. */
void cellGameGetHomeDataExportPath(ppu_context* c)
{
    ret(c, arg(c, 0) ? CELL_GAME_ERROR_NOAPP : CELL_GAME_ERROR_PARAM);
}

/* cellFontFT: cellFontInitLibraryFreeTypeWithRevision(u64 revisionFlags,
 *     CellFontLibraryConfigFT* config, const CellFontLibrary** lib)
 * The title then opens its fonts through the cellFont HLE, which ignores the
 * library handle; hand back a zeroed CellFontLibrary
 * {u32 libraryType, u32 libraryVersion, u32 SystemClosed} as RPCS3 does. */
void cellFontInitLibraryFreeTypeWithRevision(ppu_context* c)
{
    const uint32_t config = arg(c, 1), lib = arg(c, 2);
    if (!lib) return ret(c, CELL_FONT_ERROR_INVALID_PARAMETER);
    vm_write32(lib, 0);
    if (!config) return ret(c, CELL_FONT_ERROR_INVALID_PARAMETER);
    for (uint32_t o = 0; o < 12; o += 4) vm_write32(PORT_SCRATCH_FONT_LIBRARY + o, 0);
    vm_write32(lib, PORT_SCRATCH_FONT_LIBRARY);
    ret(c, CELL_OK);
}

/* cellFont: cellFontOpenFontFile(CellFont* font, const char* fontPath, u32 subNum, s32 uniqueId)
 * The toolkit HLE fopen()s the GUEST path as is ("/dev_hdd1/x.ttf"), which never
 * exists on the host. Translate it the way runtime/ppu/ppu_fs.cpp host_path()
 * does (the title copies its font into the /dev_hdd1 cache with cellFs, which
 * goes through that mapping), then run the HLE on the host path. */
std::mutex g_font_path_lock;

void guest_to_host_path(const char* guest, char* out, size_t cap)
{
    static const char* const envs[][2] = { {"/dev_hdd0/", "PS3_HDD0_ROOT"}, {"/dev_hdd1/", "PS3_HDD1_ROOT"} };
    for (const auto& e : envs) {
        const size_t n = std::strlen(e[0]);
        const char* root = std::getenv(e[1]);
        if (root && *root && std::strncmp(guest, e[0], n) == 0) {
            std::snprintf(out, cap, "%s/%s", root, guest + n);
            return;
        }
    }
    static const char* const mounts[] = { "/dev_bdvd/", "/app_home/", "/dev_hdd0/", "/dev_hdd1/",
                                          "/host_root/", "/dev_usb000/", "/dev_usb/" };
    const char* rel = guest;
    for (const char* m : mounts)
        if (std::strncmp(guest, m, std::strlen(m)) == 0) { rel = guest + std::strlen(m); break; }
    if (rel == guest && *rel == '/') ++rel;
    std::snprintf(out, cap, "%s/%s", ppu_vfs_root, rel);
}

void port_cellFontOpenFontFile(ppu_context* c)
{
    const uint32_t path_ea = arg(c, 1);
    if (!path_ea) return ret(c, CELL_FONT_ERROR_INVALID_PARAMETER);
    char guest[256];
    size_t i = 0;
    for (; i + 1 < sizeof guest && vm_base[path_ea + i]; ++i) guest[i] = (char)vm_base[path_ea + i];
    guest[i] = 0;

    std::lock_guard<std::mutex> g(g_font_path_lock);
    char* host = reinterpret_cast<char*>(vm_base + PORT_SCRATCH_FONT_PATH);
    guest_to_host_path(guest, host, PORT_SCRATCH_FONT_PATH_SZ);
    for (char* p = host; *p; ++p) if (*p == '\\') *p = '/';
    /* SDK: cellFontOpenFontFile(library, path, subNum, uniqueId, CellFont* font) -- the font
     * is r7. The toolkit's C function is (font, path, subNum, uniqueId): passing r3 opened
     * every font into the LIBRARY struct, the title's CellFonts stayed uninitialised (only one
     * whose memory happened to be 0 resolved, to slot 0) and every glyph of the other fonts
     * failed with INVALID_PARAMETER (small text of the warnings / title screen missing). */
    const uint32_t font = arg(c, 4);
    if (!font) return ret(c, CELL_FONT_ERROR_INVALID_PARAMETER);
    const uint64_t r = reinterpret_cast<hle_generic>(::cellFontOpenFontFile)(
        font, PORT_SCRATCH_FONT_PATH, c->gpr[5], c->gpr[6], 0, 0, 0, 0);
    std::fprintf(stderr, "[port] cellFontOpenFontFile(%s) -> CellFont 0x%08X rc=0x%X\n",
                 guest, font, (unsigned)r);
    c->gpr[3] = r;
}

/* cellSsl: cellSslCertificateLoader(u64 flag, char* buffer, u32 size, u32* required)
 * Bit (i-1) of flag selects root CA i, read from the firmware's
 * /dev_flash/data/cert/CAnn.cer. Called once with `required` to size the buffer,
 * then with the buffer. The toolkit HLE answered required=0, and the title's
 * HTTP client treats that as fatal: "Could not fetch proper cert size" -> exit().
 * Follows RPCS3, including its renumbering of the "normal" set when the
 * Baltimore cert (6) is requested. */
std::string load_root_cert(int id, bool normal_set)
{
    constexpr int Baltimore = 6, Class3G2V2 = 13, ClassSSV4 = 15, EntrustNet = 18, GTECyberTrust = 23;
    int file_id = id;
    if (normal_set && id >= Baltimore && id <= GTECyberTrust) {
        if (id == Baltimore)        file_id = GTECyberTrust;
        else if (id == Class3G2V2)  file_id = Baltimore;
        else if (id == EntrustNet)  file_id = ClassSSV4;
        else                        file_id = id - 1;
    }
    const char* fw = std::getenv("PS3_DEV_FLASH");
    char path[1024];
    std::snprintf(path, sizeof path, "%s/data/cert/CA%02d.cer", fw && *fw ? fw : ".", file_id);
    std::string out;
    if (FILE* f = std::fopen(path, "rb")) {
        char buf[4096];
        size_t n;
        while ((n = std::fread(buf, 1, sizeof buf, f)) > 0) out.append(buf, n);
        std::fclose(f);
    } else {
        std::fprintf(stderr, "[port] cellSslCertificateLoader: missing %s (PS3_DEV_FLASH)\n", path);
    }
    return out;
}

void cellSslCertificateLoader(ppu_context* c)
{
    const uint64_t flag = c->gpr[3];
    const uint32_t buffer = arg(c, 1), size = arg(c, 2), required = arg(c, 3);
    const bool normal_set = (flag >> 5) & 1;   /* Baltimore = cert 6 */
    std::string all;
    for (int i = 1; i <= 58; ++i)
        if ((flag >> (i - 1)) & 1) all += load_root_cert(i, normal_set);
    if (required) {
        vm_write32(required, (uint32_t)all.size());
    } else if (buffer && size) {
        std::memset(vm_base + buffer, 0, size);
        std::memcpy(vm_base + buffer, all.data(), all.size() < size ? all.size() : size);
    }
    std::printf("[port] cellSslCertificateLoader(flag=0x%llX) -> %zu bytes\n",
                (unsigned long long)flag, all.size());
    ret(c, CELL_OK);
}

/* ---- cellFont: rendering setup the toolkit HLE lacks or gets wrong -------
 * The generic NID dispatch only forwards r3..r10, so the float arguments of
 * cellFontSetScalePixel / SetupRenderScalePoint (f1, f2) arrived as whatever
 * the host had in xmm1/xmm2. These handlers take them from fpr[1]/fpr[2] and
 * call the HLE's C functions (which take the guest CellFont EA as a pointer). */
void cellFontSetScalePixel_port(ppu_context* c)
{
    ret(c, (uint32_t)::cellFontSetScalePixel(reinterpret_cast<void*>((uintptr_t)arg(c, 0)),
                                               (float)c->fpr[1], (float)c->fpr[2]));
}

/* cellFontSetupRenderScalePoint(font, f32 w, f32 h): points at the default
 * 72 dpi are pixels; the HLE renderer has one scale, so it is the pixel scale. */
void cellFontSetupRenderScalePoint(ppu_context* c)
{
    if (!arg(c, 0)) return ret(c, CELL_FONT_ERROR_INVALID_PARAMETER);
    ret(c, (uint32_t)::cellFontSetupRenderScalePixel(reinterpret_cast<void*>((uintptr_t)arg(c, 0)),
                                                       (float)c->fpr[1], (float)c->fpr[2]));
}

/* cellFontGetCharGlyphMetrics(font, code, CellFontGlyphMetrics*): same output as
 * the HLE's render metrics (eight BE floats at the current scale). */
void cellFontGetCharGlyphMetrics(ppu_context* c)
{
    if (!arg(c, 0) || !arg(c, 2)) return ret(c, CELL_FONT_ERROR_INVALID_PARAMETER);
    ret(c, (uint32_t)::cellFontGetRenderCharGlyphMetrics(reinterpret_cast<void*>((uintptr_t)arg(c, 0)),
                                                           arg(c, 1),
                                                           reinterpret_cast<void*>((uintptr_t)arg(c, 2))));
}

/* cellFontGetKerning(font, preCode, code, CellFontKerning* {f32 x, f32 y}):
 * no kerning, as RPCS3. */
void cellFontGetKerning(ppu_context* c)
{
    const uint32_t kerning = arg(c, 3);
    if (!kerning) return ret(c, CELL_FONT_ERROR_INVALID_PARAMETER);
    vm_write32(kerning, 0);
    vm_write32(kerning + 4, 0);
    ret(c, arg(c, 0) ? CELL_OK : CELL_FONT_ERROR_INVALID_PARAMETER);
}

/* void cellFontRenderSurfaceInit(surface, buffer, s32 widthByte, s32 pixelSizeByte, s32 w, s32 h)
 * CellFontRenderSurface: buffer, widthByte, pixelSizeByte, width, height, sc_x0, sc_y0, sc_x1, sc_y1. */
void cellFontRenderSurfaceInit(ppu_context* c)
{
    const uint32_t s = arg(c, 0);
    if (!s) return;
    const int32_t w = (int32_t)arg(c, 4), h = (int32_t)arg(c, 5);
    const uint32_t width = w < 0 ? 0u : (uint32_t)w, height = h < 0 ? 0u : (uint32_t)h;
    vm_write32(s + 0x00, arg(c, 1));
    vm_write32(s + 0x04, arg(c, 2));
    vm_write32(s + 0x08, arg(c, 3));
    vm_write32(s + 0x0C, width);
    vm_write32(s + 0x10, height);
    vm_write32(s + 0x14, 0);
    vm_write32(s + 0x18, 0);
    vm_write32(s + 0x1C, width);
    vm_write32(s + 0x20, height);
}

/* void cellFontRenderSurfaceSetScissor(surface, s32 x0, s32 y0, u32 w, u32 h):
 * the rectangle clipped to the surface. */
void cellFontRenderSurfaceSetScissor(ppu_context* c)
{
    const uint32_t s = arg(c, 0);
    if (!s) return;
    const int64_t sw = (int32_t)vm_read32(s + 0x0C), sh = (int32_t)vm_read32(s + 0x10);
    const int64_t x0 = (int32_t)arg(c, 1), y0 = (int32_t)arg(c, 2);
    const int64_t x1 = x0 + arg(c, 3), y1 = y0 + arg(c, 4);
    auto clip = [](int64_t v, int64_t hi) { return (uint32_t)(v < 0 ? 0 : v > hi ? hi : v); };
    vm_write32(s + 0x14, clip(x0, sw));
    vm_write32(s + 0x18, clip(y0, sh));
    vm_write32(s + 0x1C, clip(x1, sw));
    vm_write32(s + 0x20, clip(y1, sh));
}

/* cellFontRenderCharGlyphImage(font, code, surface, f32 x, f32 y, CellFontGlyphMetrics* metrics,
 *                              CellFontImageTransInfo* transInfo)    -- r3 r4 r5 f1 f2 r8 r9
 * Three toolkit bugs made the glyph cache of the title loop forever after the title screen
 * (func_004FFB88 evicting glyphs to place a 3.3e8-pixel-wide one):
 *  - x/y are floats (f1/f2), the generic NID dispatch never passes them;
 *  - the toolkit writes its own 5-word "image" struct, but the SDK's CellFontImageTransInfo is
 *    { Image, imageWidthByte, imageWidth, imageHeight, Surface, surfWidthByte }: the title read
 *    pixelSize (1) as the width of every glyph, and on an early error return nothing at all
 *    (uninitialised stack words as width/height);
 *  - the title passes a surface with no buffer and copies imageHeight rows of imageWidth bytes
 *    from Image (stride imageWidthByte) into its own atlas: the library is expected to hand back
 *    the glyph bitmap it rendered. The toolkit renders only into the caller's surface.
 * So: render the glyph with the toolkit (stb) into a port-owned scratch surface, top-left
 * of the bitmap at (PAD, PAD), and describe that bitmap in transInfo. Slots rotate (8) so a
 * second thread rendering a glyph does not overwrite a bitmap the first is still copying. */
constexpr uint32_t PORT_SCRATCH_GLYPH_SURF = 0x02040A00;   /* 8 x 0x40 B CellFontRenderSurface */
constexpr uint32_t PORT_SCRATCH_GLYPH_BUF  = 0x02080000;   /* 8 x 64 KB, 256x256 alpha bitmaps */
constexpr int      GLYPH_DIM = 256, GLYPH_PAD = 8;

float rd_f32(uint32_t ea) { const uint32_t v = vm_read32(ea); float f; std::memcpy(&f, &v, 4); return f; }

void cellFontRenderCharGlyphImage_port(ppu_context* c)
{
    const uint32_t font = arg(c, 0), code = arg(c, 1), surf = arg(c, 2);
    const float x = (float)c->fpr[1], y = (float)c->fpr[2];
    const uint32_t metrics = arg(c, 5), trans = arg(c, 6);
    if (!font) return ret(c, CELL_FONT_ERROR_INVALID_PARAMETER);

    static std::atomic<uint32_t> s_slot{0};
    const uint32_t slot = s_slot.fetch_add(1) & 7u;
    const uint32_t ss = PORT_SCRATCH_GLYPH_SURF + slot * 0x40u;
    const uint32_t sbuf = PORT_SCRATCH_GLYPH_BUF + slot * (uint32_t)(GLYPH_DIM * GLYPH_DIM);
    const uint32_t mt = metrics ? metrics : ss + 0x24;          /* 8 floats fit in the slot */

    for (uint32_t o = 0; o < 0x20; o += 4) vm_write32(mt + o, 0);
    int32_t rc = ::cellFontGetRenderCharGlyphMetrics(reinterpret_cast<void*>((uintptr_t)font), code,
                                                      reinterpret_cast<void*>((uintptr_t)mt));
    const float gw = rd_f32(mt + 0), gh = rd_f32(mt + 4), hbx = rd_f32(mt + 8), hby = rd_f32(mt + 12);

    int w = 0, h = 0, dx = GLYPH_PAD, dy = GLYPH_PAD;
    if (rc == 0) {
        std::memset(vm_base + sbuf, 0, (size_t)GLYPH_DIM * GLYPH_DIM);
        vm_write32(ss + 0x00, sbuf);
        vm_write32(ss + 0x04, GLYPH_DIM);
        vm_write32(ss + 0x08, 1);
        vm_write32(ss + 0x0C, GLYPH_DIM);
        vm_write32(ss + 0x10, GLYPH_DIM);
        /* the toolkit puts the bitmap at ((int)(x + hbx), (int)(y - hby)) */
        const float rx = (float)GLYPH_PAD - hbx, ry = (float)GLYPH_PAD + hby;
        dx = (int)(rx + hbx); dy = (int)(ry - hby);
        rc = ::cellFontRenderCharGlyphImage(reinterpret_cast<void*>((uintptr_t)font), code,
                                            reinterpret_cast<void*>((uintptr_t)ss), rx, ry, nullptr, nullptr);
        w = gw > 0.f ? (int)gw : 0; h = gh > 0.f ? (int)gh : 0;
        if (dx < 0) dx = 0;
        if (dy < 0) dy = 0;
        if (w > GLYPH_DIM - dx) w = GLYPH_DIM - dx;
        if (h > GLYPH_DIM - dy) h = GLYPH_DIM - dy;
        /* a caller surface with a buffer gets the glyph drawn in place too */
        if (surf && vm_read32(surf))
            ::cellFontRenderCharGlyphImage(reinterpret_cast<void*>((uintptr_t)font), code,
                                           reinterpret_cast<void*>((uintptr_t)surf), x, y, nullptr, nullptr);
    }
    if (rc != 0) { w = 0; h = 0; }
    if (trans) {
        vm_write32(trans + 0x00, w && h ? sbuf + (uint32_t)(dy * GLYPH_DIM + dx) : 0);
        vm_write32(trans + 0x04, GLYPH_DIM);
        vm_write32(trans + 0x08, (uint32_t)w);
        vm_write32(trans + 0x0C, (uint32_t)h);
        const uint32_t sb = surf ? vm_read32(surf) : 0, swb = surf ? vm_read32(surf + 4) : 0;
        const uint32_t spx = surf ? vm_read32(surf + 8) : 0;
        vm_write32(trans + 0x10, sb ? sb + (uint32_t)((int)y * (int)swb + (int)x * (int)spx) : 0);
        vm_write32(trans + 0x14, swb);
    }
    /* first 4 glyphs of every distinct CellFont, and every failed/empty printable glyph */
    static uint32_t s_fonts[16]; static int s_fcnt[16]; static int s_nf = 0, s_bad = 0;
    int fi = -1;
    for (int i = 0; i < s_nf; i++) if (s_fonts[i] == font) fi = i;
    if (fi < 0 && s_nf < 16) { fi = s_nf++; s_fonts[fi] = font; s_fcnt[fi] = 0; }
    const bool bad = (rc != 0 || ((!w || !h) && code > 0x20));
    if ((fi >= 0 && s_fcnt[fi] < 4) || (bad && s_bad < 40)) {
        if (fi >= 0) s_fcnt[fi]++;
        if (bad) s_bad++;
        std::fprintf(stderr, "[port] font 0x%08X (scale %.1fx%.1f) ", font,
                     rd_f32(font + 8), rd_f32(font + 12));
        std::fprintf(stderr, "[port] cellFontRenderCharGlyphImage U+%04X -> %dx%d rc=0x%X (x=%.1f y=%.1f)\n",
                     code, w, h, (unsigned)rc, x, y);
    }
    ret(c, (uint32_t)rc);
}

/* cellFontEndLibrary(library): the library struct lives in port scratch. */
void cellFontEndLibrary(ppu_context* c) { ret(c, CELL_OK); }

/* cellAdec: cellAdecOpenEx(type, CellAdecResourceEx* res, cb, handle) is
 * cellAdecOpen with a SPURS-flavoured resource struct; the HLE ignores the
 * resource argument, so the plain open serves both. */
void cellAdecOpenEx(ppu_context* c)
{
    c->gpr[3] = reinterpret_cast<hle_generic>(::cellAdecOpen)(c->gpr[3], c->gpr[4], c->gpr[5], c->gpr[6], 0, 0, 0, 0);
}

/* cellSysutil: cellSysCacheMount(CellSysCacheParam* {char cacheId[32]; char getCachePath[1024]; ...})
 * The toolkit always answered CELL_SYSCACHE_RET_OK_CLEARED without clearing, so
 * the title rebuilt its whole HDD cache every boot under fresh names (~700
 * files, 100+ MB a run) while the old ones piled up. As on the console (and
 * RPCS3): the same non-empty cache id as last time -> RELAYED, the cache is
 * reused. The last id is kept in <PS3_HDD1_ROOT>/.port_cache_id.
 * A new id answers CLEARED but deletes nothing (files are only ever removed by
 * hand); and without a dedicated PS3_HDD1_ROOT (cache would be the disc dump
 * root) it always answers CLEARED. */
constexpr uint32_t CELL_SYSCACHE_RET_OK_CLEARED = 0, CELL_SYSCACHE_RET_OK_RELAYED = 1;
constexpr uint32_t CELL_SYSCACHE_ERROR_PARAM = 0x8002BC03;

void cellSysCacheMount(ppu_context* c)
{
    const uint32_t p = arg(c, 0);
    if (!p) return ret(c, CELL_SYSCACHE_ERROR_PARAM);
    char id[33] = {};
    for (int i = 0; i < 32 && vm_base[p + i]; ++i) id[i] = (char)vm_base[p + i];
    const char path[] = "/dev_hdd1";
    std::memcpy(vm_base + p + 0x20, path, sizeof path);

    uint32_t result = CELL_SYSCACHE_RET_OK_CLEARED;
    const char* root = std::getenv("PS3_HDD1_ROOT");
    if (root && *root) {
        char marker[1024], last[64] = {};
        std::snprintf(marker, sizeof marker, "%s/.port_cache_id", root);
        if (FILE* f = std::fopen(marker, "rb")) {
            const size_t n = std::fread(last, 1, sizeof last - 1, f);
            last[n] = 0;
            std::fclose(f);
        }
        if (id[0] && std::strcmp(id, last) == 0) result = CELL_SYSCACHE_RET_OK_RELAYED;
        else if (FILE* f = std::fopen(marker, "wb")) { std::fwrite(id, 1, std::strlen(id), f); std::fclose(f); }
    }
    std::printf("[port] cellSysCacheMount(id='%s') -> %s\n", id,
                result == CELL_SYSCACHE_RET_OK_RELAYED ? "RELAYED (cache reused)" : "CLEARED");
    ret(c, result);
}

/* sysPrxForUser: sys_prx_exitspawn_with_level -- the title is quitting (main()
 * returned, often through its fatal-error path). No-op like the toolkit, but log
 * the guest stack: it names the code that gave up. */
void sys_prx_exitspawn_with_level(ppu_context* c)
{
    std::fprintf(stderr, "[port] title is exiting (sys_prx_exitspawn_with_level) lr=0x%08X tid=%u\n",
                 (uint32_t)c->lr, (unsigned)c->thread_id);
    ppu_dump_guest_stack(c, "exitspawn");
    ret(c, CELL_OK);
}

} // namespace

extern "C" void cellfs_add_path_mapping(const char* ps3_prefix, const char* host_path);   /* libs/filesystem/cellFs.c */

/* The toolkit has two filesystem front ends: runtime/ppu/ppu_fs.cpp (open,
 * read, write, stat...) and libs/filesystem/cellFs.c (rename, unlink, mkdir...),
 * each with its own guest->host mapping. cellFs.c had no /dev_hdd1 at all and
 * put /dev_hdd0 under a relative "gamedata/" (i.e. on I:), so the title's HDD
 * cache wrote "chimp" through ppu_fs and its rename to the final name failed
 * with ENOENT: the cache never persisted and 114 MB were rewritten every boot.
 * Point cellFs.c at the same roots as ppu_fs. */
static void port_align_cellfs_mappings(void)
{
    char buf[1024];
    const struct { const char* prefix; const char* env; } hdd[] = {
        { "/dev_hdd0/", "PS3_HDD0_ROOT" }, { "/dev_hdd1/", "PS3_HDD1_ROOT" } };
    for (const auto& m : hdd) {
        const char* root = std::getenv(m.env);
        std::snprintf(buf, sizeof buf, "%s/", root && *root ? root : ppu_vfs_root);   /* ppu_fs: <root>/<rest> */
        cellfs_add_path_mapping(m.prefix, buf);
    }
    if (const char* fw = std::getenv("PS3_DEV_FLASH"); fw && *fw) {
        std::snprintf(buf, sizeof buf, "%s/", fw);
        cellfs_add_path_mapping("/dev_flash/", buf);
    }
}

/* ---- Skip the FMVs (default; PORT_PLAY_VIDEOS=1 plays them) --------------------------
 * The movies (ui/video/*.avi, DivX + audio) stall after a few dozen access units: there is no
 * real video decode yet. Neither "file missing" (CELL_ENOENT: the title shuts down) nor an
 * empty file (the player's error path calls NULL, black screen forever) works. What does: a
 * SHORT BUT VALID copy of the AVI -- original headers, the first PORT_VIDEO_FRAMES (10) video
 * frames with their interleaved audio, rebuilt sizes/frame counts/idx1. The player reaches end
 * of stream, calls cellVdecEndSeq, gets SEQDONE and the title moves on (evologo -> maintitles
 * -> title screen). Copies are written once into $PS3_HDD1_ROOT/port_video/ (on F:, next to the
 * HDD cache) and the open is redirected there. Same logic as scripts/short_avi.py.
 * A fast handler (ps3_hle_register_fast) runs before the toolkit's cellFsOpen: it swaps the
 * path argument (r3) for a port-owned guest string and returns 0, so the normal open runs. */
extern "C" void ps3_hle_register_fast(uint32_t nid, int (*fn)(ppu_context*));
constexpr uint32_t PORT_SCRATCH_VIDEO_PATH = 0x02040600;   /* 4 slots x 128 B guest path */

static uint32_t rd32le(const std::string& d, size_t o) { uint32_t v; std::memcpy(&v, d.data() + o, 4); return v; }
static void wr32le(std::string& d, size_t o, uint32_t v) { std::memcpy(&d[o], &v, 4); }

/* Writes the short copy; false if the source is not a RIFF AVI we understand. */
constexpr size_t PORT_VIDEO_BUDGET = 200u * 1024u;
static bool port_write_short_avi(const std::string& src, const std::string& dst, unsigned keep)
{
    FILE* f = std::fopen(src.c_str(), "rb");
    if (!f) return false;
    std::string d;
    /* Headers + the first frames are all that is kept: read a 4 MB prefix, not a 200 MB film. */
    { char buf[1 << 16]; size_t n; while (d.size() < (4u << 20) && (n = std::fread(buf, 1, sizeof buf, f)) > 0) d.append(buf, n); }
    std::fclose(f);
    if (d.size() < 12 || d.compare(0, 4, "RIFF") || d.compare(8, 4, "AVI ")) return false;
    size_t movi = 0, movi_sz = 0;
    for (size_t o = 12; o + 8 <= d.size();) {
        uint32_t sz = rd32le(d, o + 4);
        if (!d.compare(o, 4, "LIST") && o + 12 <= d.size() && !d.compare(o + 8, 4, "movi")) { movi = o; movi_sz = sz; break; }
        o += 8 + sz + (sz & 1);
    }
    if (!movi) return false;
    std::string head = d.substr(12, movi - 12), body, index;
    unsigned nvid = 0, naud = 0, aud_total = 0; uint64_t aud_bytes = 0;
    for (size_t o = movi + 12, end = movi + 8 + movi_sz; o + 8 <= end && o + 8 <= d.size();) {
        uint32_t sz = rd32le(d, o + 4);
        if (d[o + 2] == 'w' && d[o + 3] == 'b') aud_total++;
        o += 8 + sz + (sz & 1);
    }
    for (size_t o = movi + 12, end = movi + 8 + movi_sz; o + 8 <= end && o + 8 <= d.size();) {
        uint32_t sz = rd32le(d, o + 4);
        const bool vid = d[o + 2] == 'd' && (d[o + 3] == 'c' || d[o + 3] == 'b');
        if (vid && nvid == keep) break;
        /* Byte budget: the player reads the file in 256 KB requests and only starts when the
         * whole short copy arrives in the FIRST one (evologo: 56 KB fine; a 390 KB maintitles
         * copy, read as 256 KB + rest, never started). Keep at least one frame. */
        if (vid && nvid >= 1 && body.size() + 8 + sz > PORT_VIDEO_BUDGET) break;
        if (vid) nvid++; else if (d[o + 2] == 'w' && d[o + 3] == 'b') { naud++; aud_bytes += sz; }
        char e[16]; std::memcpy(e, d.data() + o, 4);
        uint32_t flags = (vid && nvid == 1) ? 0x10u : 0u, pos = 4 + (uint32_t)body.size();
        std::memcpy(e + 4, &flags, 4); std::memcpy(e + 8, &pos, 4); std::memcpy(e + 12, &sz, 4);
        index.append(e, 16);
        body.append(d, o, 8 + sz + (sz & 1));
        o += 8 + sz + (sz & 1);
    }
    if (size_t i = head.find("avih"); i != std::string::npos) wr32le(head, i + 8 + 16, nvid);
    for (size_t j = head.find("strh"); j != std::string::npos; j = head.find("strh", j + 4)) {
        if (!head.compare(j + 8, 4, "vids")) wr32le(head, j + 8 + 32, nvid);
        else if (!head.compare(j + 8, 4, "auds")) {   /* dwLength: chunks (VBR, dwSampleSize 0) or bytes/size */
            const uint32_t ssize = rd32le(head, j + 8 + 44);
            wr32le(head, j + 8 + 32, ssize ? (uint32_t)(aud_bytes / ssize) : naud);
        }
    }
    std::string out = "RIFF0000AVI " + head + "LIST0000movi" + body + "idx10000" + index;
    wr32le(out, 4, (uint32_t)out.size() - 8);
    wr32le(out, 12 + head.size() + 4, 4 + (uint32_t)body.size());
    wr32le(out, 12 + head.size() + 12 + body.size() + 4, (uint32_t)index.size());
    const std::string tmp = dst + ".tmp";
    FILE* o = std::fopen(tmp.c_str(), "wb");
    if (!o) return false;
    const bool ok = std::fwrite(out.data(), 1, out.size(), o) == out.size();
    std::fclose(o);
    if (!ok) return false;
    std::remove(dst.c_str());   /* our own previous copy: Windows rename will not replace */
    return std::rename(tmp.c_str(), dst.c_str()) == 0;
}

static int port_cellFsOpen_skip_videos(ppu_context* c)
{
    const uint32_t ea = static_cast<uint32_t>(c->gpr[3]);
    if (!ea) return 0;
    char path[512];
    size_t i = 0;
    for (; i + 1 < sizeof path && vm_base[ea + i]; ++i) path[i] = (char)vm_base[ea + i];
    path[i] = 0;
    const char* dot = std::strrchr(path, '.');
    const char* name = std::strrchr(path, '/');
    if (!std::strstr(path, "/ui/video/") || !dot || _stricmp(dot, ".avi") != 0) return 0;
    if (std::strncmp(path, "/dev_bdvd/", 10) != 0) return 0;
    const char* hdd1 = std::getenv("PS3_HDD1_ROOT");
    if (!hdd1 || !*hdd1 || std::strlen(name) > 80) return 0;

    static std::mutex m;
    static unsigned slot = 0;
    std::lock_guard<std::mutex> lk(m);
    const std::string dir = std::string(hdd1) + "/port_video";
    /* Every movie is redirected to ONE short copy of the intro logo (evologo_60.avi): the
     * content is never decoded, and a copy of maintitles_60.avi itself (the looping title
     * background) never reaches end of stream -- its player sits idle, and stopping it on
     * START deadlocks (VideoDisplayPS3 never wakes). The logo copy plays out and ends. */
    const std::string host = dir + "/short_logo.avi";
    bool have = false;   /* reuse a copy within the budget (older, larger copies are rewritten) */
    if (FILE* f = std::fopen(host.c_str(), "rb")) {
        std::fseek(f, 0, SEEK_END); have = std::ftell(f) > 0 && std::ftell(f) <= (long)(PORT_VIDEO_BUDGET + 64 * 1024);
        std::fclose(f);
    }
    if (!have) {
        _mkdir(dir.c_str());   /* fails harmlessly when it exists */
        const std::string src = std::string(ppu_vfs_root) + "/PS3_GAME/USRDIR/ui/video/evologo_60.avi";
        if (!port_write_short_avi(src, host, 10)) {
            std::fprintf(stderr, "[port] video skip: could not shorten %s, playing it\n", path);
            return 0;
        }
    }
    const std::string guest = "/dev_hdd1/port_video/short_logo.avi";
    const uint32_t dst = PORT_SCRATCH_VIDEO_PATH + 128u * (slot++ & 3u);
    std::memcpy(vm_base + dst, guest.c_str(), guest.size() + 1);
    std::fprintf(stderr, "[port] video skipped (PORT_PLAY_VIDEOS=1 plays it): %s -> short copy\n", path);
    c->gpr[3] = dst;
    return 0;
}

/* ---- Movies that play: which file (PORT_PLAY_VIDEOS=1) ------------------------------------------
 * Fast handler on cellFsOpen, as above, for /dev_bdvd/PS3_GAME/USRDIR/ui/video/<name>.avi:
 *   - a re-encoded copy <game folder>\recomp\video\<name>.avi (scripts\video_convert.py: H.264, a
 *     few times smaller) is played instead of the disc's file when it exists, so a copy of the game
 *     can do without its 16 GB ui\video folder. PORT_VIDEO_CONVERTED=0 = always the disc's file.
 *   - PORT_VIDEO_AS=<from>:<to> (test): an open of <from>_60.avi plays <to>_60.avi, e.g.
 *     evologo:r01 puts a Festival movie (5.1 sound, 9 languages, subtitles) on the first boot screen.
 * The guest path is swapped for /dev_bdvd/recomp/video/..., which the file layer maps under the game
 * folder like every /dev_bdvd path. */
static int port_cellFsOpen_videos(ppu_context* c)
{
    const uint32_t ea = static_cast<uint32_t>(c->gpr[3]);
    if (!ea) return 0;
    char path[512];
    size_t i = 0;
    for (; i + 1 < sizeof path && vm_base[ea + i]; ++i) path[i] = (char)vm_base[ea + i];
    path[i] = 0;
    static const char kDir[] = "/dev_bdvd/PS3_GAME/USRDIR/ui/video/";
    if (std::strncmp(path, kDir, sizeof kDir - 1) != 0) return 0;
    std::string name = path + sizeof kDir - 1;
    if (name.size() < 5 || name.size() > 64 || name.find('/') != std::string::npos ||
        _stricmp(name.c_str() + name.size() - 4, ".avi") != 0) return 0;

    static std::mutex m;
    static unsigned slot = 0;
    static int conv = -1;
    static std::string as_from, as_to;
    std::lock_guard<std::mutex> lk(m);
    if (conv < 0) {
        const char* e = std::getenv("PORT_VIDEO_CONVERTED");
        conv = !(e && e[0] == '0');
        if (const char* a = std::getenv("PORT_VIDEO_AS"))
            if (const char* colon = std::strchr(a, ':')) { as_from.assign(a, colon - a); as_to = colon + 1; }
    }
    std::string guest;
    if (!as_from.empty() && name == as_from + "_60.avi") {
        name = as_to + "_60.avi";
        guest = std::string(kDir) + name;
    }
    if (conv) {
        const std::string host = std::string(ppu_vfs_root) + "/recomp/video/" + name;
        if (FILE* f = std::fopen(host.c_str(), "rb")) { std::fclose(f); guest = "/dev_bdvd/recomp/video/" + name; }
    }
    if (guest.empty() || guest.size() >= 127) return 0;
    const uint32_t dst = PORT_SCRATCH_VIDEO_PATH + 128u * (slot++ & 3u);
    std::memcpy(vm_base + dst, guest.c_str(), guest.size() + 1);
    static int lines = 0;
    if (lines < 24) { lines++; std::fprintf(stderr, "[port] video: %s -> %s\n", path, guest.c_str()); }
    c->gpr[3] = dst;
    return 0;
}

/* ---------------------------------------------------------------------------------------------
 * Network: the ONE place that answers "offline" (until our own LAN system replaces PSN).
 *
 * cellNetCtlGetState: the toolkit fails the query with NOT_INITIALIZED even after
 * cellNetCtlInit (an LBP workaround). A real console with no link answers CELL_OK and
 * state = CELL_NET_CTL_STATE_Disconnected (0), which is what RPCS3 does with networking off.
 * This title polls it every frame from the menu on. PORT_NETCTL_TOOLKIT=1 = toolkit answer.
 * ------------------------------------------------------------------------------------------- */
static void port_cellNetCtlGetState(ppu_context* c)
{
    const uint32_t state = (uint32_t)c->gpr[3];
    if (!state) { c->gpr[3] = 0x80130107u; /* CELL_NET_CTL_ERROR_INVALID_ADDR */ return; }
    vm_write32(state, 0);   /* CELL_NET_CTL_STATE_Disconnected */
    static std::atomic<int> s_n{0};
    if (s_n.fetch_add(1) < 3) std::fprintf(stderr, "[port] cellNetCtlGetState -> OK, Disconnected\n");
    c->gpr[3] = 0;
}

/* 1.06 EBOOT: its start-up code loads 35 firmware modules and keeps each success in a 34-entry
 * table (the "unload at exit" list); the 35th write lands on the stdio lock word (0x0132B6D8) and
 * the first printf spins for ever. The real firmware refuses module 0x0054 (not a module it has),
 * so the table never overflows there: refuse it the same way. Every other id goes to the toolkit. */
extern "C" int32_t cellSysmoduleLoadModule(uint16_t id);
static void port_cellSysmoduleLoadModule(ppu_context* c)
{
    const uint16_t id = (uint16_t)c->gpr[3];
    if (id == 0x0054) {
        std::fprintf(stderr, "[port] cellSysmoduleLoadModule(0x0054) -> ERROR_UNKNOWN (1.06 start-up table)\n");
        c->gpr[3] = 0x80012002u;   /* CELL_SYSMODULE_ERROR_UNKNOWN */
        return;
    }
    c->gpr[3] = (uint32_t)cellSysmoduleLoadModule(id);
}

/* ---------------------------------------------------------------------------------------------
 * EDGE MLAA skipped (PORT_SKIP_MLAA, default 1; 0 = run it).
 * The title post-processes its frame with Edge's SPU MLAA (edgepost_mlaa_handler.cpp: prepare
 * func_00857DAC, kick func_00857F44, wait func_00857EFC = `while (!ctx[0x2C]) usleep(30)`;
 * 5 tasks of SPU image 6 in 2 tasksets "EDGE MLAA"). It works on the RAM copy of the frame, which
 * this port never displays (toolkit patch #3 copies the GPU render target to the backbuffer), so
 * the ~11 ms a frame the main thread waits for it are wasted. The kick is one _cellSpursSendSignal
 * per task from a single call site (lr 0x00857F9C): answer it by raising the context's "done"
 * word instead of waking the task. The tasks stay parked in WAIT_SIGNAL, as between two frames.
 * The job has a second way of saying "done": the RSX label whose address the title stored in the
 * context (+0x28, func_006BFE90; labels 75 / 76 = 0x200004B0 / 0x200004C0). The title writes 1
 * there before the kick (func_0045F020) and queues SEMAPHORE_ACQUIRE(label == 0) in front of the
 * flip, so the RSX shows the frame only once the SPU has finished it. A skipped kick must write
 * that 0 too, or the walker waits on the label for ever once acquires block (GCM_SEMA_ACQUIRE=1,
 * which the title's own 30 FPS pacing needs: docs/journal/2026-11-23.md).
 * ------------------------------------------------------------------------------------------- */
extern "C" int32_t _cellSpursSendSignal(void* taskset, uint32_t taskId);
static void port_cellSpursSendSignal(ppu_context* c)
{
    static const int s_skip = [] { const char* e = std::getenv("PORT_SKIP_MLAA"); return !(e && e[0] == '0'); }();
    if (s_skip && (uint32_t)c->lr == T_SPURS_KICK_LR) {
        const uint32_t mlaa = (uint32_t)c->gpr[31];
        vm_write32(mlaa + 0x2C, 1);
        if (const uint32_t label = vm_read32(mlaa + 0x28)) vm_write32(label, 0);
        static std::atomic<int> s_n{0};
        if (s_n.fetch_add(1) < 3)
            std::fprintf(stderr, "[port] EDGE MLAA kick skipped (context 0x%08X, taskset 0x%08X task %u)\n",
                         mlaa, (uint32_t)c->gpr[3], (uint32_t)c->gpr[4]);
        c->gpr[3] = 0;
        return;
    }
    c->gpr[3] = (uint64_t)(int64_t)_cellSpursSendSignal((void*)(uintptr_t)(uint32_t)c->gpr[3], (uint32_t)c->gpr[4]);
}

/* ---------------------------------------------------------------------------------------------
 * cellSpursTryJoinTask2(CellSpursTaskset2* taskset, CellSpursTaskId id, s32* exitCode)
 * (NID 0x838FA4F0, not in the toolkit). Polled by the title right after a race has loaded;
 * unresolved, it "succeeded" at once without writing *exitCode.
 * State used (kept by the toolkit runtime, spu_workload.c): the taskset's enabled bitset
 * (+0x30, task 0 = MSB) is cleared when a task exits; a Taskset2's task_exit_code[128]
 * (+0x1980, 16 B each) holds the exit code at +8 and the state in byte 15 (2 = exited,
 * 4 = joined). Busy -> CELL_SPURS_TASK_ERROR_BUSY; exited -> *exitCode, mark joined, CELL_OK.
 * ------------------------------------------------------------------------------------------- */
static void port_cellSpursTryJoinTask2(ppu_context* c)
{
    const uint32_t ts = (uint32_t)c->gpr[3], id = (uint32_t)c->gpr[4], out = (uint32_t)c->gpr[5];
    uint32_t rc;
    int32_t code = 0;
    if (!ts) rc = 0x80410911u;                              /* NULL_POINTER */
    else if (ts & 0x7Fu) rc = 0x80410910u;                  /* ALIGN */
    else if (id >= 128) rc = 0x80410902u;                   /* INVAL */
    else {
        const uint8_t m = (uint8_t)(0x80u >> (id & 7));
        const int enabled = (vm_read8(ts + 0x30 + id / 8) & m) != 0;
        if (enabled) rc = 0x8041090Au;                      /* BUSY: still running */
        else {
            const uint32_t e = ts + 0x1980 + 16u * id;
            const uint8_t st = vm_read8(e + 15) & 0xF;
            if (st == 2 || st == 4) code = (int32_t)vm_read32(e + 8);
            /* vm_write8 is a coherent PPU store: it takes the (non-recursive) lock-line
             * lock itself, so taking it here first deadlocked every SPU atomic. */
            if (st == 2) vm_write8(e + 15, (uint8_t)((vm_read8(e + 15) & 0xF0) | 4));   /* joined */
            if (out) vm_write32(out, (uint32_t)code);
            rc = 0;
        }
    }
    static std::atomic<int> s_n{0};
    const int n = s_n.fetch_add(1);
    if (n < 40 || (rc == 0 && n < 200))
        std::fprintf(stderr, "[port] cellSpursTryJoinTask2(ts=0x%08X id=%u) -> 0x%08X code=%d\n",
                     ts, id, rc, code);
    c->gpr[3] = rc;
}

extern "C" const void* ps3_ffmpeg_get(void);   /* toolkit libs/codec/ffmpeg_runtime.c: NULL = no FFmpeg */

extern "C" void port_register_hle_overrides(void)
{
    ps3_hle_register_ctx(0x838FA4F0u, "cellSpursTryJoinTask2", port_cellSpursTryJoinTask2);
    ps3_hle_register_ctx(0xE0A6DBE4u, "_cellSpursSendSignal", port_cellSpursSendSignal);
    if (!std::getenv("PORT_NETCTL_TOOLKIT"))
        ps3_hle_register_ctx(0x8B3EBA69u, "cellNetCtlGetState", port_cellNetCtlGetState);
    /* The movies play when PORT_PLAY_VIDEOS is set and not 0 (run.bat / portable.cpp: 1) AND the
     * toolkit found FFmpeg (avcodec-NN.dll beside the exe): without a decoder they stall, so they
     * are skipped (short copy) instead. docs\hle.md "Movies". */
    {
        const char* pv = std::getenv("PORT_PLAY_VIDEOS");
        bool play = pv && *pv && std::strcmp(pv, "0") != 0;
        if (play && !ps3_ffmpeg_get()) {
            std::fprintf(stderr, "[port] PORT_PLAY_VIDEOS set but FFmpeg not found: movies skipped\n");
            play = false;
        }
        ps3_hle_register_fast(0x718BF5F8u /* cellFsOpen */, play ? port_cellFsOpen_videos : port_cellFsOpen_skip_videos);
        /* The title looks for "<name>_60.avi" with cellFsStat before it opens it (and falls back to
         * "<name>.avi", which no disc has, then waits for ever): a copy of the game without ui\video
         * must answer for the re-encoded file there too. Same path swap (r3). */
        if (play) ps3_hle_register_fast(0x7DE6DCEDu /* cellFsStat */, port_cellFsOpen_videos);
    }
    /* run.bat redirects stdout to a file: fully buffered, so whatever the HLE
     * printf'd last was lost when a run was killed, and the log looked like the
     * title had stopped earlier than it had. stderr is already unbuffered. */
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    port_align_cellfs_mappings();
    port_psarc_patch_init();
    port_movie_trace_init();
    ps3_hle_register_ctx(0xA2C7BA64u, "sys_prx_exitspawn_with_level",   sys_prx_exitspawn_with_level);
    ps3_hle_register_ctx(0xFAA275A4u, "cellVideoOutGetScreenSize",      cellVideoOutGetScreenSize);
    ps3_hle_register_ctx(0xA5D06BF0u, "sys_prx_get_module_list",        sys_prx_get_module_list);
    ps3_hle_register_ctx(0x59B1EDE1u, "cellGameGetHomeDataExportPath",  cellGameGetHomeDataExportPath);
    ps3_hle_register_ctx(0x7A0A83C4u, "cellFontInitLibraryFreeTypeWithRevision",
                         cellFontInitLibraryFreeTypeWithRevision);
    ps3_hle_register_ctx(0x0A7306A4u, "cellFontOpenFontFile",           port_cellFontOpenFontFile);
    ps3_hle_register_ctx(0x571AFACAu, "cellSslCertificateLoader",       cellSslCertificateLoader);
    ps3_hle_register_ctx(0x297F0E93u, "cellFontSetScalePixel",          cellFontSetScalePixel_port);
    ps3_hle_register_ctx(0x4D19C631u, "cellFontSetupRenderScalePoint",  cellFontSetupRenderScalePoint);
    ps3_hle_register_ctx(0xD8EAEE9Fu, "cellFontGetCharGlyphMetrics",    cellFontGetCharGlyphMetrics);
    ps3_hle_register_ctx(0x06BE743Du, "cellFontGetKerning",             cellFontGetKerning);
    ps3_hle_register_ctx(0x90B9465Eu, "cellFontRenderSurfaceInit",      cellFontRenderSurfaceInit);
    ps3_hle_register_ctx(0xB422B005u, "cellFontRenderSurfaceSetScissor", cellFontRenderSurfaceSetScissor);
    ps3_hle_register_ctx(0x40D40544u, "cellFontEndLibrary",             cellFontEndLibrary);
    ps3_hle_register_ctx(0x88BE4799u, "cellFontRenderCharGlyphImage",   cellFontRenderCharGlyphImage_port);
    ps3_hle_register_ctx(0x8B5551A4u, "cellAdecOpenEx",                 cellAdecOpenEx);
    ps3_hle_register_ctx(0x1E7BFF94u, "cellSysCacheMount",              cellSysCacheMount);
    ps3_hle_register_ctx(0x32267A31u, "cellSysmoduleLoadModule",        port_cellSysmoduleLoadModule);
    std::printf("[port] HLE overrides registered (17)\n");
}
