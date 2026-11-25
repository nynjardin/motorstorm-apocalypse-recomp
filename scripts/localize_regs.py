"""Keep SPU registers in C locals inside each lifted SPU function.

The lifter writes every instruction as  ctx->gpr[a] = spu_op(ctx->gpr[b], ctx->gpr[c]);
ctx->gpr[] is a union reached through a pointer and local-store accesses go through a
byte pointer, so the compiler must assume each LS store changes every register and each
register store changes LS: nothing stays in a host register, every value is stored and
loaded again. This rewrites each function so that registers are locals (r_N):

    u128 r_3, r_4, ...;  RELOAD();          entry: every register the function names
    r_4 = spu_a(r_3, r_5);                  pure lines: locals only
    <flush dirty>; spu_wrch(ctx, ...); RELOAD();     anything that passes ctx on
    if (r_5._u32[0] == 0) { <flush dirty>; SPU_DIRECT(...); }
    <flush dirty>; SPU_RET(ctx);

A line "passes ctx on" when it hands ctx to anything but spu_ls_read128/spu_ls_write128
(channels, stop, calls, tail calls, returns to the drain loop): such code may read or
write ctx->gpr[], or abandon this frame (longjmp restart), so ctx->gpr[] is made current
before it and every local is read back after it when execution continues. The text of
those lines is left untouched. "Dirty" = registers possibly written since the last
flush, from a forward data-flow over the function's labels and gotos.

Run after relift_jobmods.py --merge and direct_bie.py (it is the last step):
    python scripts/localize_regs.py [--dry-run] [--restore] [dir_substr ...]
Default: the WWS job modules (port/spu/jobmod_*). Originals are copied once to
E:/ms_perf/bak_spu_prelocal/<module>/spu_recomp.c; --restore puts them back.
"""
import os, re, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SPU = os.path.normpath(os.path.join(HERE, '..', 'port', 'spu'))
BAK = r'E:\ms_perf\bak_spu_prelocal'
MARK = '/* localize_regs.py: registers are locals inside each function */'

FUNC = re.compile(r'^void (\w+)\(spu_context\* ctx\) \{\s*$')
LABEL = re.compile(r'^loc_([0-9A-F]{8}):\s*$')
REG = re.compile(r'ctx->gpr\[(\d+)\]')
WRITE = re.compile(r'ctx->gpr\[(\d+)\](?:\._\w+\[\d+\])?\s*(?:[-+|&^]|<<|>>)?=(?!=)')
FULL_DEF = re.compile(r'^ctx->gpr\[(\d+)\] = ')      # whole-register assignment opening a line
ESC = re.compile(r'\(\s*ctx\s*[,)]')
PURE_CTX = re.compile(r'spu_ls_(?:read|write)128\(ctx,')
GOTO = re.compile(r'goto (loc_[0-9A-F]{8});')
COND_GOTO = re.compile(r'^if \(.*\) goto loc_[0-9A-F]{8};')
COND_LEAVE = re.compile(r'^if \((.*?)\) \{ (.*) \}\s*(/\*.*\*/)?\s*$')


def passes_ctx(text):
    return bool(ESC.search(PURE_CTX.sub('spu_ls_x(c,', text))) or '&ctx->gpr' in text


def leaves(text):
    return 'return;' in text or 'SPU_DIRECT(' in text or 'SPU_RET' in text


def local(text):
    return REG.sub(lambda m: 'r_%s' % m.group(1), text)


def classify(line):
    """-> (kind, data). kinds: label, pure, goto (unconditional), cgoto, cleave, leave, esc."""
    s = line.strip()
    m = LABEL.match(s)
    if m:
        return 'label', 'loc_' + m.group(1)
    esc = passes_ctx(s)
    if not esc and not leaves(s):
        g = GOTO.search(s)
        if g:
            return ('cgoto' if COND_GOTO.match(s) else 'goto'), g.group(1)
        return 'pure', None
    m = COND_LEAVE.match(s)
    if m and leaves(m.group(2)) and not passes_ctx(m.group(1)) and 'goto ' not in s:
        return 'cleave', m
    if leaves(s) and not s.startswith('if ') and 'goto ' not in s:
        return 'leave', None
    return 'esc', None


def transform(name, body):
    kinds = [classify(l) for l in body]
    used, written_any = set(), set()
    for l, (k, _) in zip(body, kinds):
        if k in ('pure', 'goto', 'cgoto'):
            used |= {int(x) for x in REG.findall(l)}
        elif k == 'cleave':
            used |= {int(x) for x in REG.findall(_.group(1))}
    if not used:
        return body, 0
    # forward may-dirty data-flow
    lab_in = {d: set() for (k, d) in kinds if k == 'label'}
    flush = {}
    while True:
        changed = False
        cur = set()
        for i, (l, (k, d)) in enumerate(zip(body, kinds)):
            if cur is None and k != 'label':
                cur = set()               # unreachable by fall-through: nothing dirty
            if k == 'label':
                s = lab_in[d] | (cur or set())
                if s != lab_in[d]:
                    lab_in[d] = s; changed = True
                cur = set(s)
            elif k in ('pure', 'goto', 'cgoto'):
                cur |= {int(x) for x in WRITE.findall(l)}
                if k != 'pure':
                    if d in lab_in:
                        if not cur <= lab_in[d]:
                            lab_in[d] |= cur; changed = True
                    else:
                        raise SystemExit('%s: goto to a label outside the function: %s' % (name, d))
                    if k == 'goto':
                        cur = None
            elif k == 'cleave':
                flush[i] = set(cur)
            elif k == 'leave':
                flush[i] = set(cur); cur = None
            else:                         # esc: flushed, then every local reloaded
                flush[i] = set(cur); cur = set()
        if not changed:
            break
    # Backward liveness of the locals: what to read back after a line that passed ctx on, and
    # at entry. Reloading every local at each such line is correct too, but the SSA form of a
    # 4000-instruction function with ~100 locals and hundreds of reload points took clang more
    # than ten minutes a module. A line that passes ctx on, or leaves, reads no local (its
    # text uses ctx->gpr[], made current by the flush): nothing is live before it.
    def use_def(l):
        s = l.strip()
        m = FULL_DEF.match(s)
        if m:
            return {int(x) for x in REG.findall(s[m.end():])}, {int(m.group(1))}
        return {int(x) for x in REG.findall(s)}, set()

    lab_live = {d: set() for (k, d) in kinds if k == 'label'}
    after = {}
    while True:
        changed = False
        live = set()                      # after the last line: the function has left
        for i in range(len(body) - 1, -1, -1):
            l, (k, d) = body[i], kinds[i]
            if k == 'label':
                if live != lab_live[d]:
                    lab_live[d] = set(live); changed = True
            elif k == 'pure':
                u, df = use_def(l)
                live = (live - df) | u
            elif k == 'goto':
                u, df = use_def(l)
                live = (set(lab_live[d]) - df) | u
            elif k == 'cgoto':
                u, df = use_def(l)
                live = ((live | lab_live[d]) - df) | u
            # A flush stores every POSSIBLY dirty local: one that this path did not write must
            # hold the register's value all the same, so a flush is a use of what it stores.
            elif k == 'cleave':
                live = live | {int(x) for x in REG.findall(d.group(1))} | flush[i]
            elif k == 'leave':
                live = set(flush[i])
            else:
                after[i] = set(live)
                live = set(flush[i])
        if not changed:
            break
    entry = live
    ind = '        '
    regs = sorted(used)

    def fl(i):
        return ''.join('ctx->gpr[%d] = r_%d; ' % (r, r) for r in sorted(flush[i] & used))

    def rl(s):
        return ind + ' '.join('r_%d = ctx->gpr[%d];' % (r, r) for r in sorted(s & used)) + '\n' if s & used else ''

    out = [ind + 'u128 ' + ', '.join('r_%d' % r for r in regs) + ';\n', rl(entry)]
    for i, (l, (k, d)) in enumerate(zip(body, kinds)):
        if k == 'label':
            out.append(l)
        elif k in ('pure', 'goto', 'cgoto'):
            out.append(local(l))
        elif k == 'cleave':
            tail = (' ' + d.group(3)) if d.group(3) else ''
            out.append('%sif (%s) { %s%s }%s\n' % (ind, local(d.group(1)), fl(i), d.group(2), tail))
        elif k == 'leave':
            f = fl(i)
            out.append((ind + f.rstrip() + '\n' if f else '') + l)
        else:
            f = fl(i)
            out.append((ind + f.rstrip() + '\n' if f else '') + l + rl(after[i]))
    return out, len(regs)


def process(path, dry):
    src = open(path, encoding='latin-1', newline='').read()
    if MARK in src:
        return None
    nl = '\r\n' if '\r\n' in src[:4000] else '\n'
    lines = src.replace('\r\n', '\n').split('\n')
    out, i, nfun, nreg = [MARK], 0, 0, 0
    while i < len(lines):
        m = FUNC.match(lines[i])
        if not m:
            out.append(lines[i]); i += 1
            continue
        j = i + 1
        while lines[j] != '}':
            if lines[j].count('{') != lines[j].count('}'):
                raise SystemExit('%s:%d: statement spans lines: %s' % (path, j + 1, lines[j]))
            j += 1
        body = [l + '\n' for l in lines[i + 1:j]]
        new, n = transform(m.group(1), body)
        out.append(lines[i])
        out.extend(l.rstrip('\n') for l in new)
        out.append('}')
        nfun += 1; nreg += n
        i = j + 1
    if not dry:
        open(path, 'w', encoding='latin-1', newline='').write(nl.join(out))
    return nfun, nreg


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    dry, restore = '--dry-run' in sys.argv, '--restore' in sys.argv
    for d in sorted(os.listdir(SPU)):
        p = os.path.join(SPU, d, 'spu_recomp.c')
        if not os.path.isfile(p):
            continue
        if args:
            if not any(a in d for a in args):
                continue
        elif not d.startswith('jobmod_'):
            continue
        b = os.path.join(BAK, d, 'spu_recomp.c')
        if restore:
            if os.path.isfile(b) and MARK in open(p, encoding='latin-1').read(200):
                shutil.copy(b, p); print('%-34s restored' % d)
            continue
        if not dry and MARK not in open(p, encoding='latin-1').read(200):
            os.makedirs(os.path.dirname(b), exist_ok=True)
            shutil.copy(p, b)
        r = process(p, dry)
        print('%-34s %s' % (d, 'already done' if r is None else '%d functions, %d locals' % r))


if __name__ == '__main__':
    main()
