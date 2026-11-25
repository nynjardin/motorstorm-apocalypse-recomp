"""Instrument (or restore) one lifted SPU job module for the lifted-vs-interpreter shadow check.

Every direct lifted call
    ctx->gpr[0] = spu_link(R); { ...; F_spu_func_XXXXXXXX(ctx); spu_drain_call(ctx, R); ...; }
gets spu_shadow_pre(ctx, 0xXXXXXXXX, R) before and spu_shadow_post(...) after (runtime:
ps3recomp/runtime/spu/spu_interp.c). Run the game with SPU_SHADOW=1; "[shadow] MISMATCH" lines name
the first callee whose lifted result differs from the interpreter's.

    python scripts/shadow_jobmod.py port/spu/<jobmod dir>            # instrument (keeps .orig)
    python scripts/shadow_jobmod.py port/spu/<jobmod dir> --restore  # put the original back
Then port\\build.bat. Diagnostic only: restore before committing to a build you keep.
"""
import os
import re
import sys

d = sys.argv[1]
src = os.path.join(d, "spu_recomp.c")
orig = src + ".orig"
if "--restore" in sys.argv:
    if os.path.exists(orig):
        os.replace(orig, src)
        os.utime(src, None)
        print("restored", src)
    else:
        print("no backup for", src)
    sys.exit(0)

text = open(src, encoding="utf-8", errors="surrogateescape", newline="").read()
if "spu_shadow_pre" in text:
    sys.exit("already instrumented: " + src)
open(orig, "w", encoding="utf-8", errors="surrogateescape", newline="").write(text)
nl = "\r\n" if "\r\n" in text[:4000] else "\n"

pat = re.compile(
    r"ctx->gpr\[0\] = spu_link\((0x[0-9A-Fa-f]+)\); \{ (int32_t _si = \(int32_t\)ctx->image_id; ctx->host_depth\+\+; "
    r"(\w+_spu_func_([0-9A-Fa-f]{8}))\(ctx\); spu_drain_call\(ctx, (0x[0-9A-Fa-f]+)\); ctx->host_depth--; "
    r"spu_img_restore\(ctx, _si\);) \}")


def rep(m):
    ret, body, _fn, entry, ret2 = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
    return (f"ctx->gpr[0] = spu_link({ret}); {{ void* _sh = spu_shadow_pre(ctx, 0x{entry}u, {ret2}u); {body} "
            f"spu_shadow_post(ctx, _sh, 0x{entry}u, {ret2}u); }}")


new, n = pat.subn(rep, text)

# Indirect calls into the job code buffer (LS >= 0x4000): in the WWS policy module that is the
# call of a whole job, so the shadow covers the job from entry to its return to the PM.
ipat = re.compile(
    r"\{ uint32_t _tg = (ctx->gpr\[\d+\]\._u32\[0\]); ctx->gpr\[0\] = spu_link\((0x[0-9A-Fa-f]+)\); "
    r"(int32_t _si = \(int32_t\)ctx->image_id; (?:ctx->int_enable = [01]; )?ctx->pc = _tg; ctx->host_depth\+\+; "
    r"spu_indirect_branch\(ctx\); spu_drain_call\(ctx, (0x[0-9A-Fa-f]+)\); ctx->host_depth--; "
    r"spu_img_restore\(ctx, _si\);) \}")


def irep(m):
    tg, ret, body, ret2 = m.group(1), m.group(2), m.group(3), m.group(4)
    return (f"{{ uint32_t _tg = {tg}; ctx->gpr[0] = spu_link({ret}); "
            f"void* _sh = (_tg & 0x3FFFFu) >= 0x4000u ? spu_shadow_pre(ctx, _tg & 0x3FFFCu, {ret2}u) : 0; {body} "
            f"spu_shadow_post(ctx, _sh, _tg & 0x3FFFCu, {ret2}u); }}")


new, ni = ipat.subn(irep, new)
n += ni
decl = ("void* spu_shadow_pre(spu_context* ctx, uint32_t entry, uint32_t ret);" + nl +
        "void spu_shadow_post(spu_context* ctx, void* h, uint32_t entry, uint32_t ret);" + nl)
# after the first #include line
i = new.index("#include")
j = new.index(nl, i) + len(nl)
new = new[:j] + decl + new[j:]
open(src, "w", encoding="utf-8", errors="surrogateescape", newline="").write(new)
print(f"instrumented {n} direct call(s) in {src}")
