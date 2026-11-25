# Applies local toolkit patch #41 to ps3recomp/runtime/ppu/ppu_vmx.h (2026-11-23).
#
#   python scripts/vmx_simd_patch.py [--check] [--file <copy of ppu_vmx.h>]
#
# What it does (all bit-identical to the scalar forms, test: E:\ms_perf\test_vmx_simd2.cpp):
#   - vaddfp / vsubfp / vmaddfp / vnmsubfp (patch #25) skip the VSCR[NJ] flush when NJ is clear
#     (this title never writes VSCR: the four masks per op were computed for nothing) and only
#     run the NaN rules when the result holds a NaN;
#   - SSE/AVX2 forms of the float compares, vrefp, vrsqrtefp, vcfsx, vcfux, vctsxs, vmaxfp,
#     vminfp, the per-word shifts / rotate and vcmpequw, which were scalar byte loops.
# The scalar functions stay as <name>_ref. Idempotent: a patched file is left alone.
# Backup of the file before the patch: E:\ms_perf\bak_1123_fastfloat\ppu_vmx.h.
import io, sys

P = r'I:/Projets/Recomp/ps3recomp/runtime/ppu/ppu_vmx.h'
if '--file' in sys.argv: P = sys.argv[sys.argv.index('--file') + 1]   # a copy, to test first
BS = bytes([92]).decode()          # a backslash, for the C macro continuations
s = io.open(P, encoding='utf-8', newline='').read()
if 'patch #41' in s:
    print('already patched'); sys.exit(0)
nl = '\r\n' if '\r\n' in s else '\n'
s = s.replace('\r\n', '\n')

def rep(old, new, count=1):
    global s
    assert s.count(old) == count, (s.count(old), old[:90])
    s = s.replace(old, new)

# 1. the scalar forms that get a SIMD twin become <name>_ref
for name in ('vmx_vrlw', 'vmx_vslw', 'vmx_vsrw', 'vmx_vsraw'):
    rep('VMX_BIN(%s, 4,' % name, 'VMX_BIN(%s_ref, 4,' % name)
rep('VMX_FBIN(vmx_vmaxfp, ', 'VMX_FBIN(vmx_vmaxfp_ref, ')
rep('VMX_FBIN(vmx_vminfp, ', 'VMX_FBIN(vmx_vminfp_ref, ')
rep('VMX_FUN(vmx_vrefp, ', 'VMX_FUN(vmx_vrefp_ref, ')
rep('VMX_FUN(vmx_vrsqrtefp, ', 'VMX_FUN(vmx_vrsqrtefp_ref, ')
rep('VMX_INL void vmx_vcfux(VMX_D, VMX_B, unsigned uimm) {', 'VMX_INL void vmx_vcfux_ref(VMX_D, VMX_B, unsigned uimm) {')
rep('VMX_INL void vmx_vcfsx(VMX_D, VMX_B, unsigned uimm) {', 'VMX_INL void vmx_vcfsx_ref(VMX_D, VMX_B, unsigned uimm) {')
rep('VMX_INL void vmx_vctsxs(VMX_D, VMX_B, unsigned uimm, uint32_t* vscr) {',
    'VMX_INL void vmx_vctsxs_ref(VMX_D, VMX_B, unsigned uimm, uint32_t* vscr) {')
rep('VMX_CMP(vmx_vcmpequw, ', 'VMX_CMP(vmx_vcmpequw_ref, ')
for name in ('vmx_vcmpeqfp', 'vmx_vcmpgefp', 'vmx_vcmpgtfp'):
    rep('VMX_CMP(%s, ' % name, 'VMX_CMP(%s_ref, ' % name)

# 2. the four float ops of patch #25: no flush when NJ is clear, NaN rules only on a NaN result
rep('''VMX_INL void vmx_vaddfp(VMX_D, VMX_A, VMX_B, uint32_t vscr) {
    const __m128i nj = vmx_njmask(vscr);
''', '''/* MotorStorm local patch #41: with VSCR[NJ] clear there is nothing to flush, and a NaN operand
 * always gives a NaN result, so the NaN rules only run when the result holds one. Same bits as
 * before; the full sequence below stays for NJ set. */
#define VMX_NO_NAN(r) (_mm_movemask_ps(_mm_cmpunord_ps((r), (r))) == 0)
VMX_INL __m128 vmx_ldf(const void* p) { return _mm_castsi128_ps(vmx_ld(p)); }
VMX_INL void vmx_stf(void* p, __m128 v) { vmx_st(p, _mm_castps_si128(v)); }
VMX_INL void vmx_vaddfp(VMX_D, VMX_A, VMX_B, uint32_t vscr) {
    if (__builtin_expect(!(vscr & VMX_NJ), 1)) {
        const __m128 x = vmx_ldf(a_), y = vmx_ldf(b_), r = _mm_add_ps(x, y);
        vmx_stf(d_, __builtin_expect(VMX_NO_NAN(r), 1) ? r : vmx_vnan2_4(r, x, y)); return; }
    const __m128i nj = vmx_njmask(vscr);
''')
rep('''VMX_INL void vmx_vsubfp(VMX_D, VMX_A, VMX_B, uint32_t vscr) {
    const __m128i nj = vmx_njmask(vscr);
''', '''VMX_INL void vmx_vsubfp(VMX_D, VMX_A, VMX_B, uint32_t vscr) {
    if (__builtin_expect(!(vscr & VMX_NJ), 1)) {
        const __m128 x = vmx_ldf(a_), y = vmx_ldf(b_), r = _mm_sub_ps(x, y);
        vmx_stf(d_, __builtin_expect(VMX_NO_NAN(r), 1) ? r : vmx_vnan2_4(r, x, y)); return; }
    const __m128i nj = vmx_njmask(vscr);
''')
rep('''VMX_INL void vmx_vmaddfp(VMX_D, VMX_A, VMX_B, VMX_C, uint32_t vscr) {
    const __m128i nj = vmx_njmask(vscr);
''', '''VMX_INL void vmx_vmaddfp(VMX_D, VMX_A, VMX_B, VMX_C, uint32_t vscr) {
    if (__builtin_expect(!(vscr & VMX_NJ), 1)) {
        const __m128 r = _mm_fmadd_ps(vmx_ldf(a_), vmx_ldf(c_), vmx_ldf(b_));
        vmx_stf(d_, __builtin_expect(VMX_NO_NAN(r), 1) ? r : vmx_fix4(r)); return; }
    const __m128i nj = vmx_njmask(vscr);
''')
rep('''VMX_INL void vmx_vnmsubfp(VMX_D, VMX_A, VMX_B, VMX_C, uint32_t vscr) {
    const __m128i nj = vmx_njmask(vscr);
''', '''VMX_INL void vmx_vnmsubfp(VMX_D, VMX_A, VMX_B, VMX_C, uint32_t vscr) {
    if (__builtin_expect(!(vscr & VMX_NJ), 1)) {
        const __m128 r = _mm_xor_ps(_mm_fmsub_ps(vmx_ldf(a_), vmx_ldf(c_), vmx_ldf(b_)),
                                    _mm_castsi128_ps(_mm_set1_epi32((int)0x80000000u)));
        vmx_stf(d_, __builtin_expect(VMX_NO_NAN(r), 1) ? r : vmx_fix4(r)); return; }
    const __m128i nj = vmx_njmask(vscr);
''')

# 3. SIMD twins of the scalar loops, at the end of the file
tail = '''
/* MotorStorm local patch #41: SSE/AVX2 forms of the ops that were scalar byte loops (the float
 * compares, estimates, conversions, max/min, per-word shifts). Each gives the same bits as its
 * <name>_ref above; a case the vector form does not cover (NJ set, a NaN) goes to the _ref. */
#if defined(__AVX2__) && defined(__FMA__) && !defined(VMX_NO_SIMD)
/* compare masks are whole lanes of ones or zeros: no byte swap to store them */
#define VMX_SIMD_FCMP(name, cmp) @
VMX_INL uint32_t name(VMX_D, VMX_A, VMX_B) { @
    const __m128 m = cmp(vmx_ldf(a_), vmx_ldf(b_)); const int k = _mm_movemask_ps(m); @
    _mm_storeu_si128((__m128i*)d_, _mm_castps_si128(m)); @
    return (uint32_t)((k == 15) << 3 | (k == 0) << 1); }
VMX_SIMD_FCMP(vmx_vcmpeqfp, _mm_cmpeq_ps)
VMX_SIMD_FCMP(vmx_vcmpgefp, _mm_cmpge_ps)
VMX_SIMD_FCMP(vmx_vcmpgtfp, _mm_cmpgt_ps)
#undef VMX_SIMD_FCMP
VMX_INL uint32_t vmx_vcmpequw(VMX_D, VMX_A, VMX_B) {
    const __m128i m = _mm_cmpeq_epi32(_mm_loadu_si128((const __m128i*)a_), _mm_loadu_si128((const __m128i*)b_));
    const int k = _mm_movemask_ps(_mm_castsi128_ps(m));
    _mm_storeu_si128((__m128i*)d_, m);
    return (uint32_t)((k == 15) << 3 | (k == 0) << 1); }
VMX_INL void vmx_vrefp(VMX_D, VMX_B, uint32_t vscr) {
    const __m128 x = vmx_ldf(b_), r = _mm_div_ps(_mm_set1_ps(1.0f), x);
    if (__builtin_expect((vscr & VMX_NJ) || !VMX_NO_NAN(r), 0)) { vmx_vrefp_ref(d_, b_, vscr); return; }
    vmx_stf(d_, r); }
VMX_INL void vmx_vrsqrtefp(VMX_D, VMX_B, uint32_t vscr) {
    const __m128 x = vmx_ldf(b_), r = _mm_div_ps(_mm_set1_ps(1.0f), _mm_sqrt_ps(x));
    if (__builtin_expect((vscr & VMX_NJ) || !VMX_NO_NAN(r), 0)) { vmx_vrsqrtefp_ref(d_, b_, vscr); return; }
    vmx_stf(d_, r); }
VMX_INL void vmx_vcfsx(VMX_D, VMX_B, unsigned uimm) {
    vmx_stf(d_, _mm_mul_ps(_mm_cvtepi32_ps(vmx_ld(b_)), _mm_set1_ps(vmx_pow2(-(int)(uimm & 31u))))); }
VMX_INL void vmx_vcfux(VMX_D, VMX_B, unsigned uimm) {
    /* u32 -> double is exact (x - 2^31 as int32, plus 2^31), then one rounding to float */
    const __m256d d = _mm256_add_pd(_mm256_cvtepi32_pd(_mm_xor_si128(vmx_ld(b_), _mm_set1_epi32((int)0x80000000u))),
                                    _mm256_set1_pd(2147483648.0));
    vmx_stf(d_, _mm_mul_ps(_mm256_cvtpd_ps(d), _mm_set1_ps(vmx_pow2(-(int)(uimm & 31u))))); }
VMX_INL void vmx_vctsxs(VMX_D, VMX_B, unsigned uimm, uint32_t* vscr) {
    const __m128 f = _mm_mul_ps(vmx_ldf(b_), _mm_set1_ps(vmx_pow2((int)(uimm & 31u))));
    const __m128 hi = _mm_cmpge_ps(f, _mm_set1_ps(2147483648.0f)), lo = _mm_cmplt_ps(f, _mm_set1_ps(-2147483648.0f));
    __m128i v = _mm_cvttps_epi32(f);                       /* out of range or NaN: 0x80000000 */
    v = _mm_blendv_epi8(v, _mm_set1_epi32(0x7FFFFFFF), _mm_castps_si128(hi));
    v = _mm_andnot_si128(_mm_castps_si128(_mm_cmpunord_ps(f, f)), v);
    if (__builtin_expect(_mm_movemask_ps(_mm_or_ps(hi, lo)), 0)) *vscr |= VMX_SAT;
    vmx_st(d_, v); }
/* max(-0, +0) = +0 and min(-0, +0) = -0: maxps/minps return their second operand for equal
 * ones, so both orders combined (and / or) give the rule; other pairs give the same value twice */
VMX_INL void vmx_vmaxfp(VMX_D, VMX_A, VMX_B, uint32_t vscr) {
    const __m128 x = vmx_ldf(a_), y = vmx_ldf(b_);
    if (__builtin_expect((vscr & VMX_NJ) || _mm_movemask_ps(_mm_cmpunord_ps(x, y)), 0)) { vmx_vmaxfp_ref(d_, a_, b_, vscr); return; }
    vmx_stf(d_, _mm_and_ps(_mm_max_ps(x, y), _mm_max_ps(y, x))); }
VMX_INL void vmx_vminfp(VMX_D, VMX_A, VMX_B, uint32_t vscr) {
    const __m128 x = vmx_ldf(a_), y = vmx_ldf(b_);
    if (__builtin_expect((vscr & VMX_NJ) || _mm_movemask_ps(_mm_cmpunord_ps(x, y)), 0)) { vmx_vminfp_ref(d_, a_, b_, vscr); return; }
    vmx_stf(d_, _mm_or_ps(_mm_min_ps(x, y), _mm_min_ps(y, x))); }
VMX_INL __m128i vmx_cnt5(const void* b_) { return _mm_and_si128(vmx_ld(b_), _mm_set1_epi32(31)); }
VMX_INL void vmx_vslw(VMX_D, VMX_A, VMX_B) { vmx_st(d_, _mm_sllv_epi32(vmx_ld(a_), vmx_cnt5(b_))); }
VMX_INL void vmx_vsrw(VMX_D, VMX_A, VMX_B) { vmx_st(d_, _mm_srlv_epi32(vmx_ld(a_), vmx_cnt5(b_))); }
VMX_INL void vmx_vsraw(VMX_D, VMX_A, VMX_B) { vmx_st(d_, _mm_srav_epi32(vmx_ld(a_), vmx_cnt5(b_))); }
VMX_INL void vmx_vrlw(VMX_D, VMX_A, VMX_B) {
    const __m128i x = vmx_ld(a_), n = vmx_cnt5(b_);        /* a count of 32 shifts everything out */
    vmx_st(d_, _mm_or_si128(_mm_sllv_epi32(x, n), _mm_srlv_epi32(x, _mm_sub_epi32(_mm_set1_epi32(32), n)))); }
#else
VMX_INL uint32_t vmx_vcmpeqfp(VMX_D, VMX_A, VMX_B) { return vmx_vcmpeqfp_ref(d_, a_, b_); }
VMX_INL uint32_t vmx_vcmpgefp(VMX_D, VMX_A, VMX_B) { return vmx_vcmpgefp_ref(d_, a_, b_); }
VMX_INL uint32_t vmx_vcmpgtfp(VMX_D, VMX_A, VMX_B) { return vmx_vcmpgtfp_ref(d_, a_, b_); }
VMX_INL uint32_t vmx_vcmpequw(VMX_D, VMX_A, VMX_B) { return vmx_vcmpequw_ref(d_, a_, b_); }
VMX_INL void vmx_vrefp(VMX_D, VMX_B, uint32_t vscr) { vmx_vrefp_ref(d_, b_, vscr); }
VMX_INL void vmx_vrsqrtefp(VMX_D, VMX_B, uint32_t vscr) { vmx_vrsqrtefp_ref(d_, b_, vscr); }
VMX_INL void vmx_vcfsx(VMX_D, VMX_B, unsigned uimm) { vmx_vcfsx_ref(d_, b_, uimm); }
VMX_INL void vmx_vcfux(VMX_D, VMX_B, unsigned uimm) { vmx_vcfux_ref(d_, b_, uimm); }
VMX_INL void vmx_vctsxs(VMX_D, VMX_B, unsigned uimm, uint32_t* vscr) { vmx_vctsxs_ref(d_, b_, uimm, vscr); }
VMX_INL void vmx_vmaxfp(VMX_D, VMX_A, VMX_B, uint32_t vscr) { vmx_vmaxfp_ref(d_, a_, b_, vscr); }
VMX_INL void vmx_vminfp(VMX_D, VMX_A, VMX_B, uint32_t vscr) { vmx_vminfp_ref(d_, a_, b_, vscr); }
VMX_INL void vmx_vslw(VMX_D, VMX_A, VMX_B) { vmx_vslw_ref(d_, a_, b_); }
VMX_INL void vmx_vsrw(VMX_D, VMX_A, VMX_B) { vmx_vsrw_ref(d_, a_, b_); }
VMX_INL void vmx_vsraw(VMX_D, VMX_A, VMX_B) { vmx_vsraw_ref(d_, a_, b_); }
VMX_INL void vmx_vrlw(VMX_D, VMX_A, VMX_B) { vmx_vrlw_ref(d_, a_, b_); }
#endif

#ifdef __cplusplus
}
#endif
#endif /* PPU_VMX_H */
'''.replace('@', BS)
end = '''
#ifdef __cplusplus
}
#endif
#endif /* PPU_VMX_H */
'''
assert s.endswith(end), repr(s[-120:])
s = s[:-len(end)] + tail

if '--check' in sys.argv:
    print('would patch (%d bytes)' % len(s)); sys.exit(0)
io.open(P, 'w', encoding='utf-8', newline='').write(s.replace('\n', nl))
print('patched')
