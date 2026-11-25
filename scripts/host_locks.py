"""Dump the lv2 mutexes / condition variables of the running MotorStormApocalypse.exe.

    python scripts/host_locks.py [--all]

Reads g_sys_mutexes / g_sys_conds (addresses from port/build/MotorStormApocalypse.map, struct
layouts of ps3recomp/runtime/syscalls/sys_mutex.h and sys_cond.h on Win64: 88 and 80 bytes).
Default: mutexes that are owned or waited on, conds with a waiter. For a frozen game this
names the guest thread (owner tid = guest thread id, as in PORT_WATCH lines) holding the
mutex another thread spins or blocks on.
"""
import ctypes, ctypes.wintypes as wt, os, re, struct, sys

sys.path.insert(0, os.path.dirname(__file__))
from guest_peek import find_pid  # noqa: E402
from host_stacks import exe_image  # noqa: E402

MAP = os.path.join(os.path.dirname(__file__), "..", "port", "build", "MotorStormApocalypse.map")
MUTEX_SZ, COND_SZ, NMAX = 88, 80, 8192


def sym_rva(name):
    base = 0x140000000
    for line in open(MAP, encoding="latin-1"):
        if "Preferred load address is" in line:
            base = int(line.split()[-1], 16)
        m = re.match(r"\s*[0-9a-f]{4}:[0-9a-f]+\s+%s\s+([0-9a-f]{16})\s" % re.escape(name), line)
        if m:
            return int(m.group(1), 16) - base
    sys.exit("symbol %s not in the map" % name)


def main():
    show_all = "--all" in sys.argv
    k32 = ctypes.windll.kernel32
    k32.OpenProcess.restype = wt.HANDLE
    h = k32.OpenProcess(0x0410, False, find_pid())
    base, _, _ = exe_image(h, 0)

    def rd(a, n):
        b = (ctypes.c_ubyte * n)(); got = ctypes.c_size_t()
        k32.ReadProcessMemory(h, ctypes.c_void_p(a), b, n, ctypes.byref(got))
        return bytes(b)

    mt = rd(base + sym_rva("g_sys_mutexes"), MUTEX_SZ * NMAX)
    print("mutexes (id name recursive owner_tid lock_count waiters | host cs: LockCount RecursionCount OwningThread)")
    for i in range(NMAX):
        e = mt[i * MUTEX_SZ:(i + 1) * MUTEX_SZ]
        active, name, proto, rec = struct.unpack_from("<i8sIi", e, 0)
        owner, count, waiters = struct.unpack_from("<Qii", e, 24)
        lockc, recc, own_host = struct.unpack_from("<iiQ", e, 48)
        if not active:
            continue
        if show_all or owner or waiters or recc:
            print("  %4d %-8s rec=%d owner=%d count=%d waiters=%d | cs %d %d host-tid %d" % (
                i + 1, name.split(b"\0")[0].decode("latin-1"), rec, owner, count, waiters, lockc, recc, own_host))
    ct = rd(base + sym_rva("g_sys_conds"), COND_SZ * NMAX)
    print("conds (id name mutex waiters?)")
    for i in range(NMAX):
        e = ct[i * COND_SZ:(i + 1) * COND_SZ]
        active, mid, name = struct.unpack_from("<iI8s", e, 0)
        wptr = struct.unpack_from("<Q", e, 24)[0]
        if active and (show_all or wptr):
            print("  %4d %-8s mutex=%d waiters=%s" % (i + 1, name.split(b"\0")[0].decode("latin-1"), mid,
                                                    "yes" if wptr else "no"))


if __name__ == "__main__":
    main()
