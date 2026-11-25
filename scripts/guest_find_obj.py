"""Find the title's objects that point to a given static string (their name), in a running game.

    python scripts/guest_find_obj.py <pid|0> <string> [--off 8] [--dump 0x60] [--vt 16]
    python scripts/guest_find_obj.py 0 QueryFormLogic
    python scripts/guest_find_obj.py 46236 --word 0x010DB454          # any 32-bit value instead

Evolution's NetLogicComponent objects keep a pointer to their static name at +8 (the "Name[%s]"
of the [game] log lines, PORT_GAME_LOG): the string is looked up in the EBOOT, every guest word
that holds its address is listed, and for each one the object around it (start = hit - --off) is
dumped with its vtable: slot -> OPD -> func_XXXXXXXX, the name of the lifted function.
pid 0 = the first MotorStormApocalypse.exe (two instances: give the pid, see the window titles).
No debugger, the game keeps running (values may change while they are read).
"""
import ctypes, os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from guest_peek import MBI, find_pid, find_vm_base, PROCESS_VM_READ, PROCESS_QUERY_INFORMATION  # noqa: E402

ELF = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'game', 'BCES00484', 'EBOOT.elf'))
MEM_COMMIT = 0x1000


def elf_segments(elf):
    phoff, = struct.unpack_from('>Q', elf, 0x20)
    phentsize, phnum = struct.unpack_from('>HH', elf, 0x36)
    segs = []
    for i in range(phnum):
        ptype, _flags, off, vaddr, _paddr, filesz, _memsz = struct.unpack_from('>IIQQQQQ', elf, phoff + i * phentsize)
        if ptype == 1 and filesz:
            segs.append((vaddr, off, filesz))
    return segs


def string_addrs(text):
    elf = open(ELF, 'rb').read()
    pat = b'\0' + text.encode('latin-1') + b'\0'
    out = []
    for vaddr, off, filesz in elf_segments(elf):
        blob = elf[off:off + filesz]
        i = blob.find(pat)
        while i >= 0:
            out.append(vaddr + i + 1)
            i = blob.find(pat, i + 1)
    return out


def main():
    argv = sys.argv[1:]
    opts = {'--off': 8, '--dump': 0x60, '--vt': 16, '--word': None}
    pos = []
    i = 0
    while i < len(argv):
        if argv[i] in opts:
            opts[argv[i]] = int(argv[i + 1], 0)
            i += 2
        else:
            pos.append(argv[i])
            i += 1
    if not pos or (len(pos) < 2 and opts['--word'] is None):
        sys.exit(__doc__)
    pid = int(pos[0], 0) or find_pid()
    words = [opts['--word']] if opts['--word'] is not None else string_addrs(pos[1])
    if not words:
        sys.exit('string not found in the EBOOT')
    print('looking for', ', '.join('%08X' % w for w in words), 'in pid', pid)

    k32 = ctypes.windll.kernel32
    k32.VirtualQueryEx.restype = ctypes.c_size_t
    h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
    if not h:
        sys.exit('OpenProcess failed')
    # find_vm_base only needs the handle
    base = find_vm_base(h)

    def read(ea, n):
        buf = ctypes.create_string_buffer(n)
        got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(h, ctypes.c_void_p(base + ea), buf, n, ctypes.byref(got)):
            return None
        return buf.raw[:got.value]

    def rd32(ea):
        b = read(ea, 4)
        return struct.unpack('>I', b)[0] if b and len(b) == 4 else None

    hits = []
    addr, mbi = base, MBI()
    end = base + 0x100000000
    while addr < end and k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
        rbase, rsize = mbi.BaseAddress or 0, mbi.RegionSize
        if mbi.State == MEM_COMMIT and not (mbi.Protect & 0x101):       # not NOACCESS / GUARD
            pos_ = rbase
            while pos_ < min(rbase + rsize, end):
                n = min(0x1000000, rbase + rsize - pos_, end - pos_)
                blob = read(pos_ - base, n)
                if blob:
                    for w in words:
                        pat = struct.pack('>I', w)
                        j = blob.find(pat)
                        while j >= 0:
                            if not (j & 3):
                                hits.append(pos_ - base + j)
                            j = blob.find(pat, j + 1)
                pos_ += n
        addr = rbase + rsize
    print(len(hits), 'hit(s)')
    for hit in hits:
        obj = hit - opts['--off']
        if 0x10000 <= hit < 0x1500000:
            print('  %08X  (in the image: a table, not an object)' % hit)
            continue
        print('object %08X (name pointer at %08X)' % (obj, hit))
        blob = read(obj, opts['--dump']) or b''
        for o in range(0, len(blob) - 3, 16):
            ws = struct.unpack('>%dI' % (len(blob[o:o + 16]) // 4), blob[o:o + 16][:len(blob[o:o + 16]) // 4 * 4])
            print('    +%03X  %s' % (o, ' '.join('%08X' % w for w in ws)))
        vt = rd32(obj)
        if vt and 0x10000 <= vt < 0x1500000:
            print('    vtable %08X:' % vt)
            for k in range(opts['--vt']):
                opd = rd32(vt + 4 * k)
                fn = rd32(opd) if opd and 0x10000 <= opd < 0x1500000 else None
                print('      +%02X  %08X -> %s' % (4 * k, opd or 0, ('func_%08X' % fn) if fn else '?'))


if __name__ == '__main__':
    main()
