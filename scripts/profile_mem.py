"""The player's profile (the XML the title saves in AUTOSAVE.DAT) read from a running game.

    python scripts/profile_mem.py [--grep <regex>] [--out <file.xml>] [--all]
    MS_PID=<pid> python scripts/profile_mem.py --grep "form\\.|chips|online"

The title keeps plain-text copies of the profile XML in guest memory (the buffer it last loaded
or saved: <root><ProfileVersion .../><Chunk name = "form"> <Key name="player_xp_curr_total"
value = "1000" type = "int" /> ...). This finds every complete copy (from "<root>" to "</root>"),
takes the last one in memory order unless --all, and prints its keys as chunk.key = value.
They are freed buffers: a copy can be older than the live values (compare with --all).
The online progression is there: chunk "form" (player_xp_curr_total = chips / experience,
player_rank_level, ...), statistics in "global" (docs/reseau.md). MS_PID picks the instance.
The save file itself is compressed (LZSS-like, variable length / distance split per token: not decoded,
notes in docs/reseau.md), so the profile is read here, from memory.
"""
import argparse, ctypes, os, re, sys

sys.path.insert(0, os.path.dirname(__file__))
import guest_peek as g  # noqa: E402

k32 = ctypes.windll.kernel32


class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", ctypes.c_ulong), ("PartitionId", ctypes.c_ushort),
                ("RegionSize", ctypes.c_size_t), ("State", ctypes.c_ulong),
                ("Protect", ctypes.c_ulong), ("Type", ctypes.c_ulong)]


def committed(h, base, lo, hi):
    """(ea, size) of the committed, readable parts of guest [lo, hi)."""
    a = base + lo
    mbi = MBI()
    while a < base + hi and k32.VirtualQueryEx(h, ctypes.c_void_p(a), ctypes.byref(mbi), ctypes.sizeof(mbi)):
        size = mbi.RegionSize - (a - (mbi.BaseAddress or 0))
        if mbi.State == 0x1000 and not (mbi.Protect & 0x101):      # MEM_COMMIT, not NOACCESS / GUARD
            yield a - base, min(size, base + hi - a)
        a += size


def read(h, base, ea, n):
    buf = (ctypes.c_ubyte * n)()
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(base + ea), buf, n, ctypes.byref(got)):
        return b''
    return bytes(buf[:got.value])


def profiles(h, base):
    out = []
    for ea, size in committed(h, base, 0x10000000, 0x70000000):
        pos = 0
        while pos < size:
            n = min(size - pos, 8 << 20)
            b = read(h, base, ea + pos, n + (1 << 20) if pos + n < size else n)
            # from "<root>": the first bytes of a freed buffer ("<?xml ...") are often overwritten
            for m in re.finditer(rb'<root>\r\n\t<ProfileVersion', b[:n]):
                e = b.find(b'</root>', m.start())
                nxt = b.find(b'<root>', m.end())             # a copy whose end was overwritten
                if 0 < e - m.start() < (1 << 20) and not (0 <= nxt < e):
                    out.append((ea + pos + m.start(), b[m.start():e + 7]))
            pos += n
    return out


def keys_of(xml):
    chunk, out = '', []
    for m in re.finditer(rb'<Chunk name\s*=\s*"([^"]*)"|<Key name\s*=\s*"([^"]*)"\s*value\s*=\s*"([^"]*)"', xml):
        if m.group(1) is not None:
            chunk = m.group(1).decode('latin-1')
        else:
            out.append((chunk + '.' + m.group(2).decode('latin-1'), m.group(3).decode('latin-1')))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--grep', default='')
    ap.add_argument('--out', default='')
    ap.add_argument('--all', action='store_true')
    a = ap.parse_args()
    h = k32.OpenProcess(0x410, False, g.find_pid())
    if not h:
        sys.exit('OpenProcess failed')
    base = g.find_vm_base(h)
    found = profiles(h, base)
    if not found:
        sys.exit('no complete profile XML in memory (enter a menu that loads or saves the profile)')
    for ea, xml in (found if a.all else found[-1:]):
        ks = keys_of(xml)
        print('== profile at 0x%08X: %d bytes, %d keys (%d copies in memory)' % (ea, len(xml), len(ks), len(found)))
        for k, v in ks:
            if not a.grep or re.search(a.grep, k, re.I):
                print('  %-52s %s' % (k, v))
    if a.out:
        open(a.out, 'wb').write(found[-1][1])
        print('wrote', a.out)


if __name__ == '__main__':
    main()
