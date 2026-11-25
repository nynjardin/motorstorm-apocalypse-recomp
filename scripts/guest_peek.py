"""Read guest memory of a running MotorStormApocalypse.exe (no debugger, no pause).

    python scripts/guest_peek.py <ea> [<len>=0x100] [<ea> <len> ...]
    python scripts/guest_peek.py 0x18314670 0x50 0x1894C990 0x180

Guest RAM is one reservation of 0x100010000 bytes (vm_base); it is found by walking the
process' regions and grouping them by AllocationBase. Prints big-endian 32-bit words.
"""
import ctypes, ctypes.wintypes as wt, subprocess, sys

PROCESS_VM_READ, PROCESS_QUERY_INFORMATION = 0x10, 0x400
GUEST_SPAN = 0x100010000


class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wt.DWORD), ("PartitionId", wt.WORD),
                ("RegionSize", ctypes.c_size_t), ("State", wt.DWORD),
                ("Protect", wt.DWORD), ("Type", wt.DWORD)]


def find_pid(name="MotorStormApocalypse.exe"):
    # Two instances (LAN tests): MS_PID=<pid> picks one for every tool built on this function.
    import os
    if os.environ.get("MS_PID"):
        return int(os.environ["MS_PID"], 0)
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if parts and parts[0].lower() == name.lower():
            return int(parts[1])
    sys.exit(f"{name} is not running")


def find_vm_base(h):
    k32 = ctypes.windll.kernel32
    k32.VirtualQueryEx.restype = ctypes.c_size_t
    spans, addr, mbi = {}, 0, MBI()
    while k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
        if mbi.State != 0x10000 and mbi.AllocationBase:  # not MEM_FREE
            ab = mbi.AllocationBase
            end = mbi.BaseAddress + mbi.RegionSize
            spans[ab] = max(spans.get(ab, 0), end - ab)
        addr = (mbi.BaseAddress or 0) + mbi.RegionSize
        if addr >= 1 << 47:
            break
    for ab, span in spans.items():
        if span == GUEST_SPAN:
            return ab
    sys.exit("guest reservation (0x100010000 bytes) not found")


def main():
    args = [int(a, 0) for a in sys.argv[1:]]
    if not args:
        sys.exit(__doc__)
    if len(args) % 2:
        args.append(0x100)
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, find_pid())
    if not h:
        sys.exit("OpenProcess failed")
    base = find_vm_base(h)
    for ea, n in zip(args[::2], args[1::2]):
        buf = (ctypes.c_ubyte * n)()
        got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(h, ctypes.c_void_p(base + ea), buf, n, ctypes.byref(got)):
            print(f"0x{ea:08X}: unreadable")
            continue
        b = bytes(buf[:got.value])
        for o in range(0, len(b), 16):
            words = " ".join(b[o + i:o + i + 4].hex().upper() for i in range(0, min(16, len(b) - o), 4))
            text = "".join(chr(c) if 32 <= c < 127 else "." for c in b[o:o + 16])
            print(f"0x{ea + o:08X}: {words:<35}  {text}")


if __name__ == "__main__":
    main()
