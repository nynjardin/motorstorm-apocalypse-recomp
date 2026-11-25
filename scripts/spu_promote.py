# Register promotion for the lifted SPU sources (port/spu/*/spu_recomp.c), after project-vekta's
# ps3recomp patch 1005 ("spu_lifter: promote leaf functions' registers to host-vector locals"),
# done here as a pass over the already lifted files (no relift).
#
# A lifted function keeps the SPU registers in ctx->gpr[], so every operation is a load and a
# store and nothing can stay in a host register across two operations (a store to the local
# store may alias ctx). In a LEAF function -- only register operations, local-store reads and
# writes, branches inside the function and the known ways out (SPU_RET, SPU_RET_REG, SPU_DIRECT,
# the interrupt check that returns to the trampoline) -- nothing else looks at the registers
# while it runs: they become locals (spu_vreg = a host vector, toolkit patch #50 in
# spu_helpers.h), loaded at entry and stored back before every way out. A function with a call,
# a channel operation, an indirect branch, a stop or any line this script does not know is left
# exactly as it is.
#
#   python scripts/spu_promote.py [--stats] [--restore] [--only <fragment>] [dir ...]
#     (no dir: every port/spu/*/spu_recomp.c)
#     --stats    count what would be promoted, write nothing
#     --restore  put back the files saved by an earlier run
#     --only     only the sources whose path contains the fragment (e.g. jobmod_d78d63199b24)
# The original of every file it changes is saved once as spu_recomp.c.prepromote next to it
# (small text files: fine on I:). Idempotent: a promoted function is recognised and skipped.
# Run it LAST in the regeneration chain of docs/spu.md (after direct_bie.py: it relies on the
# final shape of the lines). Kill switch at build time: -DSPU_NO_PROMOTE is NOT provided: restore
# and rebuild instead.
import sys, os, re, glob, shutil

root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'port', 'spu')
stats = restore = False; only = None; dirs = []
a = sys.argv[1:]
while a:
    if a[0] == '--stats': stats = True; a = a[1:]
    elif a[0] == '--restore': restore = True; a = a[1:]
    elif a[0] == '--only': only = a[1]; a = a[2:]
    else: dirs.append(a[0]); a = a[1:]
files = [os.path.join(d, 'spu_recomp.c') for d in dirs] if dirs else sorted(glob.glob(os.path.join(root, '*', 'spu_recomp.c')))
if only: files = [f for f in files if only in f]

GPR = r'ctx->gpr\[\d+\]'
COND = r'\((?:[^{};]*)\)'
INT_CHECK = re.compile(r'^if \(ctx->int_enable && \(ctx->event_status & ctx->event_mask\)\) \{ ctx->pc = 0x[0-9A-Fa-f]+; g_spu_trampoline_fn = \w+; return; \}$')
DIRECT = r'\{ SPU_DIRECT\(ctx, 0x[0-9A-Fa-f]+, \w+\); \}'
BIE = r'(?: /\* direct_bie: r\d+ \*/)?'
SHAPES = [
    ('label',  re.compile(r'^loc_[0-9A-Fa-f]+:$')),
    ('note',   re.compile(r'^/\*[^*]*\*/;$')),
    ('op',     re.compile(r'^' + GPR + r' = spu_[a-z0-9_]+\(.*\);$')),
    ('store',  re.compile(r'^spu_ls_write128\(ctx, .*\);$')),
    ('cgoto',  re.compile(r'^if ' + COND + r' goto loc_[0-9A-Fa-f]+;$')),
    ('goto',   re.compile(r'^goto loc_[0-9A-Fa-f]+;$')),
    ('ret',    re.compile(r'^SPU_RET\(ctx\);$')),
    ('cret',   re.compile(r'^if ' + COND + r' \{ SPU_RET\(ctx\); \}$')),
    ('iret',   re.compile(r'^ctx->int_enable = \d+; SPU_RET\(ctx\);$')),
    ('retreg', re.compile(r'^SPU_RET_REG\(ctx, \d+\);$')),
    ('direct', re.compile(r'^' + DIRECT + r'$')),
    ('cdirect', re.compile(r'^if ' + COND + r' ' + DIRECT + r'$')),
    ('idirect', re.compile(r'^ctx->int_enable = \d+; ' + DIRECT + BIE + r'$')),
    ('igoto',  re.compile(r'^ctx->int_enable = \d+; goto loc_[0-9A-Fa-f]+;' + BIE + r'$')),
]
EXITS = ('ret', 'cret', 'iret', 'retreg', 'direct', 'cdirect', 'idirect', 'intcheck')
FINAL = ('ret', 'iret', 'retreg', 'direct', 'idirect', 'goto', 'igoto')
DENY = ('spu_rdch', 'spu_wrch', 'spu_rchcnt', 'spu_indirect', 'spu_halt', 'spu_stop', 'spu_link', 'spu_drain')
# what may mention ctx in a promoted line, apart from the registers
CTX_OK = re.compile(GPR + r'|spu_ls_(?:read|write)128\(ctx,|SPU_RET\(ctx\)|SPU_RET_REG\(ctx,|SPU_DIRECT\(ctx,|ctx->int_enable = \d+;')

def shape(t):
    if INT_CHECK.match(t): return 'intcheck'
    for name, rx in SHAPES:
        if rx.match(t):
            if any(d in t for d in DENY): return None
            if 'ctx' in CTX_OK.sub('', t): return None
            return name
    return None

def promote(body):
    """body: the lines of one function (without its braces). Returns the new lines or None."""
    kinds = []
    for b in body:
        t = b.strip()
        if not t: kinds.append(''); continue
        k = shape(t)
        if k is None: return None
        kinds.append(k)
    if not any(k in EXITS for k in kinds): return None
    text = '\n'.join(body)
    used = sorted({int(n) for n in re.findall(r'ctx->gpr\[(\d+)\]', text)})
    written = sorted({int(n) for n in re.findall(r'ctx->gpr\[(\d+)\] = ', text)})
    if not used or sum(1 for k in kinds if k in ('op', 'store')) < 2: return None
    ind = re.match(r'\s*', body[0]).group(0) if body else '        '
    out = [ind + 'spu_vreg ' + ', '.join('r%d = SPU_U2V(ctx->gpr[%d])' % (n, n) for n in used) + ';']
    spill = ' '.join('ctx->gpr[%d] = SPU_V2U(r%d);' % (n, n) for n in written)
    last = ''
    for b, k in zip(body, kinds):
        if k: last = k
        if k in ('', 'label', 'note', 'goto', 'igoto'): out.append(b); continue
        if k == 'intcheck':
            out.append(b.replace('{ ctx->pc = 0x', '{ ' + spill + ' ctx->pc = 0x') if spill else b); continue
        b = re.sub(r'ctx->gpr\[(\d+)\]\._u32\[0\]', r'SPU_V32(r\1)', b)
        b = re.sub(r'ctx->gpr\[(\d+)\]\._u16\[0\]', r'SPU_V16(r\1)', b)
        if k == 'op':
            b = re.sub(r'ctx->gpr\[(\d+)\] = (.*);$', r'r\1 = SPU_U2V(\2);', b)
        b = re.sub(r'ctx->gpr\[(\d+)\]', r'SPU_V2U(r\1)', b)
        if spill:
            if k in ('ret', 'iret'): b = b.replace('SPU_RET(ctx);', '{ ' + spill + ' SPU_RET(ctx); }')
            elif k == 'cret': b = b.replace('{ SPU_RET(ctx); }', '{ ' + spill + ' SPU_RET(ctx); }')
            elif k == 'retreg': b = re.sub(r'(SPU_RET_REG\(ctx, \d+\);)', '{ ' + spill.replace('\\', '\\\\') + r' \1 }', b)
            elif k in ('direct', 'cdirect', 'idirect'): b = b.replace('{ SPU_DIRECT(ctx,', '{ ' + spill + ' SPU_DIRECT(ctx,')
        out.append(b)
    if last not in FINAL and spill: out.append(ind + spill + '   /* falls off the end */')
    return out

FUNC = re.compile(r'^void \w+\(spu_context\* ctx\) \{\s*$')
tot_f = tot_p = tot_l = tot_pl = 0
for f in files:
    bak = f + '.prepromote'
    if restore:
        if os.path.exists(bak): shutil.copyfile(bak, f); os.remove(bak); print('restored', f)
        continue
    src = open(f, encoding='latin-1', newline='').read()
    nl = '\r\n' if '\r\n' in src else '\n'
    lines = src.split(nl)
    out = []; i = 0; nf = npromo = nl_all = nl_promo = already = 0
    while i < len(lines):
        if FUNC.match(lines[i]):
            j = i + 1
            while j < len(lines) and lines[j] != '}': j += 1
            body = lines[i + 1:j]
            nf += 1; nl_all += len(body)
            if body and 'spu_vreg ' in body[0]: already += 1; new = None
            else: new = promote(body)
            out.append(lines[i])
            if new is not None: npromo += 1; nl_promo += len(body); out.extend(new)
            else: out.extend(body)
            i = j
        else:
            out.append(lines[i]); i += 1
    tot_f += nf; tot_p += npromo; tot_l += nl_all; tot_pl += nl_promo
    name = os.path.basename(os.path.dirname(f))
    print('%-34s %5d functions, %5d promoted (%4.1f %% of the lines)%s' % (name, nf, npromo, 100.0 * nl_promo / nl_all if nl_all else 0,
          ', %d already promoted' % already if already else ''))
    if not stats and npromo:
        if not os.path.exists(bak): shutil.copyfile(f, bak)
        open(f, 'w', encoding='latin-1', newline='').write(nl.join(out))
if not restore:
    print('total: %d functions, %d promoted (%.1f %% of the lines)%s' % (tot_f, tot_p, 100.0 * tot_pl / tot_l if tot_l else 0, ' [--stats: nothing written]' if stats else ''))
