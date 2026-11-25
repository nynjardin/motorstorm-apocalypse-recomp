# Applies local toolkit patch #43 (GEO_CACHE) to ps3recomp/libs/video/rsx_d3d12_backend.c.
#
#   python scripts/geo_cache_patch.py [--check]
#
# GEO_CACHE=1: the converted vertices and triangle-list indices of an indexed batch (compact
# layout) are kept in a persistent GPU buffer and reused, in the same frame and in later ones,
# while the batch's source bytes (its indices and the vertex arrays they reach) hash the same.
# Why: VTX_REUSE_STATS (patch #42) showed that ~100 % of a race frame's indexed geometry is byte
# for byte something already converted (37 % earlier in the same frame, 63 % the frame before),
# and converting it was half of the FIFO thread, which bounds the frame on the start line.
# Needs patch #42 applied first (it anchors on it). Idempotent.
# Backup of the file before patches #42/#43: E:\ms_perf\bak_1123_fastfloat\rsx_d3d12_backend.c.
import io, sys

P = r'I:/Projets/Recomp/ps3recomp/libs/video/rsx_d3d12_backend.c'
s = io.open(P, encoding='utf-8', newline='').read()
if 'GEO_CACHE' in s:
    print('already patched'); sys.exit(0)
nl = '\r\n' if '\r\n' in s else '\n'
s = s.replace('\r\n', '\n')

def rep(old, new, count=1):
    global s
    assert s.count(old) == count, (s.count(old), old[:90])
    s = s.replace(old, new)

# ---- 1. record field -------------------------------------------------------------------------
rep('''    u32   vmask;
    u32   cst_off;
''', '''    u32   vmask;
    u32   cst_off;
    /* GEO_CACHE (patch #43): this compact indexed record draws from the persistent geometry
     * buffers (vb_byte_offset / ib_first index s_geo.vb / s_geo.ib, not the frame's halves);
     * cst_off stays in the frame's vertex buffer. Only read when indexed && vmask. */
    int   geo;
''')

# ---- 2. globals ------------------------------------------------------------------------------
rep('''static u64 s_req_verts = 0, s_req_draws = 0, s_drop_draws = 0;
''', '''static u64 s_req_verts = 0, s_req_draws = 0, s_drop_draws = 0;

/* GEO_CACHE=1 (MotorStorm local patch #43): persistent cache of converted indexed geometry.
 * A race frame of MotorStorm Apocalypse issues 4000-8000 indexed batches, and nearly all of
 * them are byte for byte what an earlier draw already converted (same index range, same vertex
 * arrays, same layout): a third earlier in the same frame (shadow / depth / colour passes), the
 * rest in the previous frame. Converting them again was half of the FIFO thread's time.
 * An entry is one batch that starts an indexed run: key = where its indices and vertex arrays
 * are and how they are laid out; content = hashes of those source bytes, checked at EVERY use
 * (the guest may rewrite a buffer in place at any time); data = the compact vertices and the
 * triangle-list indices, in two persistent upload buffers the record then draws from.
 * A run of several batches (one BEGIN/END, strips continuing across DRAW_INDEX_ARRAY commands)
 * is one entry with one GeoBat per batch: built batch by batch while the run goes on, and
 * replayed batch by batch, each one checked, the record's index count growing as they match.
 * Anything unusual takes the per-frame path as before and marks its entry unusable: content
 * that changed more than twice (twice, the entry is built again), an attribute the hash cannot read as a flat range, a run that goes on past or
 * differs from what the entry holds (the record is then rebuilt in the frame buffers,
 * geo_replay).
 * Buffers full: no new entries for the rest of the frame, then three frames without the cache
 * (so that no frame in flight still draws from it) and it restarts empty.
 * GEO_CACHE_MB=<n> vertex buffer size (default 512, the index buffer is an eighth of it);
 * GEO_STATS=<frames> prints hits / builds / fallbacks and MB hashed per frame. */
typedef struct GeoBat {          /* one DRAW_INDEX_ARRAY batch of an entry's run */
    u64 hix, hvx;                /* hashes of its index bytes and of the vertex bytes they reach */
    u32 first, count;
    u32 lo, hi;                  /* lowest and highest vertex index */
    u32 cum_icount, pad;         /* triangle-list indices of the run up to and including it */
} GeoBat;
typedef struct GeoEnt {
    u64 key;                     /* of the run's first batch */
    u32 vb_base;                 /* its storage in s_geo.vb (an unused 256-byte block, then the vertices) */
    u32 vb_off, vcount, ib_off, icount;
    u32 bat0, nbat;              /* its batches in s_geo.bat */
    u32 frame;                   /* last frame it was used in */
    u32 state;                   /* 0 free, 1 ready, 2 unusable */
    u32 nchg, pad;               /* times its content was found changed and it was built again */
} GeoEnt;
#define GEO_BITS 18
#define GEO_BAT_CAP (1u << 19)
static struct {
    int on;                       /* -1 unread, 0 off, 1 on */
    ID3D12Resource *vb_res, *ib_res;
    u8*  vb; u32* ib;
    u64  vb_gpu, ib_gpu;
    u32  vb_cap, vb_used;         /* bytes */
    u32  ib_cap, ib_used;         /* indices */
    GeoEnt* tab;
    GeoBat* bat; u32 bat_used;
    u32  frame;
    int  full, drain;
    /* the last record, when it came from the cache: its entry and how many of the entry's
     * batches the run has consumed so far (what a continuation batch is checked against) */
    int  last_valid; u32 last_frame, last_draw, last_prim, last_vmask, last_next;
    GeoEnt* last_ent;
    GeoEnt* open_ent;             /* entry still being built: the run state of upload_prim_vp_ix is its own */
    int  stats; u32 st_frames, st_resets;
    u64  st_hit, st_build, st_changed, st_multi, st_unread, st_skip, st_hashed, st_idx_hit, st_idx_all;
} s_geo = { -1 };
/* upload_prim_vp_ix writes here instead of the frame's halves while geo_convert runs */
static u8*  s_geo_dst_vb; static u64 s_geo_dst_vb_cap;
static u32* s_geo_dst_ib; static u32 s_geo_dst_ib_cap;
static int geo_on(void)
{
    if (s_geo.on < 0) {
        const char* e = getenv("GEO_CACHE");
        s_geo.on = (e && e[0] == '1') ? 1 : 0;
        if (s_geo.on) {
            const char* m = getenv("GEO_CACHE_MB");
            int mb = m ? atoi(m) : 512;
            if (mb < 64) mb = 64;
            if (mb > 2048) mb = 2048;
            s_geo.vb_cap = (u32)mb << 20;
            s_geo.ib_cap = ((u32)mb << 20) / 8u / 4u;
            const char* st = getenv("GEO_STATS");
            s_geo.stats = st ? atoi(st) : 0;
            s_geo.tab = (GeoEnt*)calloc((size_t)1 << GEO_BITS, sizeof(GeoEnt));
            s_geo.bat = (GeoBat*)malloc((size_t)GEO_BAT_CAP * sizeof(GeoBat));
            if (!s_geo.tab || !s_geo.bat) s_geo.on = 0;
            s_geo.frame = 8;
        }
    }
    return s_geo.on;
}
''')

# ---- 3. buffers ------------------------------------------------------------------------------
rep('''            fprintf(stderr, "[VPIB] allocation failed -- indexed draws are expanded to lists%c", 10);
''', '''            fprintf(stderr, "[VPIB] allocation failed -- indexed draws are expanded to lists%c", 10);

        if (geo_on()) {   /* GEO_CACHE: persistent geometry buffers (UPLOAD, persistently mapped) */
            void* gv = NULL; void* gi = NULL;
            bd.Width = s_geo.vb_cap;
            if (SUCCEEDED(s_d3d.device->lpVtbl->CreateCommittedResource(s_d3d.device, &hp,
                    D3D12_HEAP_FLAG_NONE, &bd, D3D12_RESOURCE_STATE_GENERIC_READ, NULL,
                    &IID_ID3D12Resource, (void**)&s_geo.vb_res)))
                s_geo.vb_res->lpVtbl->Map(s_geo.vb_res, 0, &nr, &gv);
            bd.Width = (u64)s_geo.ib_cap * 4;
            if (gv && SUCCEEDED(s_d3d.device->lpVtbl->CreateCommittedResource(s_d3d.device, &hp,
                    D3D12_HEAP_FLAG_NONE, &bd, D3D12_RESOURCE_STATE_GENERIC_READ, NULL,
                    &IID_ID3D12Resource, (void**)&s_geo.ib_res)))
                s_geo.ib_res->lpVtbl->Map(s_geo.ib_res, 0, &nr, &gi);
            if (gv && gi) {
                s_geo.vb = (u8*)gv; s_geo.ib = (u32*)gi;
                s_geo.vb_gpu = s_geo.vb_res->lpVtbl->GetGPUVirtualAddress(s_geo.vb_res);
                s_geo.ib_gpu = s_geo.ib_res->lpVtbl->GetGPUVirtualAddress(s_geo.ib_res);
                fprintf(stderr, "[geo] GEO_CACHE=1: %u MB of vertices, %u M indices%c",
                        (unsigned)(s_geo.vb_cap >> 20), (unsigned)(s_geo.ib_cap >> 20), 10);
            } else {
                fprintf(stderr, "[geo] GEO_CACHE: buffer allocation failed, cache off%c", 10);
                s_geo.on = 0;
            }
        }
''')

# ---- 4. per-frame record reset ---------------------------------------------------------------
rep('''s_d3d.draws[_i].indexed = 0; s_d3d.draws[_i].vmask = 0; }''',
    '''s_d3d.draws[_i].indexed = 0; s_d3d.draws[_i].vmask = 0; s_d3d.draws[_i].geo = 0; }''', 3)

# ---- 5. FP_VSUM reads the frame's vertex buffer: not for cached records -----------------------
rep('''              if (r->is_clear || r->is_copy || !r->is_vp || r->fp_addr != (u32)fpv) continue;
''', '''              if (r->is_clear || r->is_copy || !r->is_vp || r->fp_addr != (u32)fpv) continue;
              if (r->indexed && r->vmask && r->geo) continue;   /* GEO_CACHE: not in this buffer */
''')

# ---- 6. render: which buffers a compact indexed record draws from -----------------------------
rep('''                if (dr->indexed) {
                    if (!ib_bound) {
                        D3D12_INDEX_BUFFER_VIEW ibv;
                        ibv.BufferLocation = s_d3d.vp_ib->lpVtbl->GetGPUVirtualAddress(s_d3d.vp_ib)
                                           + (u64)s_d3d.vp_parity * VP_MAX_INDICES * 4;
                        ibv.SizeInBytes = VP_MAX_INDICES * 4;
                        ibv.Format = DXGI_FORMAT_R32_UINT;
                        s_d3d.cmd_list->lpVtbl->IASetIndexBuffer(s_d3d.cmd_list, &ibv);
                        ib_bound = 1;
                    }
''', '''                if (dr->indexed) {
                    const int geo_rec = dr->vmask && dr->geo && s_geo.vb_gpu;   /* GEO_CACHE record */
                    if (ib_bound != (geo_rec ? 2 : 1)) {
                        D3D12_INDEX_BUFFER_VIEW ibv;
                        if (geo_rec) {
                            ibv.BufferLocation = s_geo.ib_gpu;
                            ibv.SizeInBytes = s_geo.ib_cap * 4u;
                        } else {
                            ibv.BufferLocation = s_d3d.vp_ib->lpVtbl->GetGPUVirtualAddress(s_d3d.vp_ib)
                                               + (u64)s_d3d.vp_parity * VP_MAX_INDICES * 4;
                            ibv.SizeInBytes = VP_MAX_INDICES * 4;
                        }
                        ibv.Format = DXGI_FORMAT_R32_UINT;
                        s_d3d.cmd_list->lpVtbl->IASetIndexBuffer(s_d3d.cmd_list, &ibv);
                        ib_bound = geo_rec ? 2 : 1;
                    }
''')
rep('''                            cv[0].BufferLocation = vbv.BufferLocation + dr->vb_byte_offset;
''', '''                            cv[0].BufferLocation = (geo_rec ? s_geo.vb_gpu : vbv.BufferLocation) + dr->vb_byte_offset;
''')

# ---- 7. frame boundary -----------------------------------------------------------------------
rep('''static HANDLE s_as_go, s_as_done, s_as_thread;
static volatile LONG s_as_busy;
static void render_frame(void);
''', '''/* GEO_CACHE: once per recorded frame, on the recording side. */
static void geo_frame(void)
{
    if (s_geo.on <= 0 || !s_geo.vb) return;
    s_geo.frame++;
    s_geo.last_valid = 0;
    s_geo.open_ent = NULL;
    if (s_geo.drain > 0) {
        if (--s_geo.drain == 0) {
            memset(s_geo.tab, 0, ((size_t)1 << GEO_BITS) * sizeof(GeoEnt));
            s_geo.vb_used = 0; s_geo.ib_used = 0; s_geo.bat_used = 0; s_geo.full = 0; s_geo.st_resets++;
        }
    } else if (s_geo.full) {
        s_geo.drain = 3;
    }
    if (s_geo.stats > 0 && ++s_geo.st_frames >= (u32)s_geo.stats) {
        const double f = (double)s_geo.st_frames;
        fprintf(stderr, "[geo] per frame: %.0f hits, %.0f builds, %.0f changed, %.0f replayed, %.0f unreadable,"
                        " %.0f known-unusable | indices from the cache %.1f%% | %.1f MB hashed | %u/%u MB vtx,"
                        " %u/%u k idx | resets %u%c",
                (double)s_geo.st_hit / f, (double)s_geo.st_build / f, (double)s_geo.st_changed / f,
                (double)s_geo.st_multi / f, (double)s_geo.st_unread / f, (double)s_geo.st_skip / f,
                s_geo.st_idx_all ? 100.0 * (double)s_geo.st_idx_hit / (double)s_geo.st_idx_all : 0.0,
                (double)s_geo.st_hashed / f / 1048576.0,
                (unsigned)(s_geo.vb_used >> 20), (unsigned)(s_geo.vb_cap >> 20),
                (unsigned)(s_geo.ib_used >> 10), (unsigned)(s_geo.ib_cap >> 10), (unsigned)s_geo.st_resets, 10);
        s_geo.st_frames = 0;
        s_geo.st_hit = s_geo.st_build = s_geo.st_changed = s_geo.st_multi = s_geo.st_unread = s_geo.st_skip = 0;
        s_geo.st_hashed = s_geo.st_idx_hit = s_geo.st_idx_all = 0;
    }
}

static HANDLE s_as_go, s_as_done, s_as_thread;
static volatile LONG s_as_busy;
static void render_frame(void);
''')
rep('''    vrs_frame();
    if (!rsx_async_on()) { render_frame(); return; }
''', '''    vrs_frame();
    geo_frame();
    if (!rsx_async_on()) { render_frame(); return; }
''')

# ---- 8. upload_prim_vp_ix: optional destination override --------------------------------------
rep('''    if (s_d3d.vp_ib_offset + maxidx > VP_MAX_INDICES) return 0;
    if (!s_ix_stamp) {''', '''    if (s_d3d.vp_ib_offset + maxidx > (s_geo_dst_vb ? s_geo_dst_ib_cap : VP_MAX_INDICES)) return 0;
    if (!s_ix_stamp) {''')
rep('''    VPSlot* vb = (VPSlot*)((u8*)s_d3d.vp_vb_mapped + (u64)s_d3d.vp_parity * MAX_VERTICES * VP_VERT_STRIDE);
    const u64 vb_cap = (u64)MAX_VERTICES * VP_VERT_STRIDE;
    if (!cont) {
        /* Compact: the constant block first''', '''    /* GEO_CACHE (geo_convert): the run goes to a persistent entry instead of the frame's halves */
    VPSlot* vb = s_geo_dst_vb ? (VPSlot*)s_geo_dst_vb
               : (VPSlot*)((u8*)s_d3d.vp_vb_mapped + (u64)s_d3d.vp_parity * MAX_VERTICES * VP_VERT_STRIDE);
    const u64 vb_cap = s_geo_dst_vb ? s_geo_dst_vb_cap : (u64)MAX_VERTICES * VP_VERT_STRIDE;
    if (!cont) {
        /* Compact: the constant block first''')
rep('''    u32* ib = (u32*)s_d3d.vp_ib_mapped + (u64)s_d3d.vp_parity * VP_MAX_INDICES + s_d3d.vp_ib_offset;
    const int local = ((state->index_array_dma & 0xF) == 0);
    const u8* ip = vm_base + cellGcmResolveLocated(local, state->index_array_offset);
    const int sixteen = (((state->index_array_dma >> 4) & 0xF) == 1);
    /* RPCS3 restart_index_enabled()''', '''    u32* ib = s_geo_dst_vb ? s_geo_dst_ib + s_d3d.vp_ib_offset
            : (u32*)s_d3d.vp_ib_mapped + (u64)s_d3d.vp_parity * VP_MAX_INDICES + s_d3d.vp_ib_offset;
    const int local = ((state->index_array_dma & 0xF) == 0);
    const u8* ip = vm_base + cellGcmResolveLocated(local, state->index_array_offset);
    const int sixteen = (((state->index_array_dma >> 4) & 0xF) == 1);
    /* RPCS3 restart_index_enabled()''')

# ---- 9. the cache itself, before d3d12_draw_indexed -------------------------------------------
rep('''static void d3d12_draw_indexed(void* ud, u32 primitive, u32 first, u32 count)
{
''', '''/* ---- GEO_CACHE (patch #43): see s_geo ---- */
static inline u64 geo_rotl(u64 x, int r) { return (x << r) | (x >> (64 - r)); }
#define GEO_K 0x9FB21C651E98DF25ull
/* Four independent lanes, 32 bytes a step: the source arrays of a frame are tens of MB. */
static u64 geo_hash(const u8* p, u64 n, u64 seed)
{
    u64 a = seed ^ 0x9E3779B97F4A7C15ull, b = seed + 0xC2B2AE3D27D4EB4Full,
        c = seed ^ 0x165667B19E3779F9ull, d = seed + 0x27D4EB2F165667C5ull;
    const u64 total = n;
    while (n >= 32) {
        u64 w[4]; memcpy(w, p, 32);
        a = geo_rotl(a ^ w[0], 27) * GEO_K; b = geo_rotl(b ^ w[1], 27) * GEO_K;
        c = geo_rotl(c ^ w[2], 27) * GEO_K; d = geo_rotl(d ^ w[3], 27) * GEO_K;
        p += 32; n -= 32;
    }
    while (n >= 8) { u64 w; memcpy(&w, p, 8); a = geo_rotl(a ^ w, 27) * GEO_K; p += 8; n -= 8; }
    if (n) { u64 w = 0; memcpy(&w, p, (size_t)n); b = geo_rotl(b ^ w, 27) * GEO_K; }
    u64 h = a ^ geo_rotl(b, 13) ^ geo_rotl(c, 29) ^ geo_rotl(d, 43) ^ (total * 0xD6E8FEB86659FD93ull);
    h ^= h >> 31; h *= 0x7FB5D329728EA185ull; h ^= h >> 27;
    return h;
}
static inline u64 geo_mix(u64 h, u64 w) { h = geo_rotl(h ^ w, 27) * GEO_K; return h ^ (h >> 29); }

/* Hash of the source bytes of vertices lo..hi for the attributes of vm (overlapping ranges, i.e.
 * interleaved streams, are read once). 0 = an attribute is not a flat readable range. */
static int geo_vert_hash(const rsx_state* st, u32 vm, u32 lo, u32 hi, u64* out)
{
    extern uint8_t* vm_base;
    extern u32 cellGcmResolveLocated(int local, u32 offset);
    const u8* r0[16]; const u8* r1[16]; int nr = 0;
    for (int i = 0; i < 16; i++) {
        if (!(vm & (1u << i))) continue;
        const rsx_vertex_attrib* a = &st->vertex_attribs[i];
        if (!s_vplan.mode[i] || !a->stride) return 0;
        u32 nc = a->size ? a->size : 4; if (nc > 4) nc = 4;
        const u64 span = (u64)(hi - lo) * a->stride + vpc_elem_bytes(a->type, nc);
        const u8* p;
        if (s_vplan.mode[i] == 1) {
            p = s_vplan.base[i] + (u64)lo * a->stride;
        } else {
            if (!(a->offset & 0x80000000u) ||
                !(a->frequency == 0 || (a->frequency == 1 && !((st->frequency_divider_op >> i) & 1u))))
                return 0;
            const u64 o0 = (u64)(a->offset & 0x7FFFFFFFu) + (u64)lo * a->stride;
            if (o0 + span > 0x80000000ull) return 0;
            const u32 e0 = cellGcmResolveLocated(0, (u32)o0);
            if (!e0 || cellGcmResolveLocated(0, (u32)(o0 + span - 1)) - e0 != (u32)(span - 1)) return 0;
            for (u64 o = (o0 | 0xFFFFFull) + 1u; o < o0 + span; o += 0x100000ull)
                if (cellGcmResolveLocated(0, (u32)o) - e0 != (u32)(o - o0)) return 0;
            p = vm_base + e0;
        }
        int j = nr++;                                   /* insertion sort by start */
        while (j > 0 && r0[j - 1] > p) { r0[j] = r0[j - 1]; r1[j] = r1[j - 1]; j--; }
        r0[j] = p; r1[j] = p + span;
    }
    if (!nr) return 0;
    u64 h = 0x9ABCDEF0ull;
    const u8* b = r0[0]; const u8* e = r1[0];
    for (int j = 1; j <= nr; j++) {
        if (j < nr && r0[j] <= e + 64) { if (r1[j] > e) e = r1[j]; continue; }
        h = geo_hash(b, (u64)(e - b), h);
        s_geo.st_hashed += (u64)(e - b);
        if (j < nr) { b = r0[j]; e = r1[j]; }
    }
    *out = h;
    return 1;
}

/* Would this batch have continued the previous record's run, had that record not come from the
 * cache? ix_can_continue's conditions, without the ones about the frame buffers. */
static int geo_would_continue(const rsx_state* st, u32 first, u32 prim, u32 vm)
{
    if (!s_geo.last_valid || s_geo.last_frame != s_geo.frame || !s_geo.last_ent) return 0;
    if (!s_d3d.merge_prev_draw || s_d3d.draw_count == 0 || s_geo.last_draw != s_d3d.draw_count - 1) return 0;
    const D3D12DrawRecord* pc = &s_d3d.draws[s_d3d.draw_count - 1];
    return pc->indexed && pc->geo && prim == s_geo.last_prim && vm == s_geo.last_vmask &&
           s_d3d.merge_first_end == first &&
           pc->fp_addr == (st ? st->shader_program : 0) && pc->begin_epoch == (st ? st->begin_epoch : 0);
}
static int upload_prim_vp_ix(const rsx_state* state, u32 prim, u32 first, u32 count, int cont, u32* nidx,
                             u32 vmask);
/* The previous record came from the cache and its run is not what the entry holds: convert the
 * batches it has consumed again, into the frame buffers, so that the run goes on like any other.
 * The entry is not used again. */
static void geo_replay(const rsx_state* st)
{
    D3D12DrawRecord* pc = &s_d3d.draws[s_d3d.draw_count - 1];
    GeoEnt* e = s_geo.last_ent;
    const u32 nb = s_geo.last_next, ib0 = s_d3d.vp_ib_offset;
    u32 total = 0; int ok = 1;
    s_geo.last_valid = 0; s_geo.open_ent = NULL;
    e->state = 2;
    s_geo.st_multi++;
    for (u32 j = 0; j < nb && ok; j++) {
        const GeoBat* b = &s_geo.bat[e->bat0 + j];
        u32 n = 0;
        ok = upload_prim_vp_ix(st, s_geo.last_prim, b->first, b->count, j > 0, &n, s_geo.last_vmask);
        total += n;
    }
    if (!ok) return;                       /* no room: the record keeps drawing what the cache holds */
    pc->geo = 0;
    pc->vb_byte_offset = s_ix_vbyte; pc->vertex_count = s_ix_nverts;
    pc->ib_first = ib0; pc->index_count = total; pc->cst_off = s_ix_cst;
}

/* The index bytes of a batch: their hash, and optionally the range of vertices they reach. */
static u64 geo_index_hash(const rsx_state* st, u32 first, u32 count, u32* plo, u32* phi)
{
    extern uint8_t* vm_base;
    extern u32 cellGcmResolveLocated(int local, u32 offset);
    const int local = ((st->index_array_dma & 0xF) == 0);
    const u8* ip = vm_base + cellGcmResolveLocated(local, st->index_array_offset);
    const int sixteen = (((st->index_array_dma >> 4) & 0xF) == 1);
    const u32 isz = sixteen ? 2u : 4u;
    s_geo.st_hashed += (u64)count * isz;
    if (plo) {
        const int rs_on = st->restart_index_enable && !(sixteen && st->restart_index > 0xFFFFu);
        u32 lo = 0xFFFFFFFFu, hi = 0;
        for (u32 k = 0; k < count; k++) {
            const u32 kk = first + k;
            const u32 ix = sixteen ? (((u32)ip[kk * 2] << 8) | ip[kk * 2 + 1])
                                   : (((u32)ip[kk * 4] << 24) | ((u32)ip[kk * 4 + 1] << 16) |
                                      ((u32)ip[kk * 4 + 2] << 8) | ip[kk * 4 + 3]);
            if (rs_on && ix == st->restart_index) continue;
            if (ix < lo) lo = ix;
            if (ix > hi) hi = ix;
        }
        *plo = lo; *phi = hi;
    }
    return geo_hash(ip + (u64)first * isz, (u64)count * isz, 0x1D8E4E27C47D124Full);
}

/* Convert a batch into the storage of entry e: upload_prim_vp_ix itself, pointed at the
 * persistent buffers (frame offsets put aside), so the data is what the frame path writes.
 * cont = 0: e's first batch, at the end of the buffers; 1: the next batch of the run e is being
 * built from (e is the last entry and the run state is still its own). */
static int geo_convert(const rsx_state* st, u32 prim, u32 first, u32 count, u32 vm, GeoEnt* e, int cont)
{
    const u32 stride = vp_mask_count(vm) * 16u;
    const u64 need_vb = (cont ? 0u : 2u * 256u) + (u64)(count + 1u) * stride + 256u;
    const u64 need_ib = (u64)count * 3u + 16u;
    if (s_geo.bat_used >= GEO_BAT_CAP ||
        (u64)s_geo.vb_used + need_vb > s_geo.vb_cap || (u64)s_geo.ib_used + need_ib > s_geo.ib_cap) {
        s_geo.full = 1;
        return 0;
    }
    if (!cont) { e->vb_base = s_geo.vb_used; e->ib_off = s_geo.ib_used; e->icount = 0; e->vcount = 0; }
    const u32 sv_vb = s_d3d.vp_vb_offset, sv_ib = s_d3d.vp_ib_offset;
    const u32 had_vb = s_geo.vb_used - e->vb_base;
    s_geo_dst_vb = s_geo.vb + e->vb_base; s_geo_dst_vb_cap = (u64)had_vb + need_vb;
    s_geo_dst_ib = s_geo.ib + e->ib_off;  s_geo_dst_ib_cap = e->icount + (u32)need_ib;
    s_d3d.vp_vb_offset = had_vb; s_d3d.vp_ib_offset = e->icount;
    u32 n = 0;
    const int ok = upload_prim_vp_ix(st, prim, first, count, cont, &n, vm);
    const u32 used_vb = s_d3d.vp_vb_offset;
    s_d3d.vp_vb_offset = sv_vb; s_d3d.vp_ib_offset = sv_ib;
    s_geo_dst_vb = NULL; s_geo_dst_ib = NULL;
    s_ix_run_valid = 0;                    /* the frame path never continues a run that lives in the cache */
    if (!ok) return 0;
    e->vb_off = e->vb_base + s_ix_vbyte;
    e->vcount = s_ix_nverts;
    e->icount += n;
    s_geo.vb_used = e->vb_base + used_vb;
    s_geo.ib_used = e->ib_off + e->icount;
    return 1;
}

/* Hash and convert one batch of entry e (its first, or the next of the run being built) and
 * note it as a GeoBat. 0 = not something the cache can hold (the caller decides what then). */
static int geo_add_batch(const rsx_state* st, u32 prim, u32 first, u32 count, u32 vm, GeoEnt* e, int cont)
{
    u32 lo, hi; u64 hvx = 0;
    const u64 hix = geo_index_hash(st, first, count, &lo, &hi);
    if (lo > hi || hi >= (1u << 20) || !geo_vert_hash(st, vm, lo, hi, &hvx)) { s_geo.st_unread++; return 0; }
    if (!geo_convert(st, prim, first, count, vm, e, cont)) return 0;
    GeoBat* b = &s_geo.bat[s_geo.bat_used];
    if (!cont) { e->bat0 = s_geo.bat_used; e->nbat = 0; }
    b->hix = hix; b->hvx = hvx; b->first = first; b->count = count; b->lo = lo; b->hi = hi;
    b->cum_icount = e->icount; b->pad = 0;
    e->nbat++; s_geo.bat_used++;
    s_geo.st_build++;
    return 1;
}

/* A batch that continues the run of the previous record, which came from the cache. 1 = taken
 * (the record now covers it); 0 = the record is back in the frame buffers (geo_replay) and the
 * caller goes on with the frame path. */
static int geo_continue(const rsx_state* st, u32 first, u32 count, u32 vm)
{
    GeoEnt* e = s_geo.last_ent;
    D3D12DrawRecord* pc = &s_d3d.draws[s_d3d.draw_count - 1];
    if (e->state == 1 && s_geo.last_next < e->nbat) {            /* the entry holds a next batch */
        const GeoBat* b = &s_geo.bat[e->bat0 + s_geo.last_next];
        u64 hvx = 0;
        if (b->first == first && b->count == count && geo_index_hash(st, first, count, NULL, NULL) == b->hix &&
            geo_vert_hash(st, vm, b->lo, b->hi, &hvx) && hvx == b->hvx) {
            pc->index_count = b->cum_icount;
            s_geo.last_next++;
            s_geo.st_hit++; s_geo.st_idx_hit += count;
            return 1;
        }
        s_geo.st_changed++;
    } else if (e->state == 1 && e == s_geo.open_ent && s_geo.last_next == e->nbat) {   /* being built */
        if (geo_add_batch(st, s_geo.last_prim, first, count, vm, e, 1)) {
            pc->index_count = e->icount; pc->vertex_count = e->vcount;
            s_geo.last_next++;
            s_geo.st_idx_hit += count;
            return 1;
        }
    }
    geo_replay(st);
    return 0;
}

/* One batch that starts a run. 1 = taken from the cache (found or just built): *ent is its
 * entry and *cst_off its constant block in the frame's vertex buffer. 0 = frame path. */
static int geo_try(const rsx_state* st, u32 prim, u32 first, u32 count, u32 vm, GeoEnt** ent, u32* cst_off)
{
    extern uint8_t* vm_base;
    extern u32 cellGcmResolveLocated(int local, u32 offset);
    s_geo.open_ent = NULL;
    if (!st || !vm_base || !count || !st->vertex_attribs[0].enabled) return 0;
    if (!s_vplan.valid || s_vplan.st != st) vplan_build(st);
    const int local = ((st->index_array_dma & 0xF) == 0);
    const u32 iea = cellGcmResolveLocated(local, st->index_array_offset);
    const int sixteen = (((st->index_array_dma >> 4) & 0xF) == 1);
    const int rs_on = st->restart_index_enable && !(sixteen && st->restart_index > 0xFFFFu);
    u64 key = geo_mix(0x47454F31ull, ((u64)iea << 32) | first);
    key = geo_mix(key, ((u64)count << 32) | (prim << 8) | (u32)sixteen);
    key = geo_mix(key, ((u64)vm << 32) | (rs_on ? st->restart_index + 1u : 0u));
    for (int i = 0; i < 16; i++) {
        if (!(vm & (1u << i))) continue;
        const rsx_vertex_attrib* a = &st->vertex_attribs[i];
        key = geo_mix(key, ((u64)a->offset << 32) | ((a->stride & 0xFFFFu) << 16) | ((a->type & 0xFFu) << 8) |
                           ((a->size & 0xFu) << 4) | (u32)i);
        key = geo_mix(key, ((u64)a->frequency << 8) | ((st->frequency_divider_op >> i) & 1u));
    }
    if (!key) key = 1;
    u32 slot = (u32)(key >> 24) & ((1u << GEO_BITS) - 1u);
    GeoEnt* e = NULL; GeoEnt* freee = NULL;
    for (int probe = 0; probe < 12; probe++, slot = (slot + 1u) & ((1u << GEO_BITS) - 1u)) {
        GeoEnt* c = &s_geo.tab[slot];
        if (c->state && c->key == key) { e = c; break; }
        if (!c->state) { freee = c; break; }
    }
    if (e && e->state == 2) { s_geo.st_skip++; return 0; }
    /* the frame's constant block must fit whatever happens next */
    if ((u64)s_d3d.vp_vb_offset + 2u * VP_VERT_STRIDE > (u64)MAX_VERTICES * VP_VERT_STRIDE) return 0;
    if (e) {
        const GeoBat* b = &s_geo.bat[e->bat0];
        u64 hvx = 0;
        if (geo_index_hash(st, first, count, NULL, NULL) != b->hix ||
            !geo_vert_hash(st, vm, b->lo, b->hi, &hvx) || hvx != b->hvx) {
            /* Rewritten in place. Once or twice it is a buffer that got new contents (another
             * track loaded at the same addresses): build the entry again, in new storage (records
             * of this frame may still draw the old one). More often than that it is a dynamic
             * buffer: leave it to the frame path. */
            s_geo.st_changed++;
            if (e->nchg >= 2 || s_geo.full || !geo_add_batch(st, prim, first, count, vm, e, 0)) {
                e->state = 2;
                return 0;
            }
            e->nchg++;
            s_geo.open_ent = e;
        } else
        s_geo.st_hit++;
    } else {
        if (!freee || s_geo.full) return 0;
        e = freee;
        if (!geo_add_batch(st, prim, first, count, vm, e, 0)) {
            if (!s_geo.full) { e->key = key; e->state = 2; }   /* remember it is not cacheable */
            return 0;
        }
        e->key = key; e->state = 1; e->nchg = 0;
        s_geo.open_ent = e;
    }
    /* the draw's constant block (attributes the vertex program reads that have no array) */
    { u8* fvb = (u8*)s_d3d.vp_vb_mapped + (u64)s_d3d.vp_parity * MAX_VERTICES * VP_VERT_STRIDE;
      memcpy(fvb + s_d3d.vp_vb_offset, s_vplan.cst, VP_VERT_STRIDE);
      *cst_off = s_d3d.vp_vb_offset;
      s_d3d.vp_vb_offset += VP_VERT_STRIDE; }
    s_ix_run_valid = 0;
    e->frame = s_geo.frame;
    s_geo.st_idx_hit += count;
    *ent = e;
    return 1;
}

static void d3d12_draw_indexed(void* ud, u32 primitive, u32 first, u32 count)
{
''')

# ---- 10. d3d12_draw_indexed: use it -----------------------------------------------------------
rep('''    int ix_used = 0, ix_cont = 0;
    const u32 ib0 = s_d3d.vp_ib_offset;
''', '''    int ix_used = 0, ix_cont = 0;
    u32 ib0 = s_d3d.vp_ib_offset;
    int geo_used = 0; GeoEnt* geo_ent = NULL; u32 geo_cst = 0, geo_vm = 0;   /* GEO_CACHE */
''')
rep('''          if (vrs_on()) vrs_note(s_d3d.current_rsx_state, primitive, first, count, vm);
          ix_cont = ix_can_continue(first, primitive, vm);
          ix_used = upload_prim_vp_ix(s_d3d.current_rsx_state, primitive, first, count, ix_cont, &emitted, vm);
''', '''          if (vrs_on()) vrs_note(s_d3d.current_rsx_state, primitive, first, count, vm);
          const int geo_ok = vm && s_geo.on > 0 && s_geo.vb && !s_geo.drain;
          if (geo_ok) s_geo.st_idx_all += count;
          if (geo_ok && geo_would_continue(s_d3d.current_rsx_state, first, primitive, vm)) {
              if (geo_continue(s_d3d.current_rsx_state, first, count, vm)) {
                  s_d3d.merge_first_end = first + count;   /* the cached record took this batch too */
                  return;
              }
              ib0 = s_d3d.vp_ib_offset; rec = s_d3d.vp_vb_offset;
          }
          s_geo.last_valid = 0; s_geo.open_ent = NULL;
          ix_cont = ix_can_continue(first, primitive, vm);
          if (geo_ok && !ix_cont && s_d3d.draw_count < MAX_DRAWS)
              geo_used = geo_try(s_d3d.current_rsx_state, primitive, first, count, vm, &geo_ent, &geo_cst);
          if (geo_used) { ix_used = 1; emitted = s_geo.bat[geo_ent->bat0].cum_icount; geo_vm = vm; }
          else
          ix_used = upload_prim_vp_ix(s_d3d.current_rsx_state, primitive, first, count, ix_cont, &emitted, vm);
''')
rep('''        dr->vmask          = 0;
        dr->cst_off        = 0;
        if (ix_used) {
            dr->vb_byte_offset = s_ix_mask ? s_ix_vbyte : s_ix_vbase * VP_VERT_STRIDE;
            dr->vertex_count   = s_ix_nverts;
            dr->ib_first       = ib0;
            dr->index_count    = emitted;
            dr->vmask          = s_ix_mask;
            dr->cst_off        = s_ix_cst;
        }
''', '''        dr->vmask          = 0;
        dr->cst_off        = 0;
        dr->geo            = 0;
        if (geo_used) {                    /* GEO_CACHE: the entry's storage + this draw's constants */
            dr->geo            = 1;
            dr->vb_byte_offset = geo_ent->vb_off;
            dr->vertex_count   = geo_ent->vcount;
            dr->ib_first       = geo_ent->ib_off;
            dr->index_count    = s_geo.bat[geo_ent->bat0].cum_icount;   /* grows as its next batches come */
            dr->vmask          = geo_vm;
            dr->cst_off        = geo_cst;
            s_geo.last_valid = 1; s_geo.last_frame = s_geo.frame; s_geo.last_draw = s_d3d.draw_count;
            s_geo.last_prim = primitive; s_geo.last_vmask = geo_vm; s_geo.last_ent = geo_ent;
            s_geo.last_next = 1;
        } else
        if (ix_used) {
            dr->vb_byte_offset = s_ix_mask ? s_ix_vbyte : s_ix_vbase * VP_VERT_STRIDE;
            dr->vertex_count   = s_ix_nverts;
            dr->ib_first       = ib0;
            dr->index_count    = emitted;
            dr->vmask          = s_ix_mask;
            dr->cst_off        = s_ix_cst;
        }
''')

if '--check' in sys.argv:
    print('would patch (%d bytes)' % len(s)); sys.exit(0)
io.open(P, 'w', encoding='utf-8', newline='').write(s.replace('\n', nl))
print('patched')
