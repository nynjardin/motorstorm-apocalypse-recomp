"""Entry hooks in lifted guest functions: the port's way to change what a game function does.

    python scripts/func_hooks.py            # apply port/func_hooks.txt to work/BCES00484/recomp
    python scripts/func_hooks.py --list     # which hooks are in the lifted sources now
    python scripts/func_hooks.py --restore  # remove every hook line

Lifted code calls guest functions directly (`func_0038A8D0(ctx);`), so the HLE override table
(NIDs) cannot reach them. For each address listed in port/func_hooks.txt (one `0x........` per
line, `#` comments) this inserts, as the first statement of `void func_<ADDR>(ppu_context* ctx)`:

    { int port_hook_<ADDR>(ppu_context*); if (port_hook_<ADDR>(ctx)) return; } /* PORT_HOOK */

The port defines `int port_hook_<ADDR>(ppu_context* c)` (C++ linkage, port/net_hooks.cpp or
another port source): return 0 = let the game's function run (arguments may have been changed in
c->gpr[]), nonzero = the hook did the whole job, with its result in c->gpr[3].
Idempotent. REDO AFTER ANY PPU RELIFT (the lifted tree is regenerated), then rebuild: only the
translation units that hold a hooked function recompile. Lifted sources are latin-1 and are
rewritten byte for byte around the inserted line.
"""
import glob, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
RECOMP = os.path.normpath(os.path.join(HERE, '..', 'work', 'BCES00484', 'recomp'))
LIST = os.path.normpath(os.path.join(HERE, '..', 'port', 'func_hooks.txt'))
MARK = b'/* PORT_HOOK */'


def wanted():
    out = []
    for line in open(LIST, encoding='utf-8'):
        line = line.split('#')[0].strip()
        if line:
            out.append('%08X' % int(line, 16))
    return out


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ''
    want = [] if mode in ('--restore', '--list') else wanted()
    todo = set(want)
    for path in sorted(glob.glob(os.path.join(RECOMP, 'ppu_recomp_[0-9]*.cpp'))):
        data = open(path, 'rb').read()
        has = MARK in data
        if not has and not any(('void func_%s(' % a).encode() in data for a in want):
            continue
        nl = b'\r\n' if b'\r\n' in data else b'\n'
        lines = data.split(nl)
        if mode == '--list':
            for l in lines:
                if MARK in l:
                    print(os.path.basename(path), re.search(rb'port_hook_([0-9A-F]{8})', l).group(1).decode())
            continue
        out, changed, i = [], False, 0
        while i < len(lines):
            l = lines[i]
            if MARK in l:                      # drop: re-added below if still wanted
                changed = True
                i += 1
                continue
            out.append(l)
            m = re.match(rb'void func_([0-9A-F]{8})\(ppu_context\* ctx\) \{', l)
            if m and m.group(1).decode() in want:
                a = m.group(1).decode()
                # keep PPU_MM_SNAP (the lifter's first line) in front of the hook
                if i + 1 < len(lines) and lines[i + 1].strip() == b'PPU_MM_SNAP':
                    out.append(lines[i + 1])
                    i += 1
                out.append(('        { int port_hook_%s(ppu_context*); if (port_hook_%s(ctx)) return; } ' % (a, a)).encode() + MARK)
                todo.discard(a)
                changed = True
            i += 1
        new = nl.join(out)
        if changed and new != data:
            open(path, 'wb').write(new)
            print('rewrote', os.path.basename(path))
    for a in sorted(todo):
        print('NOT FOUND: func_%s' % a)
    if todo:
        sys.exit(1)


if __name__ == '__main__':
    main()
