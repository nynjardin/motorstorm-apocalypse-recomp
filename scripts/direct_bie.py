"""Turn constant-target `bid`/`bie`/`bi` sites of lifted SPU modules into direct branches.

The WWS job modules toggle interrupts around their MFC work with
    ila  $2, next
    bid  $2          (or bie)
The lifter lowers every bi* as an indirect transfer:
    ctx->gpr[2] = spu_ila(0x4078);
    ctx->int_enable = 0; ctx->pc = ctx->gpr[2]._u32[0]; g_spu_trampoline_fn = spu_indirect_branch; return;
-> a host return to the drain loop, the whole spu_indirect_branch resolver and a dispatch-cache
lookup, ~1800 sites in the job modules, on the critical SPU of a race frame. The target is a
constant inside the same module, so this rewrites the transfer as
    ctx->int_enable = 0; { SPU_DIRECT(ctx, 0x4078, <module>_spu_func_00004078); }
(the register write stays: it is architectural state). SPU_DIRECT keeps the drain loop's per-step
duties: it falls back to the trampoline when an interrupt is pending with interrupts enabled
(spu_take_interrupt then runs exactly as before), at LS 0, on the run's first transfer and on the
stack-reset hint table. Only sites whose target is a function of the same file are rewritten.

Idempotent. Re-run after any regeneration of the modules (lift_jobmods / relift_jobmods.py).
    python scripts/direct_bie.py [--dry-run] [--restore] [dir_substr ...]
--restore: put back the original transfers (from the marker comment left on each site).
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SPU = os.path.normpath(os.path.join(HERE, '..', 'port', 'spu'))

FUNC = re.compile(r'^void (\w+?_spu_func_)([0-9A-F]{8})\(spu_context\* ctx\) \{', re.M)
SITE = re.compile(
    r'(?P<ila>ctx->gpr\[(?P<r>\d+)\] = spu_ila\(0x(?P<k>[0-9A-F]+)\);\n)'
    r'(?P<ind>[ \t]*)(?P<ie>ctx->int_enable = [01]; )?'
    r'ctx->pc = ctx->gpr\[(?P=r)\]\._u32\[0\]; g_spu_trampoline_fn = spu_indirect_branch; return;')
DONE = re.compile(
    r'(?P<ie>ctx->int_enable = [01]; )?(?:\{ SPU_DIRECT\(ctx, 0x(?P<k>[0-9A-F]+), \w+\); \}|'
    r'goto loc_[0-9A-F]{8};) /\* direct_bie: r(?P<r>\d+) \*/')
LABEL = re.compile(r'^loc_([0-9A-F]{8}):', re.M)


def process(path, dry, restore):
    src = open(path, encoding='latin-1').read()
    if restore:
        new, n = DONE.subn(lambda m: '%sctx->pc = ctx->gpr[%s]._u32[0]; g_spu_trampoline_fn = '
                           'spu_indirect_branch; return;' % (m.group('ie') or '', m.group('r')), src)
        skipped = 0
    else:
        funcs = {}
        heads = list(FUNC.finditer(src))
        for h in heads:
            funcs[int(h.group(2), 16)] = h.group(1) + h.group(2)
        n = skipped = 0
        labels = set()

        def rep(m):
            nonlocal n, skipped
            k = int(m.group('k'), 16)
            fn = funcs.get(k)
            if not fn:
                skipped += 1
                return m.group(0)
            n += 1
            if k in labels:
                # --merge-chunks function holding the target chunk: a goto. The lifter's
                # pending-interrupt check sits at the label (every merged chunk start).
                return '%s%s%sgoto loc_%08X; /* direct_bie: r%s */' % (
                    m.group('ila'), m.group('ind'), m.group('ie') or '', k, m.group('r'))
            return '%s%s%s{ SPU_DIRECT(ctx, 0x%X, %s); } /* direct_bie: r%s */' % (
                m.group('ila'), m.group('ind'), m.group('ie') or '', k, fn, m.group('r'))
        # per function, so a target is a goto only when its label is in the same C function
        out, pos = [], 0
        for i, h in enumerate(heads):
            end = heads[i + 1].start() if i + 1 < len(heads) else len(src)
            out.append(src[pos:h.start()])
            body = src[h.start():end]
            labels = {int(a, 16) for a in LABEL.findall(body)}
            out.append(SITE.sub(rep, body))
            pos = end
        out.append(src[pos:])
        new = ''.join(out)
    if n and not dry:
        with open(path, 'w', encoding='latin-1', newline='') as f:
            f.write(new)
    return n, skipped


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    dry, restore = '--dry-run' in sys.argv, '--restore' in sys.argv
    tot = totskip = 0
    for d in sorted(os.listdir(SPU)):
        p = os.path.join(SPU, d, 'spu_recomp.c')
        if not os.path.isfile(p):
            continue
        if args and not any(a in d for a in args):
            continue
        n, s = process(p, dry, restore)
        if n or s:
            print('%-34s %s %4d%s' % (d, 'restored' if restore else 'direct', n,
                                      ('  (%d targets not in file)' % s) if s else ''))
        tot += n; totskip += s
    print('total: %d sites%s%s' % (tot, (', %d skipped' % totskip) if totskip else '',
                                   ' (dry run)' if dry else ''))


if __name__ == '__main__':
    main()
