"""Snapshot the local store of the Multistream SPU task of the running game and compare the
MP3 codec region with the firmware file (flashMP3.pic is loaded at LS 0x1A880 + vaddr).

    python scripts/ms_ls_snap.py <out.bin> [--n 1] [--every 2.0]

Finds the context like host_spuctx.py does (the "spu job" thread whose pc or link register is
above 0x1A000 or whose LS holds the codec), dumps 256 KB, prints which 0x1000 pages of the
codec's text/rodata match the file. With --n > 1, takes several snapshots (<out>.<i>.bin).
"""
import argparse, ctypes, struct, subprocess, sys, os, time, re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from guest_peek import find_pid, PROCESS_VM_READ, PROCESS_QUERY_INFORMATION  # noqa: E402

PIC = 'I:/Projets/Recomp/tools/rpcs3/dev_flash/sys/external/flashMP3.pic'
BASE = 0x1A880
LS_OFF = 0x40800


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('--n', type=int, default=1)
    ap.add_argument('--every', type=float, default=2.0)
    a = ap.parse_args()
    k32 = ctypes.windll.kernel32
    k32.OpenProcess.restype = ctypes.c_void_p
    h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, find_pid())

    def rd(addr, n):
        b = ctypes.create_string_buffer(n)
        got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(addr), b, n, ctypes.byref(got)):
            return None
        return b.raw

    img7 = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'work', 'BCES00484',
                             'spu_images', 'spu_3f69ca9ef76f.elf'), 'rb').read()
    pic = open(PIC, 'rb').read()
    seg = pic[0x100:0x100 + 0xFF10]
    out = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'host_spuctx.py'),
                          '--name', 'spu job'], capture_output=True, text=True).stdout
    ctxs = [int(m.group(1), 16) for m in re.finditer(r'ctx=([0-9A-F]+)', out)]
    best = None
    for c in ctxs:
        p = rd(c + LS_OFF, 8)
        if not p:
            continue
        ls = rd(struct.unpack('<Q', p)[0], 0x40000)
        if ls and ls[0x3000:0x3040] == img7[0x100:0x140]:   # Multistream's own text
            best = c
            break
    if best is None:
        sys.exit('Multistream context not found (contexts: %d)' % len(ctxs))
    print('context %X' % best)
    for i in range(a.n):
        ls = rd(struct.unpack('<Q', rd(best + LS_OFF, 8))[0], 0x40000)
        name = a.out if a.n == 1 else '%s.%d.bin' % (a.out, i)
        open(name, 'wb').write(ls)
        row = ''
        for o in range(0, 0xFF10, 0x1000):
            n = min(0x1000, 0xFF10 - o)
            same = sum(1 for k in range(0, n, 16) if seg[o + k:o + k + 16] == ls[BASE + 0x80 + o + k:BASE + 0x80 + o + k + 16])
            row += ' %x:%3d%%' % ((o + 0x80) >> 12, 100 * same // (n // 16))
        print('snap %d %s match per 0x1000 of vaddr:%s' % (i, time.strftime('%H:%M:%S'), row), flush=True)
        if i + 1 < a.n:
            time.sleep(a.every)


if __name__ == '__main__':
    main()
