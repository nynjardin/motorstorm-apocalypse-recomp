/* fp_addr=0x002A4441, 36 instrs */cbuffer RsxTexScale : register(b1) { float4 rsx_texscale[4]; float4 _rsx_b1_atest; float4 fp_k[64]; float4 _rsx_b1pad[3]; float4 rsx_texscale_hi[6]; };
struct PSInput {
    float4 position : SV_POSITION; float4 col0 : COLOR0; float4 col1 : COLOR1;
    float4 fog : FOG;
    float4 tc0:TEXCOORD0; float4 tc1:TEXCOORD1; float4 tc2:TEXCOORD2; float4 tc3:TEXCOORD3;
    float4 tc4:TEXCOORD4; float4 tc5:TEXCOORD5; float4 tc6:TEXCOORD6; float4 tc7:TEXCOORD7;
};
#define _rsx_wpos(p) (p)
Texture2D    rsx_tex[16] : register(t0);
SamplerState rsx_samp[16] : register(s0);
float _rsx_shadow_cmp13(float reference, float depth) { return (float)(depth >= reference); }
float4 _rsx_shadow13(float3 coordinate) {
    float reference = saturate(coordinate.z);
    uint width, height; rsx_tex[13].GetDimensions(width, height);
    float2 size = float2(width, height);
    float2 uv = coordinate.xy;
    float2 position = uv * size - 0.5;
    float2 base = floor(position); float2 fraction = position - base;
    float d0 = rsx_tex[13].SampleLevel(rsx_samp[13], ((base + float2(0.5, 0.5)) / size) * rsx_texscale_hi[4].zw, 0.0).r;
    float c0 = _rsx_shadow_cmp13(reference, d0);
    float d1 = rsx_tex[13].SampleLevel(rsx_samp[13], ((base + float2(1.5, 0.5)) / size) * rsx_texscale_hi[4].zw, 0.0).r;
    float c1 = _rsx_shadow_cmp13(reference, d1);
    float d2 = rsx_tex[13].SampleLevel(rsx_samp[13], ((base + float2(0.5, 1.5)) / size) * rsx_texscale_hi[4].zw, 0.0).r;
    float c2 = _rsx_shadow_cmp13(reference, d2);
    float d3 = rsx_tex[13].SampleLevel(rsx_samp[13], ((base + float2(1.5, 1.5)) / size) * rsx_texscale_hi[4].zw, 0.0).r;
    float c3 = _rsx_shadow_cmp13(reference, d3);
    return (float4)lerp(lerp(c0, c1, fraction.x), lerp(c2, c3, fraction.x), fraction.y);
}
float4 _rsx_expand_input(float4 v, uint mask, bool bx2) {
    float4 e = bx2 ? v * 2.0 - 1.0
             : (mask & 16u) ? (floor(v * 65535.0 + 0.5) - 32768.0) / 32767.0
                            : (floor(v * 255.0 + 0.5) - 128.0) / 127.0;
    return float4((mask & 1u) ? e.r : v.r,
                  (mask & 2u) ? e.g : v.g,
                  (mask & 4u) ? e.b : v.b,
                  (mask & 8u) ? e.a : v.a);
}
struct PSOutput {
    float4 t0 : SV_TARGET0;
    float4 t1 : SV_TARGET1;
    float4 t2 : SV_TARGET2;
};
PSOutput main(PSInput input) {
    float4 r[48]; float4 h[48];
    [unroll] for (int _i = 0; _i < 48; _i++) { r[_i] = (float4)0; h[_i] = (float4)0; }
    float4 cc0 = (float4)0; float4 cc1 = (float4)0;
    { float4 _v = (float4)(rsx_tex[0].Sample(rsx_samp[0], (((input.tc0).xyzw).xy) * rsx_texscale[0].xy)); r[0].xyw = _v.xyw; }
    { float4 _v = (float4)(((r[0]).wxyw) * ((fp_k[0]).xxxx) + ((fp_k[0]).yyyy)); r[1].xyz = _v.xyz; }
    { float4 _v = (float4)(((_rsx_wpos(input.position)).xyzw) + ((fp_k[1]).xxxx)); r[0].xy = _v.xy; }
    { float4 _v = (float4)(floor((r[1]).xyzw)); r[1].xyz = _v.xyz; }
    { float4 _v = (float4)(((r[0]).yyyy) + ((r[0]).xxxx)); r[1].w = _v.w; }
    { float4 _v = (float4)(dot(((r[1]).xyzw).xyz, ((fp_k[2]).xyzw).xyz)); r[0].z = _v.z; }
    { float4 _v = (float4)(((r[0]).zzzz) + ((fp_k[3]).yyyy)); r[1].x = _v.x; }
    { float4 _v = (float4)((r[0]).xxxx); r[1].z = _v.z; }
    { float4 _v = (float4)(((r[1]).zwzz) * ((fp_k[4]).yyyy)); r[0].xy = _v.xy; }
    { float4 _v = (float4)(((fp_k[5]).xxxx) / ((r[1]).xyzw).x); r[2].w = _v.w; }
    { float4 _v = (float4)(frac((r[0]).xyzw)) * 2.0; r[2].xy = _v.xy; }
    { float4 _v = (float4)(_rsx_expand_input(rsx_tex[1].Sample(rsx_samp[1], (((input.tc0).xyzw).xy) * rsx_texscale[1].xy), 15u, true)); h[2].xyz = _v.xyz; }
    { float4 _v = (float4)(dot(((h[2]).xyzw).xyz, (-((fp_k[6]).xyzw)).xyz)); _v = saturate(_v); h[7].x = _v.x; }
    { float4 _v = (float4)((input.tc3).xyzw); r[1].xyzw = _v.xyzw; }
    { float4 _v = (float4)(((r[2]).wwww) * ((r[1]).xzxz) + ((r[1]).ywyw)); _v = saturate(_v); h[3].zw = _v.zw; }
    { float4 _v = (float4)(min(((h[3]).zzzz), ((h[3]).xyzw))); h[7].w = _v.w; }
    { float4 _v = (float4)(((input.tc1).xyzw) * ((r[2]).wwww)); r[0].xyz = _v.xyz; }
    { float4 _v = (float4)(((input.tc2).xyzw) + ((r[0]).xyzw)); r[0].xyz = _v.xyz; }
    { float4 _v = (float4)(((r[2]).xyzw) * ((fp_k[7]).xyxx) + ((r[0]).xyzw)); r[1].xy = _v.xy; }
    { float4 _v = (float4)((r[0]).xyzw); r[1].z = _v.z; }
    { float4 _v = (float4)(((r[1]).xyzw) + ((fp_k[8]).xyzw)); r[2].xyz = _v.xyz; }
    { float4 _v = (float4)(((r[1]).xyzw) + ((fp_k[9]).xyzw)); r[0].xyz = _v.xyz; }
    { float4 _v = (float4)(_rsx_shadow13(((r[0]).xyzw).xyz)); h[0].x = _v.x; }
    { float4 _v = (float4)(((r[1]).xxyz) + ((fp_k[10]).xxyz)); r[0].yzw = _v.yzw; }
    { float4 _v = (float4)((h[0]).xxxx); h[6].z = _v.z; }
    { float4 _v = (float4)(_rsx_shadow13(((r[0]).yzww).xyz)); h[0].x = _v.x; }
    { float4 _v = (float4)(((r[1]).xxyz) + ((fp_k[11]).xxyz)); r[0].yzw = _v.yzw; }
    { float4 _v = (float4)((h[0]).xxxx); h[6].w = _v.w; }
    { float4 _v = (float4)(_rsx_shadow13(((r[0]).yzww).xyz)); h[6].x = _v.x; }
    { float4 _v = (float4)((h[6]).xxxx); h[6].y = _v.y; }
    { float4 _v = (float4)(_rsx_shadow13(((r[2]).xyzw).xyz)); h[6].x = _v.x; }
    { float4 _v = (float4)(dot(((h[6]).xyzw), ((fp_k[12]).xxxx))); _v = saturate(_v); h[0].x = _v.x; }
    { float4 _v = (float4)(((h[0]).xxxx) * ((h[7]).xyzw)); h[0].w = _v.w; }
    { float4 _v = (float4)(((h[7]).xxxx) * ((fp_k[13]).xyzw)); h[0].xyz = _v.xyz; }
    { float4 _v = (float4)(((h[0]).wwww) * ((h[0]).xyzw)); h[0].xyz = _v.xyz; }
    { float4 _v = (float4)((h[0]).xyzw); h[0].w = _v.w; }
    PSOutput _out;
    float4 _o0 = h[0];
    _out.t0 = (_o0 == _o0) ? _o0 : (float4)0;
    float4 _o1 = h[4];
    _out.t1 = (_o1 == _o1) ? _o1 : (float4)0;
    float4 _o2 = h[6];
    _out.t2 = (_o2 == _o2) ? _o2 : (float4)0;
    return _out;
}
